"""Cross-producer refresh orchestration (ri-07).

One idempotent operation that drives every configured context producer for an
exact repository revision, stages their canonical results on the single ri-06
operation, and emits the durable manifest — without re-implementing any producer,
result, or manifest model.

Ownership boundary (design D1):

* Producers, results, generate/check protocol → ri-05 ``registry`` + the
  ``architecture`` producer (ri-04).
* Durable operation store, manifest projection, and every data model → ri-06
  ``project-context-runtime``.
* This module owns only *coordination*: order, recording, outcome, and manifest
  emission.

Two modes:

* :func:`generate` — reuse/create the canonical operation, run every configured
  producer, record each result **before** attempting the degradable semantic
  index, finalize the terminal outcome, then write + record the manifest.
* :func:`check` — fully read-only: run every producer in ``check`` mode, decide
  the aggregate outcome, and return it with an exit code (0 fresh · 2 drift · 1
  failed). It never writes the store or the working tree.

The semantic index (ri-02) is the one degradable producer: its failure or absence
degrades the outcome but never discards deterministic output, because deterministic
and architecture results are recorded first (design D3/D4).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

# Importing _runtime first inserts the ri-06 runtime scripts dir onto sys.path,
# so the bare ``store``/``manifest``/``models`` imports below resolve.
from _runtime import (
    Fallback,
    FallbackKind,
    ProducerResult,
    ProducerStatus,
    Remediation,
    SafeError,
    ensure_git_revision,
    sha256_hex,
)
from manifest import write_manifest
from models import (
    DuplicateProducerError,
    InvalidTransitionError,
    ManifestPointerStatus,
    OperationState,
    SemanticIndexReference,
)
from registry import Mode, list_producers, run_producer
from semantic_adapter import SemanticIndexer, resolve_semantic_index
from store import OperationStore

#: Repository-relative, gitignored manifest location. Kept out of the tracked
#: tree so a repeat refresh at the same revision produces no repository diff
#: (design D6); the ri-06 ``ManifestPointer`` still stores this exact path.
DEFAULT_MANIFEST_PATH = ".git-context/context-refresh-manifest.json"

# Producer id for the architecture producer (ri-04). Kept as a literal so this
# module does not import refresh-architecture at module load time.
ARCHITECTURE_PRODUCER_ID = "architecture"

# An architecture-result source: (repository, revision, mode) -> ProducerResult.
ArchitectureProducer = Callable[[Path, str, Mode], ProducerResult]


@dataclass(frozen=True, slots=True)
class RefreshResult:
    """Outcome of a refresh run (generate or check)."""

    operation_id: str | None
    outcome: OperationState
    producer_results: tuple[ProducerResult, ...]
    semantic_index: SemanticIndexReference | None = None
    manifest_path: str | None = None
    manifest_sha256: str | None = None

    def exit_code(self) -> int:
        """0 succeeded · 2 degraded (actionable drift) · 1 failed."""
        if self.outcome is OperationState.SUCCEEDED:
            return 0
        if self.outcome is OperationState.DEGRADED:
            return 2
        return 1


class RevisionMismatchError(ValueError):
    """Raised when an explicit revision is not the one actually checked out.

    A ``ValueError`` subclass so existing callers that fail closed on bad input
    keep working unchanged.
    """


def _git_out(repo_root: Path, *args: str) -> str:
    """Run a read-only git command in *repo_root*, returning stripped stdout.

    Returns an empty string when git is unavailable, the path is not a
    repository, or the command failed; every caller treats "" as "unknown".

    The return code check is load-bearing: in a repository with no commits
    ``git rev-parse HEAD`` echoes the literal string ``HEAD`` on stdout and exits
    128, so trusting stdout alone would report ``HEAD`` as the checked-out
    revision.
    """
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def resolve_repository_identity(
    repository: Path | str, revision: str | None
) -> tuple[Path, str, str]:
    """Return ``(repo_root, repository_id, full_revision)``.

    ``repository_id`` honors the ``PROJECT_CONTEXT_REPO_ID`` override and
    otherwise falls back to the repository directory name — the same rule as
    ``refresh-architecture``'s canonical ``provenance.repository_id``. Both must
    agree, or the same clone would yield two operation ids and split the ledger,
    hiding ri-04's architecture results from this refresh.

    An explicit *revision* MUST name the revision that is actually checked out.
    Every producer reads the live filesystem, so accepting some other SHA would
    persist and manifest artifacts under a revision they did not come from. When
    the path is not a git checkout at all there is no HEAD to contradict, and the
    supplied revision is taken at face value.
    """
    repo_root = Path(repository).resolve()
    toplevel = _git_out(repo_root, "rev-parse", "--show-toplevel")
    repo_root = Path(toplevel) if toplevel else repo_root
    repository_id = os.environ.get("PROJECT_CONTEXT_REPO_ID") or repo_root.name

    head = _git_out(repo_root, "rev-parse", "HEAD")
    rev = revision or head
    if not rev:
        raise ValueError("could not resolve HEAD; pass an explicit full-SHA revision")
    ensure_git_revision(rev)
    if revision and head and revision != head:
        raise RevisionMismatchError(
            f"requested revision {revision[:12]} is not the checked-out revision "
            f"{head[:12]}; producers read the working tree, so refresh accepts only "
            "the checked-out revision (check it out, or use a worktree at it)"
        )
    return repo_root, repository_id, rev


def _default_architecture_producer(
    repository: Path, revision: str, mode: Mode
) -> ProducerResult:
    """Read the current architecture provenance via the ri-04 canonical owner.

    Architecture *regeneration* is refresh-architecture's own staged command
    (`make architecture`, gated by ri-10); orchestration only collects the
    producer's current result. If refresh-architecture is not importable or its
    provenance cannot be built, architecture is reported ``not-configured`` with a
    skip fallback rather than failing the whole refresh.
    """
    arch_scripts = (
        Path(__file__).resolve().parents[2] / "refresh-architecture" / "scripts"
    )
    if arch_scripts.is_dir() and str(arch_scripts) not in sys.path:
        sys.path.insert(0, str(arch_scripts))
    try:
        from arch_utils import provenance  # type: ignore[import-not-found]
        from context_runtime_adapter import (  # type: ignore[import-not-found]
            architecture_result_fresh,
            architecture_result_not_configured,
        )
    except Exception as exc:  # noqa: BLE001 - missing owner degrades, never fails
        return _architecture_not_configured_fallback(
            f"refresh-architecture not importable: {exc}"
        )
    try:
        doc = provenance.build_provenance(repository, mode="full")
        return architecture_result_fresh(doc)
    except Exception as exc:  # noqa: BLE001
        return architecture_result_not_configured(
            f"architecture provenance unavailable for {revision[:12]}: {exc}"
        )


#: Remediation for a not-configured architecture producer. ri-06 rejects *any*
#: non-fresh ``ProducerResult`` that carries no remediation, so this constant is
#: what keeps the degradation path from raising instead of degrading. It mirrors
#: ri-04's own ``_REMEDIATION_REFRESH`` for callers that cannot import it.
_ARCHITECTURE_REMEDIATION = Remediation(
    summary=(
        "Architecture provenance is unavailable; regenerate it with the "
        "refresh-architecture skill."
    ),
    command="make architecture",
)


def _architecture_not_configured_fallback(reason: str) -> ProducerResult:
    """Build a not-configured architecture result without importing ri-04.

    Used only when refresh-architecture (and its result builders) cannot be
    imported at all; the fallback keeps the manifest producer entry honest.

    Both ``remediation`` and ``fallback`` are required: ri-06's
    ``ProducerResult`` rejects a non-fresh result missing either, and this
    builder *is* the graceful-degradation path — raising here would abort the
    whole refresh in exactly the situation it exists to survive.
    """
    return ProducerResult(
        producer_id=ARCHITECTURE_PRODUCER_ID,
        producer_version="unknown",
        status=ProducerStatus.NOT_CONFIGURED,
        remediation=(_ARCHITECTURE_REMEDIATION,),
        fallback=Fallback(kind=FallbackKind.SKIP, reason=reason),
    )


def _deterministic_ids(producer_ids: Sequence[str] | None) -> list[str]:
    """Resolve the deterministic producer ids to run (all configured by default)."""
    all_ids = [spec.producer_id for spec in list_producers()]
    if producer_ids is None:
        return all_ids
    unknown = [pid for pid in producer_ids if pid not in {*all_ids, ARCHITECTURE_PRODUCER_ID}]
    if unknown:
        raise ValueError(f"unknown producer id(s): {', '.join(sorted(unknown))}")
    return [pid for pid in producer_ids if pid != ARCHITECTURE_PRODUCER_ID]


def _collect_results(
    mode: Mode,
    repo_root: Path,
    revision: str,
    producer_ids: Sequence[str] | None,
    architecture: ArchitectureProducer | None,
) -> list[ProducerResult]:
    """Run every configured producer once and return the results in id order.

    Deterministic producers come from the ri-05 registry; the architecture
    producer comes from its seam unless the caller restricted the run to a subset
    that excludes it.
    """
    results: list[ProducerResult] = []
    for pid in _deterministic_ids(producer_ids):
        results.append(run_producer(pid, mode, repo_root, revision))

    wants_architecture = producer_ids is None or ARCHITECTURE_PRODUCER_ID in producer_ids
    if wants_architecture:
        arch = architecture or _default_architecture_producer
        try:
            results.append(arch(repo_root, revision, mode))
        except Exception as exc:  # noqa: BLE001 - an architecture crash degrades
            results.append(
                _architecture_not_configured_fallback(
                    f"architecture producer raised: {exc.__class__.__name__}"
                )
            )
    return sorted(results, key=lambda r: r.producer_id)


def decide_outcome(
    producer_results: Sequence[ProducerResult],
    semantic_index: SemanticIndexReference | None,
) -> tuple[OperationState, SafeError | None]:
    """Map recorded results to one terminal state (design D5), IO-free and total.

    * Any ``failed`` producer → FAILED (with an aggregated bounded error).
    * Else any ``degraded``/``not-configured`` producer, or a non-succeeded
      semantic index → DEGRADED.
    * Else → SUCCEEDED.

    A required producer that is genuinely misconfigured has already been converted
    to ``failed`` by ``registry.run_producer``; a ``not-configured`` result here is
    an optional/absent producer and only degrades.

    ``semantic_index`` is ``None`` when the semantic index is not part of this run
    (a producer-scoped invocation); that never degrades the outcome. A supplied
    reference degrades unless it ``succeeded``.
    """
    failed = [r.producer_id for r in producer_results if r.status is ProducerStatus.FAILED]
    if failed:
        return OperationState.FAILED, SafeError(
            error_class="RefreshProducerFailure",
            summary=f"producers failed: {', '.join(sorted(failed))}",
        )
    degraded = any(
        r.status in (ProducerStatus.DEGRADED, ProducerStatus.NOT_CONFIGURED)
        for r in producer_results
    )
    from models import SemanticIndexStatus

    semantic_ok = (
        semantic_index is None
        or semantic_index.status is SemanticIndexStatus.SUCCEEDED
    )
    if degraded or not semantic_ok:
        return OperationState.DEGRADED, None
    return OperationState.SUCCEEDED, None


def _manifest_present(repo_root: Path, relative_path: str | None, sha256: str | None) -> bool:
    """True when the pointed-to manifest exists **in this worktree** and matches.

    The operation ledger is shared across linked worktrees, but the manifest
    lives in the gitignored ``.git-context/``, which is per-worktree and freely
    cleaned. A ``validated`` pointer is therefore not evidence that the file is
    readable *here*, so the digest is re-checked against the bytes on disk.
    """
    if relative_path is None or sha256 is None:
        return False
    try:
        return sha256_hex((repo_root / relative_path).read_bytes()) == sha256
    except OSError:
        return False


def _reuse_terminal(
    op_store: OperationStore, op, repo_root: Path, manifest_path: str
) -> RefreshResult:
    """Return a terminal operation verbatim, recreating a missing manifest.

    A terminal record is an immutable sink, so a repeat run reuses it — no
    re-attempt, no repository diff. The manifest is re-projected and recorded
    when the pointer is ``absent`` (a crash between ``finalize`` and
    ``record_manifest``) *or* when the pointed-to file is missing or stale in
    this worktree (``.git-context/`` cleaned, or the operation was created from a
    sibling worktree). Otherwise a reuse would report a path that does not exist
    locally. ``project_manifest`` works on any terminal record, so this is safe
    for ``degraded``/``failed`` as well as ``succeeded``.
    """
    needs_manifest = (
        op.manifest.status is ManifestPointerStatus.ABSENT
        or not _manifest_present(repo_root, op.manifest.path, op.manifest.sha256)
    )
    if needs_manifest:
        # Rewrite at the recorded location when there is one, so reuse stays
        # idempotent even if the caller passed a different default.
        target = op.manifest.path or manifest_path
        write_result = write_manifest(op, target, repo_root=repo_root)
        op = op_store.record_manifest(
            op.operation_id,
            path=write_result.path,
            sha256=write_result.sha256,
            status=ManifestPointerStatus.VALIDATED,
        )
    return RefreshResult(
        operation_id=op.operation_id,
        outcome=op.state,
        producer_results=op.producer_results,
        semantic_index=op.semantic_index,
        manifest_path=op.manifest.path,
        manifest_sha256=op.manifest.sha256,
    )


def _record_tolerant(op_store: OperationStore, op, result: ProducerResult):
    """Record a producer result, converging when a concurrent attempt beat us.

    Two processes refreshing one revision race in two distinguishable ways, and
    ``OperationStore`` checks them in this order:

    * the operation already went terminal → ``InvalidTransitionError``;
    * the producer was already recorded while still running →
      ``DuplicateProducerError``.

    Neither is a failure: the other attempt recorded an identical, deterministic
    result for the same revision. Both converge by reloading the persisted
    record. Catching only the duplicate case would crash the slower refresh
    whenever the winner finalized first.
    """
    try:
        return op_store.record_producer_result(op.operation_id, result)
    except (DuplicateProducerError, InvalidTransitionError):
        return op_store.load(op.operation_id)


def generate(
    repository: Path | str,
    *,
    revision: str | None = None,
    producer_ids: Sequence[str] | None = None,
    store: OperationStore | None = None,
    architecture: ArchitectureProducer | None = None,
    semantic_indexer: SemanticIndexer | None = None,
    manifest_path: str = DEFAULT_MANIFEST_PATH,
) -> RefreshResult:
    """Run the full refresh for one revision and emit the durable manifest.

    Idempotent per ``(repository, revision)``. A fully ``succeeded`` operation is
    reused verbatim (no repository diff). A ``degraded``/``failed`` operation is
    *resumed*: already-recorded producer results are immutable for the revision
    (ri-06 is append-only) so they are not re-run, but the mutable semantic index
    is re-attempted, which can lift ``degraded -> succeeded`` once the index is
    available. Deterministic and architecture results are always recorded before
    the semantic index, so a semantic failure never discards deterministic output.

    A *producer-scoped* run (``producer_ids`` given) is a targeted
    regenerate-and-report: it never drives the shared per-revision operation to a
    terminal state (which would poison a later full refresh) and emits no
    aggregate manifest.
    """
    repo_root, repository_id, rev = resolve_repository_identity(repository, revision)

    if producer_ids is not None:
        results = tuple(
            _collect_results("generate", repo_root, rev, producer_ids, architecture)
        )
        outcome, _error = decide_outcome(results, None)
        return RefreshResult(
            operation_id=None, outcome=outcome, producer_results=results
        )

    op_store = store or OperationStore(repo_root)
    op = op_store.create_or_load(repository_id, rev)
    if op.state is OperationState.SUCCEEDED:
        return _reuse_terminal(op_store, op, repo_root, manifest_path)

    try:
        op = op_store.begin_attempt(op.operation_id)
    except InvalidTransitionError:
        # A concurrent attempt finalized ``succeeded`` between load and begin.
        op = op_store.load(op.operation_id)
        if op.state is OperationState.SUCCEEDED:
            return _reuse_terminal(op_store, op, repo_root, manifest_path)
        raise

    # Deterministic + architecture producers are recorded once per revision
    # (append-only). On a resume, sealed producers are NOT re-run — their result
    # is immutable for this revision — so we never regenerate an artifact whose
    # fresh result we would then have to discard.
    recorded_ids = set(op.producer_ids())
    for pid in _deterministic_ids(None):
        if pid in recorded_ids:
            continue
        op = _record_tolerant(op_store, op, run_producer(pid, "generate", repo_root, rev))
    if ARCHITECTURE_PRODUCER_ID not in recorded_ids:
        arch = architecture or _default_architecture_producer
        try:
            arch_result = arch(repo_root, rev, "generate")
        except Exception as exc:  # noqa: BLE001 - an architecture crash degrades
            arch_result = _architecture_not_configured_fallback(
                f"architecture producer raised: {exc.__class__.__name__}"
            )
        op = _record_tolerant(op_store, op, arch_result)

    # A concurrent attempt may have finalized while our producers were running.
    # ri-06 records are immutable once terminal, so converge on what was
    # persisted instead of attempting a second terminal transition.
    if op.state is not OperationState.RUNNING:
        return _reuse_terminal(op_store, op, repo_root, manifest_path)

    # The semantic index is mutable; always (re-)attempt it on a full run so a
    # previously degraded operation can complete when the service returns.
    semantic_ref = resolve_semantic_index(repo_root, rev, indexer=semantic_indexer)
    try:
        op = op_store.record_semantic_index(op.operation_id, semantic_ref)
    except InvalidTransitionError:
        # Lost the race between the producer loop and here.
        return _reuse_terminal(
            op_store, op_store.load(op.operation_id), repo_root, manifest_path
        )

    outcome, error = decide_outcome(op.producer_results, op.semantic_index)
    try:
        op = op_store.finalize(op.operation_id, outcome, error=error)
    except InvalidTransitionError:
        # A concurrent attempt finalized first; converge on the persisted record.
        op = op_store.load(op.operation_id)

    # Always (re-)project the manifest from the terminal record: a resume may have
    # changed the outcome (e.g. degraded -> succeeded once the index returned), so
    # a stale VALIDATED pointer must not be trusted. The write is byte-stable, so
    # an unchanged rerun still produces no repository diff.
    write_result = write_manifest(op, manifest_path, repo_root=repo_root)
    op = op_store.record_manifest(
        op.operation_id,
        path=write_result.path,
        sha256=write_result.sha256,
        status=ManifestPointerStatus.VALIDATED,
    )

    return RefreshResult(
        operation_id=op.operation_id,
        outcome=op.state,
        producer_results=op.producer_results,
        semantic_index=op.semantic_index,
        manifest_path=write_result.path,
        manifest_sha256=write_result.sha256,
    )


def check(
    repository: Path | str,
    *,
    revision: str | None = None,
    producer_ids: Sequence[str] | None = None,
    architecture: ArchitectureProducer | None = None,
    semantic_indexer: SemanticIndexer | None = None,
) -> RefreshResult:
    """Read-only drift assessment: run every producer in ``check`` mode.

    Writes neither the durable store nor the working tree. This is a
    *deterministic-drift* assessment: it does not attempt the semantic index (an
    environmental service whose availability is not deterministic drift), so
    ``refresh-project-context-check`` exits 0 (fresh) / 2 (drift) / 1 (failed) as
    a faithful drift signal for the ri-10 gate. ``semantic_indexer`` is accepted
    for signature symmetry with :func:`generate` but is intentionally unused here.
    """
    _ = semantic_indexer
    repo_root, _repository_id, rev = resolve_repository_identity(repository, revision)
    results = tuple(
        _collect_results("check", repo_root, rev, producer_ids, architecture)
    )
    outcome, _error = decide_outcome(results, None)
    return RefreshResult(
        operation_id=None,
        outcome=outcome,
        producer_results=results,
        semantic_index=None,
    )


__all__ = [
    "DEFAULT_MANIFEST_PATH",
    "ARCHITECTURE_PRODUCER_ID",
    "ArchitectureProducer",
    "RefreshResult",
    "RevisionMismatchError",
    "resolve_repository_identity",
    "decide_outcome",
    "generate",
    "check",
]

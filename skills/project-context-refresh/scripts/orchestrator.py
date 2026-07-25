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

import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

# Importing _runtime first inserts the ri-06 runtime scripts dir onto sys.path,
# so the bare ``store``/``manifest``/``models`` imports below resolve.
from _runtime import (
    ProducerResult,
    ProducerStatus,
    SafeError,
    ensure_git_revision,
)
from manifest import write_manifest
from models import (
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


def resolve_repository_identity(
    repository: Path | str, revision: str | None
) -> tuple[Path, str, str]:
    """Return ``(repo_root, repository_id, full_revision)``.

    ``repository_id`` is the repository directory name (matching ri-04's
    convention so the architecture producer shares the same operation), and the
    revision is the full HEAD SHA unless one is supplied.
    """
    repo_root = Path(repository).resolve()
    toplevel = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    repo_root = Path(toplevel) if toplevel else repo_root
    repository_id = repo_root.name

    rev = revision
    if not rev:
        rev = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
    if not rev:
        raise ValueError("could not resolve HEAD; pass an explicit full-SHA revision")
    ensure_git_revision(rev)
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


def _architecture_not_configured_fallback(reason: str) -> ProducerResult:
    """Build a not-configured architecture result without importing ri-04.

    Used only when refresh-architecture (and its result builders) cannot be
    imported at all; the fallback keeps the manifest producer entry honest.
    """
    from _runtime import Fallback, FallbackKind

    return ProducerResult(
        producer_id=ARCHITECTURE_PRODUCER_ID,
        producer_version="unknown",
        status=ProducerStatus.NOT_CONFIGURED,
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

    Idempotent per ``(repository, revision)``: reuses the canonical operation and,
    because every producer is byte-stable, produces no repository diff on a repeat
    run. Deterministic and architecture results are recorded before the semantic
    index is attempted, so a semantic failure degrades the outcome without
    discarding any deterministic output.
    """
    repo_root, repository_id, rev = resolve_repository_identity(repository, revision)
    op_store = store or OperationStore(repo_root)

    op = op_store.create_or_load(repository_id, rev)
    if op.state is OperationState.SUCCEEDED:
        # A fully-successful refresh for this revision is immutable (the store
        # makes ``succeeded`` a terminal sink). A repeat run reuses it verbatim —
        # no re-attempt, no rewrite, no repository diff (design D2/D6).
        return RefreshResult(
            operation_id=op.operation_id,
            outcome=op.state,
            producer_results=op.producer_results,
            semantic_index=op.semantic_index,
            manifest_path=op.manifest.path,
            manifest_sha256=op.manifest.sha256,
        )
    op = op_store.begin_attempt(op.operation_id)

    results = _collect_results("generate", repo_root, rev, producer_ids, architecture)
    recorded_ids = set(op.producer_ids())
    for result in results:
        if result.producer_id in recorded_ids:
            continue  # idempotent reuse: already recorded on this operation
        op = op_store.record_producer_result(op.operation_id, result)
        recorded_ids.add(result.producer_id)

    # Semantic index is attempted last, and only on a full run; failure never
    # discards the results above. A producer-scoped run leaves the existing
    # semantic reference untouched.
    semantic_for_outcome: SemanticIndexReference | None = None
    if producer_ids is None:
        semantic_ref = resolve_semantic_index(repo_root, rev, indexer=semantic_indexer)
        op = op_store.record_semantic_index(op.operation_id, semantic_ref)
        semantic_for_outcome = op.semantic_index

    outcome, error = decide_outcome(op.producer_results, semantic_for_outcome)
    op = op_store.finalize(op.operation_id, outcome, error=error)

    write_result = write_manifest(op, manifest_path, repo_root=repo_root)
    op_store.record_manifest(
        op.operation_id,
        path=write_result.path,
        sha256=write_result.sha256,
        status=ManifestPointerStatus.VALIDATED,
    )

    return RefreshResult(
        operation_id=op.operation_id,
        outcome=outcome,
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
    "resolve_repository_identity",
    "decide_outcome",
    "generate",
    "check",
]

"""Branch-local context checkpoint (ri-09).

A checkpoint is a read-only, scope-restricted, per-work-package report of the
project context a feature branch has invalidated. It composes machinery that
already exists — the ri-08 context-impact detector, the ri-05 producer registry,
the ri-04 architecture provenance, and the ri-06 value objects — and adds only
report assembly.

**D1 is the load-bearing decision and it is a prohibition.** This module does not
construct an ``OperationStore``, does not create, record into, or finalize a
refresh operation, and does not emit a refresh manifest. ri-07 D9 makes a
recorded producer result immutable for its revision and reuses it verbatim in
later refreshes; a checkpoint result is scope-restricted and feature-namespaced,
so admitting one into the shared ledger would be unrecoverable *by design*
rather than by accident — nothing in the ri-06 contract can distinguish or
supersede it. ``checkout_policy`` cannot catch that mistake because it reasons
about the worktree path only, while the ledger lives in the clone-global git
common directory (D10), so the invariant is asserted here and pinned by
``test_checkpoint_isolation.py``.

What this module owns:

* :func:`should_checkpoint` — the trigger decision ``implement-feature``
  consumes, keyed on the ri-08 status of the package's own changed-file list
  (D2). ``unmigrated`` (no ``context_impact`` block) is reported as itself and
  never collapsed into "no impact": absence of evidence is not an assertion.
* :func:`run_checkpoint` — dispatch every configured producer through
  ``registry.run_producer`` in ``check`` mode only (D3), collect architecture
  freshness and delta as *separate* findings (D6), attempt the degradable
  semantic index in a ``work_package`` namespace (D4/D5/D9), and write one
  byte-stable report (D7).

The report never fails the run: drift is data, and turning it into a build
failure belongs to the drift-gate capability (D8). The single non-zero outcome
is being unable to produce a valid report at all, which surfaces as
:class:`CheckpointError`.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Importing _runtime first inserts the ri-06 runtime scripts dir onto sys.path,
# so the bare ``models``/``atomic`` imports below resolve. Only ri-06 *types* and
# pure serialization helpers are used — never its durable-store writers (D1).
from _runtime import (
    Fallback,
    FallbackKind,
    ProducerResult,
    ProducerStatus,
    canonical_json_bytes,
    ensure_git_revision,
)
from atomic import atomic_write_bytes
from models import SemanticIndexReference, SemanticIndexStatus
from registry import Mode, list_producers, run_producer
from semantic_adapter import (
    IndexNamespace,
    ReadScope,
    SemanticIndexer,
    default_semantic_indexer,
    resolve_semantic_index,
)

# ri-08 lives in ``validate-packages``. Its detector layer is deliberately
# git-free, which is exactly why a checkpoint can reuse it against an
# uncommitted worktree's changed-file list instead of a git range (D2).
_VALIDATE_PACKAGES_SCRIPTS = (
    Path(__file__).resolve().parents[2] / "validate-packages" / "scripts"
)
if _VALIDATE_PACKAGES_SCRIPTS.is_dir() and str(_VALIDATE_PACKAGES_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_VALIDATE_PACKAGES_SCRIPTS))

from context_impact import (  # noqa: E402
    SURFACES,
    ImpactRules,
    IndexScopes,
    index_scopes,
    load_rules,
)
from validate_context_impact import FAILING_STATUSES, evaluate  # noqa: E402

#: Contract version of the emitted report. Pinned by the schema's ``const``.
CHECKPOINT_SCHEMA_VERSION = 1

#: Change-local, version-controlled report location (D7). Tracked because the
#: stated purpose is review context and a reviewer reads the PR diff.
REPORT_SUBDIR = "context-checkpoints"

#: The committed architecture graph the merge-base delta is computed against.
ARCHITECTURE_GRAPH_PATH = "docs/architecture-analysis/architecture.graph.json"

#: Default baseline for the architecture delta.
DEFAULT_INTEGRATION_BRANCH = "main"

FRESHNESS_FRESH = "fresh"
FRESHNESS_STALE = "stale"
FRESHNESS_UNKNOWN = "unknown"
_FRESHNESS_VALUES = (FRESHNESS_FRESH, FRESHNESS_STALE, FRESHNESS_UNKNOWN)

CHECKPOINT_SUCCEEDED = "succeeded"
CHECKPOINT_DEGRADED = "degraded"

#: The ri-08 status meaning "this package predates the ``context_impact`` field".
UNMIGRATED = "unmigrated"

#: Surfaces whose invalidation warrants a checkpoint. Every surface ri-08 knows
#: about is a project-context surface, so this is the full set — but it is named
#: rather than inlined so that adding a surface to ri-08 without deciding
#: whether it triggers a checkpoint is a test failure, not a silent gap.
CONTEXT_INVALIDATING_SURFACES: frozenset[str] = frozenset(SURFACES)

_MAX_REASON = 300
_CHANGE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,127}$")
_PACKAGE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

#: The ri-05 dispatch seam: ``(producer_id, mode, repository, revision)``.
ProducerRunner = Callable[[str, Mode, Path, str], ProducerResult]
#: The indexer factory seam, matching ``default_semantic_indexer``'s keywords.
IndexerFactory = Callable[..., SemanticIndexer | None]


class CheckpointError(Exception):
    """A checkpoint could not produce a valid report.

    This is the *only* failure a checkpoint has (D8). Deterministic drift, a
    stale architecture artifact, and an unavailable semantic index are all
    recorded in the report and exit 0.
    """


# --------------------------------------------------------------------------- #
# D2 — the trigger decision
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class CheckpointDecision:
    """Whether a package warrants a checkpoint, and why.

    ``status`` is the ri-08 verdict verbatim. ``unmigrated`` and an explicit
    empty ``surfaces`` list both yield ``should_run=False`` but are deliberately
    distinguishable: the first is absence of evidence (the package declares no
    ``context_impact`` block at all), the second is an assertion of no impact
    that the ri-08 gate checks strictly. Collapsing them would let an unmigrated
    package look verified.
    """

    should_run: bool
    status: str
    surfaces: tuple[str, ...]
    reason: str

    @property
    def is_unmigrated(self) -> bool:
        return self.status == UNMIGRATED

    @property
    def is_blocking(self) -> bool:
        """Whether the ri-08 gate fails this package outright."""
        return self.status in FAILING_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_run": self.should_run,
            "status": self.status,
            "surfaces": list(self.surfaces),
            "reason": self.reason,
        }


def should_checkpoint(
    package: Mapping[str, Any],
    changed_files: Sequence[str],
    *,
    rules: ImpactRules | None = None,
) -> CheckpointDecision:
    """Decide whether *package* warrants a checkpoint for its *changed_files*.

    Evaluation runs through ri-08's ``evaluate``, so the status semantics have
    exactly one definition in the system. The file list is supplied by the
    caller and never derived from a git range: the decision must work on an
    uncommitted worktree (D2).
    """
    impact_rules = rules if rules is not None else load_rules()
    result = evaluate(package, list(changed_files), impact_rules)
    inferred = tuple(sorted(result.implied))

    if result.status == UNMIGRATED:
        return CheckpointDecision(
            should_run=False,
            status=UNMIGRATED,
            surfaces=inferred,
            reason=(
                "package declares no context_impact block; ri-08 reports "
                "'unmigrated', which is absence of evidence and must not be "
                "reported as impact-free"
            ),
        )

    if result.status in FAILING_STATUSES:
        return CheckpointDecision(
            should_run=False,
            status=result.status,
            surfaces=inferred,
            reason=(
                f"the ri-08 context-impact gate fails this package with "
                f"{result.status!r}; that blocks before a checkpoint runs"
            ),
        )

    declared = tuple(result.declared or ())
    surfaces = tuple(
        sorted(
            surface
            for surface in set(declared) | set(inferred)
            if surface in CONTEXT_INVALIDATING_SURFACES
        )
    )
    if not surfaces:
        return CheckpointDecision(
            should_run=False,
            status=result.status,
            surfaces=(),
            reason=(
                "package asserts an empty context_impact surface list and its "
                "changed files imply none; that is an assertion of no impact"
            ),
        )
    return CheckpointDecision(
        should_run=True,
        status=result.status,
        surfaces=surfaces,
        reason=f"package invalidates: {', '.join(surfaces)}",
    )


# --------------------------------------------------------------------------- #
# D6 — architecture freshness and delta are distinct findings
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ArchitectureFinding:
    """Freshness and delta for the branch's architecture artifact.

    ``delta_authoritative`` is *derived*, never supplied. A delta computed from
    a stale or unreadable artifact can be empty or actively misleading, so the
    one value that must never be wrong is the one nobody gets to set. The report
    schema encodes the same rule as an ``if``/``then``, so a wrong value would
    also fail validation.
    """

    freshness: str
    changed_nodes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.freshness not in _FRESHNESS_VALUES:
            raise ValueError(
                f"architecture freshness must be one of {_FRESHNESS_VALUES!r}, "
                f"got {self.freshness!r}"
            )
        object.__setattr__(
            self, "changed_nodes", tuple(sorted(set(self.changed_nodes)))
        )

    @property
    def delta_authoritative(self) -> bool:
        return self.freshness == FRESHNESS_FRESH

    def to_dict(self) -> dict[str, Any]:
        return {
            "freshness": self.freshness,
            "delta_authoritative": self.delta_authoritative,
            "changed_nodes": list(self.changed_nodes),
        }


#: An architecture seam: ``(repository, merge_base) -> ArchitectureFinding``.
ArchitectureResolver = Callable[[Path, str | None], ArchitectureFinding]


def _architecture_scripts_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "refresh-architecture" / "scripts"


def _ensure_architecture_on_path() -> bool:
    scripts = _architecture_scripts_dir()
    if not scripts.is_dir():
        return False
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    return True


def architecture_freshness(repository: Path) -> str:
    """Provenance-based, mtime-independent freshness of the architecture artifact.

    Delegates to ``arch_utils.provenance.check_freshness`` — the exact function
    ``run_architecture.py --check`` calls, minus a subprocess and a JSON round
    trip that would discard the ``stale`` / ``invalid`` distinction. ri-04's
    ``invalid`` (no or unparseable provenance) maps to ``unknown``: we cannot say
    the artifact is stale, only that we cannot vouch for it.
    """
    if not _ensure_architecture_on_path():
        return FRESHNESS_UNKNOWN
    try:
        from arch_utils.provenance import check_freshness  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - an absent owner is unknown, never fatal
        return FRESHNESS_UNKNOWN
    try:
        result = check_freshness(Path(repository))
    except Exception:  # noqa: BLE001
        return FRESHNESS_UNKNOWN
    if result.is_fresh:
        return FRESHNESS_FRESH
    return FRESHNESS_STALE if result.status == FRESHNESS_STALE else FRESHNESS_UNKNOWN


def architecture_changed_nodes(repository: Path, merge_base: str | None) -> tuple[str, ...]:
    """Architecture nodes differing from the merge-base graph.

    Uses ``diff_architecture.diff_graphs`` — the standalone graph differ ri-04
    already ships — against the *committed* baseline read out of git, so the
    comparison is revision-pinned rather than dependent on a working-tree file.
    Every failure to resolve either side yields an empty delta; the caller pairs
    it with a non-fresh freshness value, which marks it non-authoritative.
    """
    if not merge_base:
        return ()
    current_path = Path(repository) / ARCHITECTURE_GRAPH_PATH
    if not current_path.is_file():
        return ()
    baseline_raw = _git_out(repository, "show", f"{merge_base}:{ARCHITECTURE_GRAPH_PATH}")
    if not baseline_raw:
        return ()
    if not _ensure_architecture_on_path():
        return ()
    try:
        from diff_architecture import diff_graphs  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return ()
    try:
        baseline = json.loads(baseline_raw)
        current = json.loads(current_path.read_text(encoding="utf-8"))
        report = diff_graphs(baseline, current)
    except Exception:  # noqa: BLE001 - an unreadable graph is an empty delta
        return ()
    details = report.get("details", {}) if isinstance(report, Mapping) else {}
    added = details.get("added_nodes") or []
    removed = details.get("removed_nodes") or []
    return tuple(sorted({str(node) for node in (*added, *removed)}))


def resolve_architecture(repository: Path, merge_base: str | None) -> ArchitectureFinding:
    """Collect both architecture findings, keeping them independent (D6)."""
    return ArchitectureFinding(
        freshness=architecture_freshness(repository),
        changed_nodes=architecture_changed_nodes(repository, merge_base),
    )


# --------------------------------------------------------------------------- #
# Git helpers (read-only)
# --------------------------------------------------------------------------- #
def _git_out(repository: Path, *args: str) -> str:
    """Run a read-only git command; return stripped stdout, "" on any failure."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def resolve_merge_base(
    repository: Path,
    *,
    integration_branch: str = DEFAULT_INTEGRATION_BRANCH,
    revision: str = "HEAD",
) -> str | None:
    """The merge base against the integration branch, or ``None`` when unresolvable.

    ``None`` is a first-class answer: a detached fixture repository or a branch
    with no common ancestor has no baseline, and the report simply omits
    ``merge_base_revision`` rather than inventing one.
    """
    out = _git_out(repository, "merge-base", integration_branch, revision)
    return out if _FULL_SHA.match(out) else None


# --------------------------------------------------------------------------- #
# D9 — the degradable semantic index
# --------------------------------------------------------------------------- #
def _bounded_reason(exc: BaseException) -> str:
    summary = str(exc).strip() or exc.__class__.__name__
    text = f"Semantic index unavailable ({exc.__class__.__name__}): {summary}"
    return text if len(text) <= _MAX_REASON else text[: _MAX_REASON - 3] + "..."


def _index_failed(revision: str, reason: str) -> SemanticIndexReference:
    return SemanticIndexReference(
        status=SemanticIndexStatus.FAILED,
        requested_revision=revision,
        fallback=Fallback(kind=FallbackKind.EXACT_SEARCH, reason=reason),
    )


def _resolve_index(
    repository: Path,
    revision: str,
    namespace: IndexNamespace,
    scopes: IndexScopes,
    factory: IndexerFactory | None,
) -> SemanticIndexReference:
    """Attempt the branch-local index; every failure degrades, none propagates."""
    try:
        scope = ReadScope.from_index_scopes(scopes)
    except ValueError as exc:
        # A scope whose deny cancels every read-allow glob cannot be expressed
        # without widening it downstream, where an empty read_allow means "no
        # restriction". Degrading the index is correct; silently indexing the
        # whole repository for this package would not be.
        return _index_failed(revision, _bounded_reason(exc))

    build = factory or default_semantic_indexer
    try:
        indexer = build(namespace=namespace, scope=scope)
    except Exception as exc:  # noqa: BLE001
        return _index_failed(revision, _bounded_reason(exc))
    return resolve_semantic_index(repository, revision, indexer=indexer)


# --------------------------------------------------------------------------- #
# Report assembly
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class CheckpointResult:
    """A produced checkpoint: the report, where it landed, and whether it moved."""

    report: Mapping[str, Any]
    report_path: str
    changed: bool
    decision: CheckpointDecision

    @property
    def checkpoint_status(self) -> str:
        return str(self.report["checkpoint_status"])

    def exit_code(self) -> int:
        """Always 0. A produced report is a success, drift included (D8)."""
        return 0


def report_relative_path(change_id: str, package_id: str) -> str:
    return f"openspec/changes/{change_id}/{REPORT_SUBDIR}/{package_id}.json"


def work_packages_path(repository: Path, change_id: str) -> Path:
    return Path(repository) / "openspec" / "changes" / change_id / "work-packages.yaml"


def load_package(repository: Path, change_id: str, package_id: str) -> Mapping[str, Any]:
    """Read one package out of the change's ``work-packages.yaml``.

    Fails closed: a missing file or an unknown package id is a caller error, not
    an empty package that would silently checkpoint nothing.
    """
    import yaml

    path = work_packages_path(repository, change_id)
    if not path.is_file():
        raise CheckpointError(f"no work-packages.yaml for change {change_id!r}: {path}")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise CheckpointError(f"{path}: invalid YAML: {exc}") from exc
    for package in document.get("packages") or ():
        if isinstance(package, Mapping) and package.get("package_id") == package_id:
            return package
    raise CheckpointError(f"package {package_id!r} not found in {path}")


def _ensure_identifier(value: str, pattern: re.Pattern[str], label: str) -> str:
    if not pattern.match(value):
        raise CheckpointError(f"invalid {label}: {value!r}")
    return value


def _checkpoint_status(
    producer_results: Sequence[ProducerResult], index: SemanticIndexReference
) -> str:
    """Terminal state of the checkpoint's own apparatus.

    Deterministic *drift* — a producer reporting ``degraded`` because its managed
    output would change — is the checkpoint working, so it stays ``succeeded``
    (D8). ``degraded`` is reserved for a part of the checkpoint that could not
    run: a producer that failed or is not configured, or an index that did not
    succeed.
    """
    apparatus_broken = any(
        result.status in (ProducerStatus.FAILED, ProducerStatus.NOT_CONFIGURED)
        for result in producer_results
    )
    if apparatus_broken or index.status is not SemanticIndexStatus.SUCCEEDED:
        return CHECKPOINT_DEGRADED
    return CHECKPOINT_SUCCEEDED


def run_checkpoint(
    repository: Path | str,
    *,
    change_id: str,
    package_id: str,
    package: Mapping[str, Any],
    changed_files: Sequence[str],
    revision: str,
    merge_base: str | None = None,
    rules: ImpactRules | None = None,
    producer_ids: Sequence[str] | None = None,
    producer_runner: ProducerRunner | None = None,
    architecture: ArchitectureResolver | None = None,
    indexer_factory: IndexerFactory | None = None,
    write: bool = True,
) -> CheckpointResult:
    """Produce one branch-local checkpoint report for one work package.

    Read-only against the working tree apart from the report itself: producers
    run in ``check`` mode only (D3) and no durable refresh state is touched (D1).

    Raises :class:`CheckpointError` when no valid report could be produced —
    including when the ri-08 gate blocks the package, because a report carrying
    ``undeclared`` or ``spurious_rationale`` would be self-contradictory (those
    statuses fail before a checkpoint is reached, and the report schema has no
    member for them).
    """
    repo_root = Path(repository).resolve()
    _ensure_identifier(change_id, _CHANGE_ID_PATTERN, "change id")
    _ensure_identifier(package_id, _PACKAGE_ID_PATTERN, "package id")
    try:
        ensure_git_revision(revision)
    except Exception as exc:  # noqa: BLE001 - re-raised as the module's own error
        raise CheckpointError(f"invalid source revision: {exc}") from exc
    if merge_base is not None and not _FULL_SHA.match(merge_base):
        raise CheckpointError(f"invalid merge-base revision: {merge_base!r}")

    decision = should_checkpoint(package, changed_files, rules=rules)
    if decision.is_blocking:
        raise CheckpointError(decision.reason)

    namespace = IndexNamespace.for_work_package(change_id, package_id)
    if namespace.is_canonical:  # pragma: no cover - structurally unreachable (D4)
        raise CheckpointError("a checkpoint may never target the canonical namespace")

    # D3: `check`, hardcoded. A generate producer has a write path into docs/,
    # docs/decisions/, and openspec/specs/; a check producer does not, which is
    # what makes "tracked outputs are unchanged" true by construction.
    run = producer_runner or run_producer
    ids = (
        list(producer_ids)
        if producer_ids is not None
        else [spec.producer_id for spec in list_producers()]
    )
    producer_results = sorted(
        (run(pid, "check", repo_root, revision) for pid in ids),
        key=lambda result: result.producer_id,
    )

    resolver = architecture or resolve_architecture
    try:
        finding = resolver(repo_root, merge_base)
    except Exception:  # noqa: BLE001 - architecture is a finding, not a gate
        finding = ArchitectureFinding(freshness=FRESHNESS_UNKNOWN)

    scopes = index_scopes(package)
    index = _resolve_index(repo_root, revision, namespace, scopes, indexer_factory)

    report: dict[str, Any] = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "change_id": change_id,
        "package_id": package_id,
        "source_revision": revision,
        "namespace": {"kind": namespace.kind, "key": namespace.key},
        "scope": {
            "read_allow": list(scopes.read_allow),
            "deny": list(scopes.deny),
        },
        "context_impact": {
            "status": decision.status,
            "surfaces": list(decision.surfaces),
        },
        "producer_results": [result.to_dict() for result in producer_results],
        "architecture": finding.to_dict(),
        "semantic_index": index.to_dict(),
        "checkpoint_status": _checkpoint_status(producer_results, index),
    }
    if merge_base:
        report["merge_base_revision"] = merge_base

    relative = report_relative_path(change_id, package_id)
    changed = False
    if write:
        changed = atomic_write_bytes(repo_root / relative, canonical_json_bytes(report))
    return CheckpointResult(
        report=report, report_path=relative, changed=changed, decision=decision
    )


__all__ = [
    "ARCHITECTURE_GRAPH_PATH",
    "CHECKPOINT_DEGRADED",
    "CHECKPOINT_SCHEMA_VERSION",
    "CHECKPOINT_SUCCEEDED",
    "CONTEXT_INVALIDATING_SURFACES",
    "DEFAULT_INTEGRATION_BRANCH",
    "FRESHNESS_FRESH",
    "FRESHNESS_STALE",
    "FRESHNESS_UNKNOWN",
    "REPORT_SUBDIR",
    "UNMIGRATED",
    "ArchitectureFinding",
    "ArchitectureResolver",
    "CheckpointDecision",
    "CheckpointError",
    "CheckpointResult",
    "IndexerFactory",
    "ProducerRunner",
    "architecture_changed_nodes",
    "architecture_freshness",
    "load_package",
    "report_relative_path",
    "resolve_architecture",
    "resolve_merge_base",
    "run_checkpoint",
    "should_checkpoint",
    "work_packages_path",
]

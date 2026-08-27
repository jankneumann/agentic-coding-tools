"""Main context convergence driver (ri-11).

``merge-pull-requests`` is the only skill that writes ``main``; every other skill
lands through a pull request from a managed worktree. That makes it the
authoritative main-synchronization point, and this module is the one place that
turns a completed merge pass into a converged main state: regenerated
deterministic context, one follow-up commit, one push, one enqueued semantic
index, and one tracked record of all of it.

Boundary (design D1). This is **not** a hook of ``post_merge_pipeline``. That
pipeline is deliberately per-PR and failure-isolated, so putting convergence
there would produce N convergences, N commits, and N index requests for N merged
PRs. Convergence fires **once per invocation pass** (Step 11.6), after the
per-PR loop has drained and after post-merge OpenSpec cleanup has staged its
output. ``k = 0`` merged PRs converge nothing at all: that pass was a read of
main, not a write.

Four invariants, in the order they matter:

1. **A refresh failure never un-merges and never blocks the merge** (D6).
   Convergence is strictly downstream of the merge commit. This module cannot
   revert, close, or reopen a pull request, and that is enforced at runtime by
   :func:`reverses_merge`, which every issued command passes through -- not by a
   comment claiming it is so.
2. **Idempotence is two-source** (D4). A retry detects a prior convergence from
   the terminal ri-06 operation record *or* from the ``Context-Refresh-Operation``
   commit trailer. Either alone is sufficient to skip; neither alone is
   sufficient as the only check, because the record is lost on a fresh clone and
   the trailer does not exist until the commit lands.
3. **Never fail open.** Unknown or unreachable state is degraded or blocked,
   never silent success. A run that could consult neither idempotence source
   reports ``inconclusive`` and refuses to converge, rather than assuming it is
   the first.
4. **Safe defaults.** Every seam defaults to the real thing, and every new
   behaviour is opt-in at the call site.

Self-reference, stated rather than hidden. A commit cannot contain its own SHA,
so the record that lands *inside* the convergence commit necessarily carries
``convergence_commit: null`` and the deferred (``pending``) semantic reference
that the refresh actually recorded. That in-flight shape is exactly what the
published schema anticipates. The *completed* record -- convergence commit SHA
plus the index enqueued for that final pushed revision -- is returned on
:class:`ConvergenceResult` for the pass summary and the merge log. Amending the
commit to close the loop was rejected: an amend after a partial failure silently
rewrites cleanup work that succeeded, and a second commit would make the pass
produce N+1 commits.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

# ri-06 owns every durable model and the operation ledger. Import it by adding
# the runtime's flat ``scripts`` directory, matching the shared-runtime
# convention used across the skills tree.
_SKILLS_DIR = Path(__file__).resolve().parents[2]
for _extra in (
    _SKILLS_DIR / "project-context-runtime" / "scripts",
    _SKILLS_DIR / "shared",
):
    if _extra.is_dir() and str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from models import (  # noqa: E402
    OperationState,
    derive_operation_id,
    ensure_git_revision,
)

#: Trailer that pins a convergence commit to its durable operation identity.
#: One of the two idempotence sources (D4); the one that survives a fresh clone.
CONVERGENCE_TRAILER = "Context-Refresh-Operation"

#: Tracked, append-only record location. The ri-07 manifest itself stays
#: gitignored on purpose (a repeat refresh at one revision must produce no
#: repository diff); this record pins it by digest instead (D9).
CONVERGENCE_RECORD_PATH = "docs/merge-logs/context-convergence.jsonl"

#: Coordinator lock key for the whole of Step 11.6 (guard layer 2, D5).
COORDINATOR_LOCK_KEY = "sync-point:main-convergence"

SOURCE_OPERATION_RECORD = "operation-record"
SOURCE_COMMIT_TRAILER = "commit-trailer"

#: Operation states that mean "this SHA already converged". ``failed`` is
#: deliberately excluded: D6 leaves a failed convergence *resumable*, so reading
#: it as done would strand the tree with no step that would ever fix it.
_CONVERGED_STATES = frozenset({OperationState.SUCCEEDED, OperationState.DEGRADED})

_RECORD_FILENAME = "operation.json"


# --------------------------------------------------------------------------- #
# Command seam
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class CommandResult:
    """Outcome of one issued command. Never raises on a non-zero exit."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


#: ``(argv, cwd) -> CommandResult``. Tests substitute a recording double; the
#: production default is :func:`run_command`.
CommandRunner = Callable[[Sequence[str], Path], CommandResult]


def run_command(argv: Sequence[str], cwd: Path) -> CommandResult:
    """Run *argv* in *cwd*, capturing output and never raising on exit status."""
    completed = subprocess.run(
        list(argv),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return CommandResult(
        argv=tuple(argv),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


class ConvergenceApparatusError(RuntimeError):
    """The convergence apparatus could not run. Never a merge failure."""


class MergeReversalError(ConvergenceApparatusError):
    """A command would have un-merged, closed, reopened, or force-pushed.

    Raised *instead of* running it. D6's hardest constraint is structural here:
    the driver is physically unable to issue such a command, so no future edit
    can quietly reintroduce one behind a passing test suite.
    """


#: Command shapes this module must never issue, as ordered argv subsequences.
#: A merge is terminal: convergence is downstream of it and owns no authority
#: over it. Force-pushing is listed for the same reason -- at a sync point,
#: losing a race is information, not an obstacle (D5).
FORBIDDEN_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("gh", "pr", "close"),
    ("gh", "pr", "reopen"),
    ("gh", "pr", "merge"),
    ("gh", "pr", "edit"),
    ("git", "revert"),
    ("git", "reset", "--hard"),
)

#: Flags this module must never pass, wherever they appear.
FORBIDDEN_FLAGS: frozenset[str] = frozenset(
    {"--force", "-f", "--force-with-lease", "--force-if-includes"}
)


def reverses_merge(argv: Sequence[str]) -> bool:
    """Return whether *argv* would un-merge, re-open, or overwrite shared history.

    Checked before dispatch on every command the driver issues, so "convergence
    never reverts a merge" is a property of the apparatus rather than a claim
    about it.
    """
    parts = [str(part) for part in argv]
    if any(part in FORBIDDEN_FLAGS for part in parts):
        return True
    for forbidden in FORBIDDEN_COMMANDS:
        window = len(forbidden)
        for start in range(len(parts) - window + 1):
            if tuple(parts[start : start + window]) == forbidden:
                return True
    return False


def guarded_runner(runner: CommandRunner) -> CommandRunner:
    """Wrap *runner* so a merge-reversing command raises instead of running."""

    def _guarded(argv: Sequence[str], cwd: Path) -> CommandResult:
        if reverses_merge(argv):
            raise MergeReversalError(
                "refusing to issue a merge-reversing or history-overwriting "
                f"command from the convergence driver: {' '.join(str(a) for a in argv)}"
            )
        return runner(argv, cwd)

    return _guarded


# --------------------------------------------------------------------------- #
# Durable identity (D4)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ConvergenceIdentity:
    """The durable identity of one convergence, keyed on the merged main SHA."""

    repository_id: str
    merged_revision: str
    operation_id: str


def _git_stdout(runner: CommandRunner, repository: Path, *args: str) -> str:
    """Return stripped stdout of a read-only git command, or "" when unknown.

    The return-code check is load-bearing: in a repository with no commits
    ``git rev-parse HEAD`` echoes the literal string ``HEAD`` and exits 128, so
    trusting stdout alone would report ``HEAD`` as a revision.
    """
    try:
        result = runner(["git", *args], repository)
    except OSError:
        return ""
    return result.stdout.strip() if result.ok else ""


def resolve_repository_id(
    repository: Path | str,
    *,
    environ: Mapping[str, str] | None = None,
    runner: CommandRunner = run_command,
) -> str:
    """Return the repository identity used to key the operation ledger.

    Honors ``PROJECT_CONTEXT_REPO_ID`` and otherwise falls back to the
    repository directory name -- byte-for-byte the rule
    ``orchestrator.resolve_repository_identity`` uses. The two must agree, or one
    clone would yield two operation ids, split the ledger, and hide a prior
    convergence from the retry that is looking for it.
    """
    root = Path(repository).resolve()
    toplevel = _git_stdout(runner, root, "rev-parse", "--show-toplevel")
    if toplevel:
        root = Path(toplevel)
    env = os.environ if environ is None else environ
    return env.get("PROJECT_CONTEXT_REPO_ID") or root.name


def derive_convergence_identity(
    repository: Path | str,
    *,
    merged_revision: str | None = None,
    environ: Mapping[str, str] | None = None,
    runner: CommandRunner = run_command,
) -> ConvergenceIdentity:
    """Derive the durable identity for the merged main state.

    *merged_revision* is main's HEAD after every merge in the pass and before the
    convergence commit -- the exact revision the deterministic producers read.
    Keying on the set of merged PR numbers was rejected: a retry after a partial
    pass merges a different set and would mint a new identity for the same tree.
    A per-invocation UUID was rejected outright; it defeats resume, which is the
    duplicate-commit failure this exists to prevent.
    """
    root = Path(repository).resolve()
    repository_id = resolve_repository_id(root, environ=environ, runner=runner)
    revision = merged_revision or _git_stdout(runner, root, "rev-parse", "HEAD")
    if not revision:
        raise ConvergenceApparatusError(
            "could not resolve main's HEAD; pass an explicit full-SHA merged revision"
        )
    ensure_git_revision(revision)
    return ConvergenceIdentity(
        repository_id=repository_id,
        merged_revision=revision,
        operation_id=derive_operation_id(repository_id, revision),
    )


# --------------------------------------------------------------------------- #
# Two-source idempotence (D4)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class PriorConvergence:
    """Whether this merged main state already converged, and how we know."""

    found: bool
    sources: tuple[str, ...] = ()
    unreadable: tuple[str, ...] = ()
    convergence_commit: str | None = None

    @property
    def conclusive(self) -> bool:
        """True when the answer can be relied on.

        A negative answer is only trustworthy if *every* source was actually
        consulted. Two unreadable sources and no evidence is not "no prior
        convergence" -- it is "unknown", and unknown must never be spent as
        permission to converge a second time.
        """
        return self.found or not self.unreadable

    def to_dict(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "sources": list(self.sources),
            "unreadable": list(self.unreadable),
            "convergence_commit": self.convergence_commit,
            "conclusive": self.conclusive,
        }


def _operation_record_exists(store: Any, operation_id: str) -> bool:
    """Whether the ledger file for *operation_id* is present on disk.

    ``OperationStore.load`` raises the same typed error for "absent" and for
    "corrupt", and the difference matters: absent is a conclusive negative,
    corrupt is unknown. Anything that prevents the check answers True, so an
    unreadable ledger is treated as present-but-unreadable rather than absent.
    """
    try:
        base = Path(store.base_dir)
    except Exception:  # noqa: BLE001 - unknown location must not read as absent
        return True
    try:
        return (base / operation_id / _RECORD_FILENAME).exists()
    except OSError:
        return True


def find_prior_operation_record(
    identity: ConvergenceIdentity, *, store: Any
) -> tuple[bool, bool]:
    """Return ``(converged, unreadable)`` from the ri-06 durable ledger."""
    try:
        record = store.load(identity.operation_id)
    except Exception:  # noqa: BLE001 - every failure is classified, never raised
        if _operation_record_exists(store, identity.operation_id):
            return False, True
        return False, False
    state = getattr(record, "state", None)
    return state in _CONVERGED_STATES, False


def _trailer_values(message: str, key: str) -> tuple[str, ...]:
    """Extract trailer values for *key* from a commit message body.

    Parsed here rather than delegated to ``git log --format=%(trailers:...)``
    so the check does not vary with the git version in the environment, and so
    the operation id appearing in ordinary prose can never be mistaken for a
    trailer.
    """
    prefix = f"{key}:"
    values: list[str] = []
    for raw in message.splitlines():
        line = raw.strip()
        if line.startswith(prefix):
            values.append(line[len(prefix) :].strip())
    return tuple(values)


def find_prior_commit_trailer(
    repository: Path,
    identity: ConvergenceIdentity,
    *,
    runner: CommandRunner = run_command,
    ref: str = "HEAD",
    max_candidates: int = 20,
) -> tuple[str | None, bool]:
    """Return ``(convergence_commit, unreadable)`` from the commit trailer."""
    needle = f"{CONVERGENCE_TRAILER}: {identity.operation_id}"
    try:
        listing = runner(
            [
                "git",
                "log",
                f"--max-count={max_candidates}",
                "--format=%H",
                "--fixed-strings",
                f"--grep={needle}",
                ref,
            ],
            repository,
        )
    except OSError:
        return None, True
    if not listing.ok:
        return None, True
    for sha in listing.stdout.split():
        try:
            body = runner(["git", "log", "-1", "--format=%B", sha], repository)
        except OSError:
            return None, True
        if not body.ok:
            return None, True
        if identity.operation_id in _trailer_values(body.stdout, CONVERGENCE_TRAILER):
            return sha, False
    return None, False


def find_prior_convergence(
    repository: Path | str,
    identity: ConvergenceIdentity,
    *,
    store: Any | None = None,
    runner: CommandRunner = run_command,
    ref: str = "HEAD",
) -> PriorConvergence:
    """Consult **both** idempotence sources and report what they said.

    Both are always consulted, even once one is positive, so the result names
    every source that agreed and every source that could not be read. That is
    what makes :attr:`PriorConvergence.conclusive` meaningful.
    """
    root = Path(repository).resolve()
    resolved_store = store if store is not None else _default_store(root)

    sources: list[str] = []
    unreadable: list[str] = []

    if resolved_store is None:
        unreadable.append(SOURCE_OPERATION_RECORD)
    else:
        record_found, record_unreadable = find_prior_operation_record(
            identity, store=resolved_store
        )
        if record_found:
            sources.append(SOURCE_OPERATION_RECORD)
        elif record_unreadable:
            unreadable.append(SOURCE_OPERATION_RECORD)

    commit, trailer_unreadable = find_prior_commit_trailer(
        root, identity, runner=runner, ref=ref
    )
    if commit is not None:
        sources.append(SOURCE_COMMIT_TRAILER)
    elif trailer_unreadable:
        unreadable.append(SOURCE_COMMIT_TRAILER)

    return PriorConvergence(
        found=bool(sources),
        sources=tuple(sources),
        unreadable=tuple(unreadable),
        convergence_commit=commit,
    )


def _default_store(repository: Path) -> Any | None:
    """Build the production ri-06 store, or ``None`` when it cannot be built."""
    try:
        from store import OperationStore

        return OperationStore(repository)
    except Exception:  # noqa: BLE001 - absence is classified upstream, never fatal
        return None


# --------------------------------------------------------------------------- #
# Three-layer sync-point guard (D5)
# --------------------------------------------------------------------------- #
class GuardLayer(str, Enum):
    """The three layers, in the order they are enforced."""

    ACTIVE_AGENTS = "active-agents"
    COORDINATOR_LOCK = "coordinator-lock"
    PUSH_COMPARE_AND_SWAP = "push-compare-and-swap"


@dataclass(frozen=True, slots=True)
class GuardResult:
    """Verdict of one guard layer."""

    layer: GuardLayer
    allowed: bool
    reason: str
    warnings: tuple[str, ...] = ()
    lock_acquired: bool = False
    observed_revision: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer.value,
            "allowed": self.allowed,
            "reason": self.reason,
            "warnings": list(self.warnings),
            "lock_acquired": self.lock_acquired,
            "observed_revision": self.observed_revision,
        }


@dataclass(frozen=True, slots=True)
class GuardState:
    """Composite verdict of the layers that run *before* the write begins."""

    allowed: bool
    blocked_by: GuardLayer | None = None
    reason: str | None = None
    warnings: tuple[str, ...] = ()
    lock_acquired: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "blocked_by": self.blocked_by.value if self.blocked_by else None,
            "reason": self.reason,
            "warnings": list(self.warnings),
            "lock_acquired": self.lock_acquired,
        }


#: ``repo_root -> (clear, active_agents)``. Matches ``active_agents``' own shape.
ActiveAgentChecker = Callable[[Path], tuple[bool, Sequence[Any]]]

#: Default identity used for the coordinator lock when the caller names none.
DEFAULT_AGENT_ID = "merge-pull-requests-sync-point"

#: Coordinator lock lifetime. Generous enough for a full deterministic refresh
#: plus an architecture regeneration, short enough that a crashed pass expires.
DEFAULT_LOCK_TTL_MINUTES = 60


def _default_active_agent_checker(repo_root: Path) -> tuple[bool, Sequence[Any]]:
    from active_agents import check_no_active_agents

    return check_no_active_agents(repo_root=repo_root)


def check_active_agents(
    repository: Path | str,
    *,
    checker: ActiveAgentChecker | None = None,
) -> GuardResult:
    """Layer 1: refuse to write main while any agent holds a managed worktree.

    Re-run here rather than trusted from skill start: the merge loop takes long
    enough for an agent to have set one up in between.

    A checker that cannot run **blocks**. "The guard did not answer" is not the
    same as "the guard said yes", and this roadmap exists because that
    substitution was made once already.
    """
    resolved = checker or _default_active_agent_checker
    try:
        clear, active = resolved(Path(repository).resolve())
    except Exception as exc:  # noqa: BLE001 - classified, never propagated
        return GuardResult(
            layer=GuardLayer.ACTIVE_AGENTS,
            allowed=False,
            reason="active_agent_check_unavailable",
            warnings=(f"active-agent guard could not run: {exc}",),
        )
    if clear:
        return GuardResult(
            layer=GuardLayer.ACTIVE_AGENTS, allowed=True, reason="no_active_agents"
        )
    labels = ", ".join(str(_agent_label(agent)) for agent in active)
    return GuardResult(
        layer=GuardLayer.ACTIVE_AGENTS,
        allowed=False,
        reason=f"active_agents_hold_worktrees: {labels}",
    )


def _agent_label(agent: Any) -> str:
    label = getattr(agent, "label", None)
    if callable(label):
        return str(label())
    if label is not None:
        return str(label)
    return str(agent)


def _default_lock_acquirer(**kwargs: Any) -> dict[str, Any]:
    from coordination_bridge import try_lock

    return try_lock(**kwargs)


def _default_lock_releaser(**kwargs: Any) -> dict[str, Any]:
    from coordination_bridge import try_unlock

    return try_unlock(**kwargs)


def acquire_coordinator_lock(
    *,
    agent_id: str = DEFAULT_AGENT_ID,
    ttl_minutes: int = DEFAULT_LOCK_TTL_MINUTES,
    acquirer: Callable[..., dict[str, Any]] | None = None,
) -> GuardResult:
    """Layer 2: hold ``sync-point:main-convergence`` for the whole of Step 11.6.

    Coordinator *absence* degrades to layers 1 and 3 with a recorded warning and
    never blocks: this repository runs solo often enough that a coordinator-only
    guard would be missing exactly when it matters. Coordinator *contention* is a
    different signal entirely -- another writer holds the sync point -- and
    blocks.
    """
    resolved = acquirer or _default_lock_acquirer
    try:
        response = resolved(
            file_path=COORDINATOR_LOCK_KEY,
            agent_id=agent_id,
            agent_type="merge-pull-requests",
            reason="main context convergence sync point",
            ttl_minutes=ttl_minutes,
        )
    except Exception as exc:  # noqa: BLE001 - unavailability is a warning, not a stop
        return GuardResult(
            layer=GuardLayer.COORDINATOR_LOCK,
            allowed=True,
            reason="coordinator_lock_unavailable",
            warnings=(f"coordinator lock unavailable, proceeding on layers 1 and 3: {exc}",),
        )

    status = str((response or {}).get("status", "")).lower()
    if status == "ok":
        return GuardResult(
            layer=GuardLayer.COORDINATOR_LOCK,
            allowed=True,
            reason="coordinator_lock_held",
            lock_acquired=True,
        )
    if status == "skipped":
        why = str((response or {}).get("reason", "unknown"))
        return GuardResult(
            layer=GuardLayer.COORDINATOR_LOCK,
            allowed=True,
            reason="coordinator_lock_unavailable",
            warnings=(
                f"coordinator lock skipped ({why}); proceeding on layers 1 and 3",
            ),
        )
    return GuardResult(
        layer=GuardLayer.COORDINATOR_LOCK,
        allowed=False,
        reason=f"coordinator_lock_contended: {(response or {}).get('status_code', status)}",
    )


def acquire_sync_point_guards(
    repository: Path | str,
    *,
    agent_id: str = DEFAULT_AGENT_ID,
    ttl_minutes: int = DEFAULT_LOCK_TTL_MINUTES,
    active_agent_checker: ActiveAgentChecker | None = None,
    lock_acquirer: Callable[..., dict[str, Any]] | None = None,
) -> GuardState:
    """Run layers 1 and 2 in order, stopping at the first that blocks.

    Layer 2 is never reached once layer 1 blocked, so a blocked pass never takes
    a lock it would then have to remember to release.
    """
    layer_one = check_active_agents(repository, checker=active_agent_checker)
    if not layer_one.allowed:
        return GuardState(
            allowed=False,
            blocked_by=layer_one.layer,
            reason=layer_one.reason,
            warnings=layer_one.warnings,
        )

    layer_two = acquire_coordinator_lock(
        agent_id=agent_id, ttl_minutes=ttl_minutes, acquirer=lock_acquirer
    )
    if not layer_two.allowed:
        return GuardState(
            allowed=False,
            blocked_by=layer_two.layer,
            reason=layer_two.reason,
            warnings=layer_one.warnings + layer_two.warnings,
        )

    return GuardState(
        allowed=True,
        warnings=layer_one.warnings + layer_two.warnings,
        lock_acquired=layer_two.lock_acquired,
    )


def release_sync_point_guards(
    state: GuardState,
    *,
    agent_id: str = DEFAULT_AGENT_ID,
    releaser: Callable[..., dict[str, Any]] | None = None,
) -> tuple[str, ...]:
    """Release whatever :func:`acquire_sync_point_guards` took.

    Returns warnings rather than raising: a lock that cannot be released is a
    reporting problem, and letting it abort the pass would turn a coordinator
    hiccup into a convergence failure.
    """
    if not state.lock_acquired:
        return ()
    resolved = releaser or _default_lock_releaser
    try:
        resolved(file_path=COORDINATOR_LOCK_KEY, agent_id=agent_id)
    except Exception as exc:  # noqa: BLE001 - release failure is reported, not raised
        return (f"coordinator lock {COORDINATOR_LOCK_KEY} could not be released: {exc}",)
    return ()


def verify_push_target(
    repository: Path | str,
    identity: ConvergenceIdentity,
    *,
    runner: CommandRunner = run_command,
    remote: str = "origin",
    branch: str = "main",
    fetch: bool = True,
) -> GuardResult:
    """Layer 3: compare-and-swap ``<remote>/<branch>`` against the keyed revision.

    Run immediately before the push. A mismatch means someone else landed a
    commit while this pass worked, so the tree about to be pushed converges a
    main state this pass did not produce: abort, leave the operation resumable,
    report. Never force, and never ``--force-with-lease`` -- a lease that
    succeeds still overwrites the other writer's commit.

    A fetch or read that fails also blocks. A stale ref that happens to match is
    indistinguishable from a real match, so "could not refresh the ref" cannot be
    allowed to look like agreement.
    """
    root = Path(repository).resolve()
    guarded = guarded_runner(runner)
    if fetch:
        try:
            fetched = guarded(["git", "fetch", remote, branch], root)
        except OSError as exc:
            return GuardResult(
                layer=GuardLayer.PUSH_COMPARE_AND_SWAP,
                allowed=False,
                reason=f"push_target_unreadable: {exc}",
            )
        if not fetched.ok:
            return GuardResult(
                layer=GuardLayer.PUSH_COMPARE_AND_SWAP,
                allowed=False,
                reason="push_target_unreadable: could not fetch "
                f"{remote}/{branch}: {fetched.stderr.strip()}",
            )

    try:
        observed = guarded(["git", "rev-parse", f"{remote}/{branch}"], root)
    except OSError as exc:
        return GuardResult(
            layer=GuardLayer.PUSH_COMPARE_AND_SWAP,
            allowed=False,
            reason=f"push_target_unreadable: {exc}",
        )
    if not observed.ok or not observed.stdout.strip():
        return GuardResult(
            layer=GuardLayer.PUSH_COMPARE_AND_SWAP,
            allowed=False,
            reason=f"push_target_unreadable: could not resolve {remote}/{branch}",
        )

    actual = observed.stdout.strip()
    if actual != identity.merged_revision:
        return GuardResult(
            layer=GuardLayer.PUSH_COMPARE_AND_SWAP,
            allowed=False,
            reason=(
                f"push_race_lost: {remote}/{branch} is {actual[:12]}, not the merged "
                f"revision {identity.merged_revision[:12]} this convergence is keyed on"
            ),
            observed_revision=actual,
        )
    return GuardResult(
        layer=GuardLayer.PUSH_COMPARE_AND_SWAP,
        allowed=True,
        reason="push_target_matches_merged_revision",
        observed_revision=actual,
    )


# --------------------------------------------------------------------------- #
# Phase sequence (D2, D3, D10)
# --------------------------------------------------------------------------- #
#: The staged, provenance-writing architecture target. NOT ``make architecture``:
#: ``write_provenance`` is called only from ``run_staged``, and ri-10's producer
#: routes missing provenance to *drift* rather than to ``not-configured``, so the
#: full generation target can regenerate every artifact and still leave the gate
#: red (D10).
ARCHITECTURE_COMMAND: tuple[str, ...] = ("make", "architecture-refresh")

#: Read-only composed drift gate, used by the dry run only (D12).
DRIFT_GATE_COMMAND: tuple[str, ...] = ("make", "context-drift-gate")

#: Refresh statuses, mirroring the refresh CLI's exit codes plus one value the
#: CLI has no reason to know about: ``not-run`` records a convergence whose
#: cleanup output was committed but whose refresh never started. Collapsing that
#: into ``failed`` would make a successful partial convergence indistinguishable
#: from a producer crash.
REFRESH_NOT_RUN = "not-run"
_REFRESH_STATUS_BY_EXIT: dict[int, str] = {0: "succeeded", 2: "degraded", 1: "failed"}

#: Refresh outcomes whose output is safe to sweep into the convergence commit.
#: A ``failed`` run is excluded on purpose: D6 commits the *cleanup* output and
#: omits the failed run's partial artifacts, leaving the operation resumable.
_SWEEPABLE_REFRESH_STATUSES = frozenset({"succeeded", "degraded"})


@dataclass(frozen=True, slots=True)
class MergedPullRequest:
    """One merge that contributed to the main state being converged."""

    number: int
    origin: str
    change_id: str | None = None
    cleanup: str = "not-applicable"

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"number": self.number, "origin": self.origin}
        if self.change_id is not None:
            out["change_id"] = self.change_id
        out["cleanup"] = self.cleanup
        return out


@dataclass(frozen=True, slots=True)
class RefreshPhase:
    """Outcome of the one deterministic refresh this pass runs."""

    ran: bool
    status: str
    exit_code: int | None = None
    summary: dict[str, Any] | None = None
    warnings: tuple[str, ...] = ()

    @property
    def sweepable(self) -> bool:
        return self.status in _SWEEPABLE_REFRESH_STATUSES


def refresh_cli_path() -> Path:
    """Absolute path to the refresh CLI that owns ``--sync-point``."""
    return _SKILLS_DIR / "project-context-refresh" / "scripts" / "cli.py"


def run_architecture_refresh(
    repository: Path | str, *, runner: CommandRunner = run_command
) -> CommandResult:
    """Run the staged architecture target so provenance is written (D10)."""
    return guarded_runner(runner)(list(ARCHITECTURE_COMMAND), Path(repository).resolve())


def run_deterministic_refresh(
    repository: Path | str,
    *,
    runner: CommandRunner = run_command,
    python: str | None = None,
) -> RefreshPhase:
    """Run the single deterministic refresh for this pass.

    ``--sync-point`` is what makes the write legal in the shared checkout where
    ``merge-pull-requests`` operates; ``--defer-semantic-index`` keeps the index
    out of the critical path, because the revision worth indexing is the one this
    pass has not created yet (D7).

    A refresh that exits non-zero is *data*, never an exception: the outcome maps
    straight onto D6's table.
    """
    root = Path(repository).resolve()
    argv = [
        python or sys.executable,
        str(refresh_cli_path()),
        "--repo",
        str(root),
        "refresh",
        "--sync-point",
        "--defer-semantic-index",
    ]
    try:
        result = guarded_runner(runner)(argv, root)
    except OSError as exc:
        return RefreshPhase(
            ran=False,
            status=REFRESH_NOT_RUN,
            warnings=(f"deterministic refresh could not be started: {exc}",),
        )

    status = _REFRESH_STATUS_BY_EXIT.get(result.returncode, "failed")
    warnings: list[str] = []
    summary: dict[str, Any] | None = None
    try:
        parsed = json.loads(result.stdout)
        summary = parsed if isinstance(parsed, dict) else None
    except (ValueError, TypeError):
        summary = None
    if summary is None:
        warnings.append(
            "deterministic refresh emitted no parsable summary; producer detail is "
            "unavailable for this record"
        )
    if status != "succeeded":
        warnings.append(
            f"deterministic refresh reported {status} (exit {result.returncode})"
        )
    return RefreshPhase(
        ran=True,
        status=status,
        exit_code=result.returncode,
        summary=summary,
        warnings=tuple(warnings),
    )


def build_commit_message(
    identity: ConvergenceIdentity,
    *,
    merged_pull_requests: Sequence[MergedPullRequest],
    refresh_status: str,
) -> str:
    """Render the convergence commit message, deterministically.

    No timestamps and no set iteration: the same inputs must render the same
    message, or two runs of one pass would be indistinguishable only by luck.
    The ``Context-Refresh-Operation`` trailer is the half of the idempotence
    contract that survives a fresh clone, so it appears exactly once.
    """
    numbers = sorted(pr.number for pr in merged_pull_requests)
    rendered = ", ".join(f"#{number}" for number in numbers)
    plural = "" if len(numbers) == 1 else "s"
    lines = [
        f"chore(context): converge main after {len(numbers)} merged pull request{plural}",
        "",
        f"Merged pull request{plural}: {rendered}." if numbers else "No merged pull requests.",
        f"Merged revision: {identity.merged_revision}.",
        f"Deterministic refresh: {refresh_status}.",
        "",
        "Derived context regenerated at the authoritative main-synchronization",
        "point. This commit is downstream of the merges above and reverses none",
        "of them.",
        "",
        f"{CONVERGENCE_TRAILER}: {identity.operation_id}",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# The tracked convergence record (D9)
# --------------------------------------------------------------------------- #
RECORD_SCHEMA_VERSION = 1
_RECORD_SCHEMA_FILE = "context-convergence-record.schema.json"

#: Contract bounds, mirrored so the driver truncates rather than emitting a
#: record the published schema would reject.
_MAX_WARNING_LEN = 500
_MAX_FALLBACK_LEN = 500

#: Where the published schemas may live, most specific first. The install-asset
#: copies travel with the skills into a consumer repository that has no
#: ``openspec/contracts/`` of its own; the promoted copy is the stable
#: capability-scoped home in this repository.
_SCHEMA_SEARCH_DIRS: tuple[Path, ...] = (
    _SKILLS_DIR / "project-context-refresh" / "install_assets" / "openspec" / "schemas",
    _SKILLS_DIR / "project-context-runtime" / "install_assets" / "openspec" / "schemas",
)


@dataclass(frozen=True, slots=True)
class ProducerOutcome:
    """One producer's outcome joined with its canonical owner.

    The join exists because the ri-06 ``ProducerResult`` carries no ``owner``
    field -- ownership lives on the registry ``ProducerSpec`` -- so a record that
    wants to *name* who must act has to carry both.
    """

    producer_id: str
    status: str
    owner: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"producer_id": self.producer_id, "status": self.status, "owner": self.owner}


@dataclass(frozen=True, slots=True)
class SemanticIndexRecord:
    """The index enqueued for a revision, as recorded rather than as awaited."""

    status: str
    requested_revision: str
    operation_id: str | None = None
    fallback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "status": self.status,
            "requested_revision": self.requested_revision,
            "operation_id": self.operation_id,
        }
        if self.fallback is not None:
            out["fallback"] = self.fallback[:_MAX_FALLBACK_LEN]
        return out


def producers_from_summary(summary: Mapping[str, Any] | None) -> tuple[ProducerOutcome, ...]:
    """Project the refresh summary's producer results onto record entries."""
    if not summary:
        return ()
    results = summary.get("producer_results") or []
    outcomes: list[ProducerOutcome] = []
    for item in results:
        if not isinstance(item, Mapping):
            continue
        producer_id = item.get("producer_id")
        status = item.get("status")
        if not isinstance(producer_id, str) or not isinstance(status, str):
            continue
        owner = item.get("owner")
        outcomes.append(
            ProducerOutcome(
                producer_id=producer_id,
                status=status,
                owner=owner if isinstance(owner, str) else None,
            )
        )
    # Sorted so a re-run over the same results renders byte-identical bytes; the
    # registry's iteration order is not part of this contract.
    return tuple(sorted(outcomes, key=lambda outcome: outcome.producer_id))


def semantic_from_summary(
    summary: Mapping[str, Any] | None, *, requested_revision: str
) -> SemanticIndexRecord:
    """Project the refresh summary's semantic reference onto a record entry.

    Recording *nothing* was rejected: ``decide_outcome`` reads a missing
    reference as "the index was not part of this run" and would report a clean
    success while making no currency claim at all. ``pending`` with a fallback is
    the honest value, so an absent summary degrades to exactly that rather than
    to silence.
    """
    reference = (summary or {}).get("semantic_index") if summary else None
    if not isinstance(reference, Mapping):
        return SemanticIndexRecord(
            status="pending",
            requested_revision=requested_revision,
            fallback="exact-search: no semantic reference was reported by the refresh",
        )
    fallback = reference.get("fallback")
    rendered: str | None = None
    if isinstance(fallback, Mapping):
        rendered = f"{fallback.get('kind')}: {fallback.get('reason')}"
    elif isinstance(fallback, str):
        rendered = fallback
    status = reference.get("status")
    return SemanticIndexRecord(
        status=status if isinstance(status, str) else "pending",
        requested_revision=(
            reference.get("requested_revision")
            if isinstance(reference.get("requested_revision"), str)
            else requested_revision
        ),
        operation_id=(
            reference.get("operation_id")
            if isinstance(reference.get("operation_id"), str)
            else None
        ),
        fallback=rendered,
    )


def build_record(
    *,
    identity: ConvergenceIdentity,
    refresh_revision: str,
    refresh_status: str,
    summary: Mapping[str, Any] | None,
    merged_pull_requests: Sequence[MergedPullRequest],
    convergence_commit: str | None = None,
    semantic_index: SemanticIndexRecord | None = None,
    warnings: Sequence[str] = (),
) -> dict[str, Any]:
    """Build one convergence record.

    Two shapes come out of this one builder, on purpose.

    The *in-flight* shape (``convergence_commit=None``) is what lands inside the
    convergence commit, because a commit cannot contain its own SHA. Its
    ``semantic_index`` is the deferred ``pending`` reference the refresh actually
    recorded -- a true statement about the moment the commit was made.

    The *completed* shape names the convergence commit and the index enqueued for
    that final pushed revision, and is returned to the pass summary and merge log.

    Deterministic by construction: producers and pull requests are sorted, and
    nothing derived from a clock or from set iteration order enters the record.
    """
    index = semantic_index or semantic_from_summary(
        summary, requested_revision=refresh_revision
    )
    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "operation_id": identity.operation_id,
        "merged_revision": identity.merged_revision,
        "refresh_revision": refresh_revision,
        "convergence_commit": convergence_commit,
        "manifest_path": (summary or {}).get("manifest_path"),
        "manifest_sha256": (summary or {}).get("manifest_sha256"),
        "refresh_status": refresh_status,
        "producers": [outcome.to_dict() for outcome in producers_from_summary(summary)],
        "semantic_index": index.to_dict(),
        "merged_pull_requests": [
            pr.to_dict() for pr in sorted(merged_pull_requests, key=lambda pr: pr.number)
        ],
        "warnings": [warning[:_MAX_WARNING_LEN] for warning in warnings],
    }


def render_record_line(record: Mapping[str, Any]) -> str:
    """Render one record as its canonical single JSONL line."""
    return json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"


def _record_schema_dirs(repository: Path | None) -> tuple[Path, ...]:
    dirs = list(_SCHEMA_SEARCH_DIRS)
    if repository is not None:
        dirs.append(
            Path(repository) / "openspec" / "contracts" / "project-context-refresh" / "schemas"
        )
    return tuple(d for d in dirs if d.is_dir())


def _build_record_validator(repository: Path | None) -> Any:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    resources = []
    schema: dict[str, Any] | None = None
    for directory in _record_schema_dirs(repository):
        for path in sorted(directory.glob("*.schema.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            identifier = data.get("$id")
            if not isinstance(identifier, str):
                continue
            resources.append(
                (identifier, Resource.from_contents(data, default_specification=DRAFT202012))
            )
            if schema is None and path.name == _RECORD_SCHEMA_FILE:
                schema = data
    if schema is None:
        raise ConvergenceApparatusError(
            "the convergence record contract "
            f"({_RECORD_SCHEMA_FILE}) is not installed; refusing to emit an "
            "unvalidatable record"
        )
    return Draft202012Validator(schema, registry=Registry().with_resources(resources))


def validate_record(record: Mapping[str, Any], *, repository: Path | str | None = None) -> None:
    """Validate a record against the published contract, failing closed.

    A record that cannot be validated is never emitted: the whole point of a
    tracked record is that a later reader can trust it, and an unvalidated line
    is a claim with no contract behind it.
    """
    validator = _build_record_validator(Path(repository) if repository else None)
    errors = sorted(validator.iter_errors(record), key=lambda err: list(err.absolute_path))
    if errors:
        rendered = "; ".join(
            f"{'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
            for err in errors
        )
        raise ConvergenceApparatusError(f"convergence record is invalid: {rendered}")


def append_record(
    repository: Path | str,
    record: Mapping[str, Any],
    *,
    path: str = CONVERGENCE_RECORD_PATH,
) -> Path:
    """Append one record as a single line, creating the file if needed.

    Append-only and one object per line, following the existing
    ``docs/merge-logs/metrics.jsonl`` convention: a per-SHA file under ``docs/``
    would grow without bound in a directory the documentation producer reads, and
    recording only in the human merge log would leave the idempotence check with
    nothing machine-readable to consult.
    """
    target = Path(repository).resolve() / path
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(render_record_line(record))
    return target


# --------------------------------------------------------------------------- #
# Semantic index enqueue (D7)
# --------------------------------------------------------------------------- #
_ENQUEUE_FALLBACK = (
    "exact-search: the semantic index is enqueued for the pushed revision and has "
    "not completed; use exact search until it does"
)
_ENQUEUE_FAILED_FALLBACK = (
    "exact-search: the semantic index could not be enqueued for the pushed "
    "revision; use exact search"
)


def enqueue_semantic_index(
    repository: Path | str,
    revision: str,
    *,
    repository_id: str | None = None,
    store: Any | None = None,
    environ: Mapping[str, str] | None = None,
    runner: CommandRunner = run_command,
) -> SemanticIndexRecord:
    """Enqueue exactly one index for the **final pushed** revision, and return.

    The pushed revision is a different revision from the one the operation is
    keyed on -- the convergence commit moved main's tip -- and therefore a
    separate ri-06 operation of its own. Creating that operation *is* the
    enqueue: it makes a durable, discoverable ``pending`` request for the exact
    revision, which a later indexer resumes.

    Never awaited. One indexing run defaults to a 1800-second ceiling, and
    blocking a sync point on a half-hour rebuild would make the semantic index a
    hard dependency of merging, which this change explicitly rules out.

    Never fail-open: an enqueue that did not happen is reported ``failed`` with a
    fallback, not ``pending``. ``pending`` is a claim that a request exists.
    """
    root = Path(repository).resolve()
    try:
        ensure_git_revision(revision)
        resolved_id = repository_id or resolve_repository_id(
            root, environ=environ, runner=runner
        )
        resolved_store = store if store is not None else _default_store(root)
        if resolved_store is None:
            raise ConvergenceApparatusError("no operation ledger is available")
        record = resolved_store.create_or_load(resolved_id, revision)
    except Exception:  # noqa: BLE001 - the index never blocks or crashes a pass
        return SemanticIndexRecord(
            status="failed",
            requested_revision=revision,
            fallback=_ENQUEUE_FAILED_FALLBACK,
        )
    return SemanticIndexRecord(
        status="pending",
        requested_revision=revision,
        operation_id=getattr(record, "operation_id", None),
        fallback=_ENQUEUE_FALLBACK,
    )


# --------------------------------------------------------------------------- #
# Convergence outcomes (D6)
# --------------------------------------------------------------------------- #
class ConvergenceStatus(str, Enum):
    """What the pass did. None of these values can mean "the merge failed"."""

    CONVERGED = "converged"
    ALREADY_CONVERGED = "already-converged"
    NO_MERGES = "no-merges"
    BLOCKED = "blocked"
    DRY_RUN = "dry-run"


@dataclass(frozen=True, slots=True)
class ConvergenceResult:
    """Everything the pass summary and the merge log need to report."""

    status: ConvergenceStatus
    identity: ConvergenceIdentity | None = None
    refresh_status: str = REFRESH_NOT_RUN
    convergence_commit: str | None = None
    pushed_revision: str | None = None
    record: dict[str, Any] | None = None
    prior: PriorConvergence | None = None
    drift: dict[str, Any] | None = None
    reason: str | None = None
    warnings: tuple[str, ...] = ()

    def exit_code(self) -> int:
        """D6's exit column. A non-zero code NEVER means the merge failed.

        The merge is already terminal by the time this runs, so every code here
        describes derived context only. Step 12 reports the merges either way.
        """
        if self.status in (
            ConvergenceStatus.ALREADY_CONVERGED,
            ConvergenceStatus.NO_MERGES,
            ConvergenceStatus.DRY_RUN,
        ):
            return 0
        if self.status is ConvergenceStatus.BLOCKED:
            return 2
        if self.refresh_status == "succeeded":
            return 0
        if self.refresh_status == "failed":
            return 1
        return 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "identity": (
                {
                    "repository_id": self.identity.repository_id,
                    "merged_revision": self.identity.merged_revision,
                    "operation_id": self.identity.operation_id,
                }
                if self.identity
                else None
            ),
            "refresh_status": self.refresh_status,
            "convergence_commit": self.convergence_commit,
            "pushed_revision": self.pushed_revision,
            "record": self.record,
            "prior": self.prior.to_dict() if self.prior else None,
            "drift": self.drift,
            "reason": self.reason,
            "warnings": list(self.warnings),
            "exit_code": self.exit_code(),
        }


#: Drift-gate exit codes, in the gate's own vocabulary. ``1`` is deliberately
#: NOT folded into "drift": an apparatus failure is unknown state, and reporting
#: unknown as either fresh or drifted would be a guess presented as a finding.
_DRIFT_VERDICT_BY_EXIT: dict[int, str] = {0: "fresh", 2: "drift"}


# --------------------------------------------------------------------------- #
# The gate record (D7) -- telemetry about the verdict, never part of it
# --------------------------------------------------------------------------- #
#: Environment variable ``make context-drift-gate`` forwards to the gate as
#: ``--event``. The report does not echo it back, so the record reads it from the
#: same environment the invocation was made in. Absent means no event was
#: supplied, which is the gate's strict rule and is recorded as an absent key
#: rather than an invented name.
GATE_EVENT_ENV = "CONTEXT_GATE_EVENT"

#: The gate's attribution vocabulary, consumed rather than defined here:
#: ``gate.py`` owns these names and writes them verbatim onto every finding it
#: reports. Counted as a fixed group so a run with no inherited findings records
#: ``0`` rather than omitting the key -- "three clean runs in a row" is a claim
#: about runs that counted zero, and a missing key would let silence count as
#: clean.
_GATE_ATTRIBUTIONS: tuple[str, ...] = ("inherited", "introduced", "indeterminate")


def _attribution_counts(findings: Any) -> dict[str, int]:
    """Count one drift group by attribution, with every member present."""
    counts = dict.fromkeys(_GATE_ATTRIBUTIONS, 0)
    for finding in findings or ():
        attribution = finding.get("attribution") if isinstance(finding, dict) else None
        if attribution in counts:
            counts[attribution] += 1
    return counts


def record_gate_event(
    repository: Path | str,
    gate: CommandResult,
    *,
    environ: Mapping[str, str] | None = None,
) -> Path | None:
    """Append one ``context_gate`` row for *gate*. Returns where, or ``None``.

    The gate builds this record but cannot deliver it. A ratified scenario
    requires it to leave the tree it grades byte-identical, so it refuses any
    destination inside the checkout -- which is every destination a reader of
    this repository would look in. The direction is therefore inverted here: the
    gate stays read-only and reports on stdout, and the merge train, which
    already writes ``docs/merge-logs/``, reads that report and writes the row.

    The row is built by :func:`merge_events.context_gate_event`, the same builder
    the gate calls, so there is one field vocabulary rather than two that drift
    apart. The destination is ``merge_events.DEFAULT_LOG_PATH`` resolved against
    the repository root -- read at call time, because that constant is the
    suite's single monkeypatchable seam and because the train may be driven from
    a directory that is not the checkout.

    **Recording must never change the verdict.** The verdict is the product; the
    row is evidence about the product. Every failure mode -- stdout that is not a
    report, a report missing a key, an unwritable log, the events module absent
    -- is caught here and reported to stderr, which is why the ``except
    Exception`` is deliberate rather than lazy: narrowing it would let some
    unanticipated error escape into a convergence outcome, and a convergence
    outcome that depends on whether telemetry succeeded is worse than no
    telemetry. *gate* is taken read-only and the caller's ``verdict`` is already
    computed, so there is no path by which this edits what it describes.
    """
    try:
        scripts_dir = str(Path(__file__).resolve().parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import merge_events

        report = json.loads(gate.stdout)
        tree = report.get("tree") or {}
        blocking = _attribution_counts(report.get("blocking_drift"))
        informational = _attribution_counts(report.get("informational_drift"))
        env = os.environ if environ is None else environ
        destination = Path(repository).resolve() / merge_events.DEFAULT_LOG_PATH
        merge_events.emit_event(
            merge_events.context_gate_event(
                outcome=report["outcome"],
                exit_code=report["exit_code"],
                gate_event=env.get(GATE_EVENT_ENV) or None,
                source_revision=report.get("source_revision"),
                base_revision=tree.get("base_resolved_revision"),
                base_resolved_from=tree.get("base_resolved_from"),
                blocking_inherited=blocking["inherited"],
                blocking_introduced=blocking["introduced"],
                blocking_indeterminate=blocking["indeterminate"],
                informational_inherited=informational["inherited"],
                informational_introduced=informational["introduced"],
                informational_indeterminate=informational["indeterminate"],
            ),
            log_path=destination,
        )
        return destination
    except Exception as error:  # noqa: BLE001 -- see the docstring
        print(
            f"[WARN] context gate event not recorded: "
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return None


def dry_run(
    repository: Path | str,
    *,
    merged_revision: str | None = None,
    runner: CommandRunner = run_command,
    store: Any | None = None,
    environ: Mapping[str, str] | None = None,
) -> ConvergenceResult:
    """Report what a convergence *would* do, having done none of it (D12).

    A dry run performs no merge, so there is no merged SHA and no convergence.
    It reports the identity it would derive from the current ``main`` HEAD,
    whether a terminal record or a commit trailer already exists for that
    identity, and a read-only drift assessment.

    Running the real refresh here "to show what would change" was rejected: the
    mutating path writes producer output into the working tree, and a dry run
    that dirties main is not a dry run. ``make context-drift-gate`` writes
    nothing by construction, which is why it is the assessment used.

    The one thing this pass does write is a single ``context_gate`` telemetry row
    for the gate run it just observed (:func:`record_gate_event`). That is not
    producer output and it is not part of the assessment: the row is appended to
    the same append-only ``docs/merge-logs/`` log the train already keeps, and
    failing to write it cannot alter a field of the result below.
    """
    root = Path(repository).resolve()
    identity = derive_convergence_identity(
        root, merged_revision=merged_revision, environ=environ, runner=runner
    )
    prior = find_prior_convergence(root, identity, store=store, runner=runner)

    try:
        gate = guarded_runner(runner)(list(DRIFT_GATE_COMMAND), root)
        verdict = _DRIFT_VERDICT_BY_EXIT.get(gate.returncode, "apparatus-failure")
        exit_code: int | None = gate.returncode
    except OSError as exc:
        verdict = "apparatus-failure"
        exit_code = None
        prior = prior  # unchanged; the gate says nothing about idempotence
        gate_error: str | None = str(exc)
    else:
        gate_error = None
        # After the verdict, never before it, and unable to change it.
        record_gate_event(root, gate, environ=environ)

    return ConvergenceResult(
        status=ConvergenceStatus.DRY_RUN,
        identity=identity,
        prior=prior,
        drift={
            "command": list(DRIFT_GATE_COMMAND),
            "exit_code": exit_code,
            "verdict": verdict,
            "error": gate_error,
        },
        reason=(
            "dry run: no merge was performed, so nothing was converged. "
            f"Identity that would have been used: {identity.operation_id}."
        ),
    )


#: Stable alias for :func:`dry_run`, used inside ``converge`` where the
#: ``dry_run`` keyword parameter shadows the function name.
_dry_run_report = dry_run


def converge(
    repository: Path | str,
    *,
    merged_pull_requests: Sequence[MergedPullRequest] = (),
    merged_revision: str | None = None,
    runner: CommandRunner = run_command,
    store: Any | None = None,
    environ: Mapping[str, str] | None = None,
    agent_id: str = DEFAULT_AGENT_ID,
    active_agent_checker: ActiveAgentChecker | None = None,
    lock_acquirer: Callable[..., dict[str, Any]] | None = None,
    lock_releaser: Callable[..., dict[str, Any]] | None = None,
    semantic_enqueuer: Callable[[Path, str], Any] | None = None,
    remote: str = "origin",
    branch: str = "main",
    python: str | None = None,
    record_path: str = CONVERGENCE_RECORD_PATH,
    dry_run: bool = False,
) -> ConvergenceResult:
    """Converge derived context for the main state this pass produced.

    One invocation pass, one convergence (D8). ``k = 0`` merged pull requests
    converge nothing: that pass was a read of main, not a write.

    The sequence is fixed -- staged cleanup output (already in the index, owned by
    ``cleanup-feature``), then the staged architecture target, then one
    deterministic refresh, then one commit, then one push. Convergence never
    archives, never merges spec deltas, and never migrates tasks; duplicating that
    logic in two skills would make the first divergence between them a silent spec
    corruption.
    """
    root = Path(repository).resolve()
    recorded: list[tuple[str, ...]] = []

    def _record_calls(argv: Sequence[str], cwd: Path) -> CommandResult:
        recorded.append(tuple(str(a) for a in argv))
        return runner(argv, cwd)

    if dry_run:
        # Aliased before the keyword parameter shadows the module-level name.
        return _dry_run_report(
            root,
            merged_revision=merged_revision,
            runner=_record_calls,
            store=store,
            environ=environ,
        )

    if not merged_pull_requests:
        return ConvergenceResult(
            status=ConvergenceStatus.NO_MERGES,
            reason="no pull request merged during this pass; nothing to converge",
        )

    identity = derive_convergence_identity(
        root, merged_revision=merged_revision, environ=environ, runner=_record_calls
    )

    prior = find_prior_convergence(root, identity, store=store, runner=_record_calls)
    if prior.found:
        return ConvergenceResult(
            status=ConvergenceStatus.ALREADY_CONVERGED,
            identity=identity,
            prior=prior,
            convergence_commit=prior.convergence_commit,
            reason=f"already converged; evidence from {', '.join(prior.sources)}",
        )
    if not prior.conclusive:
        return ConvergenceResult(
            status=ConvergenceStatus.BLOCKED,
            identity=identity,
            prior=prior,
            reason=(
                "idempotence check inconclusive: could not read "
                f"{', '.join(prior.unreadable)}. Refusing to converge a state that "
                "may already have converged."
            ),
        )

    guards = acquire_sync_point_guards(
        root,
        agent_id=agent_id,
        active_agent_checker=active_agent_checker,
        lock_acquirer=lock_acquirer,
    )
    if not guards.allowed:
        return ConvergenceResult(
            status=ConvergenceStatus.BLOCKED,
            identity=identity,
            prior=prior,
            reason=guards.reason,
            warnings=guards.warnings,
        )

    warnings: list[str] = list(guards.warnings)

    def _enqueue(target: Path, revision: str) -> SemanticIndexRecord:
        return enqueue_semantic_index(
            target,
            revision,
            repository_id=identity.repository_id,
            store=store,
            environ=environ,
            runner=_record_calls,
        )

    try:
        return _converge_under_guard(
            root,
            identity=identity,
            prior=prior,
            merged_pull_requests=tuple(merged_pull_requests),
            runner=_record_calls,
            warnings=warnings,
            semantic_enqueuer=semantic_enqueuer or _enqueue,
            remote=remote,
            branch=branch,
            python=python,
            record_path=record_path,
        )
    except ConvergenceApparatusError as exc:
        return ConvergenceResult(
            status=ConvergenceStatus.BLOCKED,
            identity=identity,
            prior=prior,
            reason=f"convergence apparatus failed: {exc}",
            warnings=tuple(warnings),
        )
    except OSError as exc:
        return ConvergenceResult(
            status=ConvergenceStatus.BLOCKED,
            identity=identity,
            prior=prior,
            reason=f"convergence apparatus failed: {exc}",
            warnings=tuple(warnings),
        )
    finally:
        warnings.extend(
            release_sync_point_guards(guards, agent_id=agent_id, releaser=lock_releaser)
        )


def _converge_under_guard(
    root: Path,
    *,
    identity: ConvergenceIdentity,
    prior: PriorConvergence,
    merged_pull_requests: tuple[MergedPullRequest, ...],
    runner: CommandRunner,
    warnings: list[str],
    semantic_enqueuer: Callable[[Path, str], Any],
    remote: str,
    branch: str,
    python: str | None,
    record_path: str,
) -> ConvergenceResult:
    """Phases 2 and 3, with layers 1 and 2 already held by the caller."""
    guarded = guarded_runner(runner)

    architecture = run_architecture_refresh(root, runner=runner)
    if not architecture.ok:
        warnings.append(
            "staged architecture refresh failed "
            f"(exit {architecture.returncode}); the architecture producer will "
            "report drift for this revision"
        )

    refresh = run_deterministic_refresh(root, runner=runner, python=python)
    warnings.extend(refresh.warnings)

    # The in-flight record: validated before it is written, so an unvalidatable
    # claim never reaches a commit, and written before staging so it lands in the
    # single convergence commit rather than trailing it.
    in_flight = build_record(
        identity=identity,
        refresh_revision=identity.merged_revision,
        refresh_status=refresh.status,
        summary=refresh.summary,
        merged_pull_requests=merged_pull_requests,
        warnings=warnings,
    )
    validate_record(in_flight, repository=root)
    append_record(root, in_flight, path=record_path)

    if refresh.sweepable:
        guarded(["git", "add", "-A"], root)
    guarded(["git", "add", "--", record_path], root)

    staged = guarded(["git", "diff", "--cached", "--quiet"], root)
    if staged.returncode == 0:
        return ConvergenceResult(
            status=ConvergenceStatus.CONVERGED,
            identity=identity,
            prior=prior,
            refresh_status=refresh.status,
            reason="no repository diff to converge; derived context was already current",
            warnings=tuple(warnings),
        )

    message = build_commit_message(
        identity,
        merged_pull_requests=merged_pull_requests,
        refresh_status=refresh.status,
    )
    committed = guarded(["git", "commit", "-m", message], root)
    if not committed.ok:
        return ConvergenceResult(
            status=ConvergenceStatus.BLOCKED,
            identity=identity,
            prior=prior,
            refresh_status=refresh.status,
            reason=f"convergence commit failed: {committed.stderr.strip()}",
            warnings=tuple(warnings),
        )
    convergence_commit = _git_stdout(runner, root, "rev-parse", "HEAD") or None

    swap = verify_push_target(
        root, identity, runner=runner, remote=remote, branch=branch
    )
    if not swap.allowed:
        return ConvergenceResult(
            status=ConvergenceStatus.BLOCKED,
            identity=identity,
            prior=prior,
            refresh_status=refresh.status,
            convergence_commit=convergence_commit,
            reason=swap.reason,
            warnings=tuple(
                [
                    *warnings,
                    "the convergence commit is present locally and unpushed; the "
                    "operation remains resumable and nothing staged was discarded",
                ]
            ),
        )

    pushed = guarded(["git", "push", remote, f"HEAD:{branch}"], root)
    if not pushed.ok:
        return ConvergenceResult(
            status=ConvergenceStatus.BLOCKED,
            identity=identity,
            prior=prior,
            refresh_status=refresh.status,
            convergence_commit=convergence_commit,
            reason=f"push rejected: {pushed.stderr.strip()}",
            warnings=tuple(
                [
                    *warnings,
                    "the convergence commit is present locally and unpushed; it was "
                    "not retried with force, because losing a sync-point race is "
                    "information rather than an obstacle",
                ]
            ),
        )

    enqueued: SemanticIndexRecord | None = None
    if convergence_commit:
        try:
            candidate = semantic_enqueuer(root, convergence_commit)
        except Exception as exc:  # noqa: BLE001 - the index never blocks a pass
            warnings.append(f"semantic index enqueue failed: {exc}")
        else:
            if isinstance(candidate, SemanticIndexRecord):
                enqueued = candidate
                if enqueued.status != "pending":
                    warnings.append(
                        "semantic index could not be enqueued for the pushed "
                        f"revision; recorded as {enqueued.status}"
                    )

    completed = build_record(
        identity=identity,
        refresh_revision=identity.merged_revision,
        refresh_status=refresh.status,
        summary=refresh.summary,
        merged_pull_requests=merged_pull_requests,
        convergence_commit=convergence_commit,
        semantic_index=enqueued,
        warnings=warnings,
    )

    return ConvergenceResult(
        status=ConvergenceStatus.CONVERGED,
        identity=identity,
        prior=prior,
        refresh_status=refresh.status,
        convergence_commit=convergence_commit,
        pushed_revision=convergence_commit,
        record=completed,
        warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def load_merged_pull_requests(path: Path | str) -> tuple[MergedPullRequest, ...]:
    """Read the merged-PR records collected during the pass.

    Accepts the same shape ``post_merge_cleanup.py --merged-json`` reads, so the
    merge skill collects the records once and both consumers read them.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    records = data.get("merged", data) if isinstance(data, Mapping) else data
    if not isinstance(records, list):
        raise ConvergenceApparatusError(f"{path} does not contain a list of merges")
    merges: list[MergedPullRequest] = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        number = record.get("pr_number") or record.get("number")
        if not isinstance(number, int):
            continue
        change_id = record.get("change_id")
        cleanup = record.get("cleanup")
        merges.append(
            MergedPullRequest(
                number=number,
                origin=str(record.get("origin") or "other"),
                change_id=change_id if isinstance(change_id, str) else None,
                cleanup=cleanup if isinstance(cleanup, str) else "not-applicable",
            )
        )
    return tuple(merges)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one convergence pass and print its result as JSON.

    The exit code follows D6 and describes derived context only. It can never
    mean that a merge failed: by the time this runs, every merge in the pass is
    already terminal, and Step 12 reports them regardless of what happens here.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Converge derived context for the main state a merge pass produced "
            "(ri-11 Step 11.6). Runs once per pass, never once per pull request."
        )
    )
    parser.add_argument("--repo", type=Path, default=Path("."), help="Repository root.")
    parser.add_argument(
        "--merged-json",
        type=Path,
        default=None,
        help="Path to the merged-PR records collected during this pass.",
    )
    parser.add_argument(
        "--merged-revision",
        default=None,
        help="Full SHA of main after every merge in the pass (default: HEAD).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Converge nothing. Report the identity that would be used, whether a "
            "convergence already exists for it, and a read-only drift assessment."
        ),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        merges = (
            load_merged_pull_requests(args.merged_json) if args.merged_json else ()
        )
        result = converge(
            args.repo,
            merged_pull_requests=merges,
            merged_revision=args.merged_revision,
            dry_run=args.dry_run,
        )
    except ConvergenceApparatusError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    sys.stdout.write(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n")
    for warning in result.warnings:
        sys.stderr.write(f"warning: {warning}\n")
    if result.reason:
        sys.stderr.write(f"{result.status.value}: {result.reason}\n")
    return result.exit_code()


__all__ = [
    "ARCHITECTURE_COMMAND",
    "CONVERGENCE_RECORD_PATH",
    "CONVERGENCE_TRAILER",
    "COORDINATOR_LOCK_KEY",
    "DEFAULT_AGENT_ID",
    "DEFAULT_LOCK_TTL_MINUTES",
    "DRIFT_GATE_COMMAND",
    "FORBIDDEN_COMMANDS",
    "FORBIDDEN_FLAGS",
    "REFRESH_NOT_RUN",
    "SOURCE_COMMIT_TRAILER",
    "SOURCE_OPERATION_RECORD",
    "ActiveAgentChecker",
    "CommandResult",
    "CommandRunner",
    "ConvergenceApparatusError",
    "ConvergenceIdentity",
    "ConvergenceResult",
    "ConvergenceStatus",
    "GuardLayer",
    "GuardResult",
    "GuardState",
    "MergeReversalError",
    "MergedPullRequest",
    "PriorConvergence",
    "ProducerOutcome",
    "RefreshPhase",
    "SemanticIndexRecord",
    "acquire_coordinator_lock",
    "acquire_sync_point_guards",
    "build_commit_message",
    "check_active_agents",
    "enqueue_semantic_index",
    "converge",
    "dry_run",
    "derive_convergence_identity",
    "find_prior_commit_trailer",
    "find_prior_convergence",
    "find_prior_operation_record",
    "guarded_runner",
    "load_merged_pull_requests",
    "main",
    "append_record",
    "build_record",
    "producers_from_summary",
    "refresh_cli_path",
    "render_record_line",
    "semantic_from_summary",
    "validate_record",
    "release_sync_point_guards",
    "resolve_repository_id",
    "reverses_merge",
    "run_architecture_refresh",
    "run_command",
    "run_deterministic_refresh",
    "verify_push_target",
]


if __name__ == "__main__":
    raise SystemExit(main())

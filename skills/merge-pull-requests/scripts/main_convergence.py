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


__all__ = [
    "CONVERGENCE_RECORD_PATH",
    "CONVERGENCE_TRAILER",
    "COORDINATOR_LOCK_KEY",
    "DEFAULT_AGENT_ID",
    "DEFAULT_LOCK_TTL_MINUTES",
    "FORBIDDEN_COMMANDS",
    "FORBIDDEN_FLAGS",
    "SOURCE_COMMIT_TRAILER",
    "SOURCE_OPERATION_RECORD",
    "ActiveAgentChecker",
    "CommandResult",
    "CommandRunner",
    "ConvergenceApparatusError",
    "ConvergenceIdentity",
    "GuardLayer",
    "GuardResult",
    "GuardState",
    "MergeReversalError",
    "PriorConvergence",
    "acquire_coordinator_lock",
    "acquire_sync_point_guards",
    "check_active_agents",
    "derive_convergence_identity",
    "find_prior_commit_trailer",
    "find_prior_convergence",
    "find_prior_operation_record",
    "guarded_runner",
    "release_sync_point_guards",
    "resolve_repository_id",
    "reverses_merge",
    "run_command",
    "verify_push_target",
]

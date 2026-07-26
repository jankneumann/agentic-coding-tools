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


__all__ = [
    "CONVERGENCE_RECORD_PATH",
    "CONVERGENCE_TRAILER",
    "COORDINATOR_LOCK_KEY",
    "FORBIDDEN_COMMANDS",
    "FORBIDDEN_FLAGS",
    "SOURCE_COMMIT_TRAILER",
    "SOURCE_OPERATION_RECORD",
    "CommandResult",
    "CommandRunner",
    "ConvergenceApparatusError",
    "ConvergenceIdentity",
    "MergeReversalError",
    "PriorConvergence",
    "derive_convergence_identity",
    "find_prior_commit_trailer",
    "find_prior_convergence",
    "find_prior_operation_record",
    "guarded_runner",
    "resolve_repository_id",
    "reverses_merge",
    "run_command",
]

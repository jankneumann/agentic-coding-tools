"""The three guard layers that stand between a merge pass and a write to main.

The layer count is not padding. ``checkout_policy``'s own ``approved_sync_point``
message says the caller must still enforce clean-tree and active-agent guards, so
the refresh CLI's ``--sync-point`` flag is only one part of the contract and this
driver owns the rest:

1. **Active agents** -- re-run at Step 11.6, not just at skill start, because an
   agent may have started a worktree during the merge loop. Unable to check is
   *blocked*, never "probably fine".
2. **Coordinator lock** -- degrades with a recorded warning when the coordinator
   is absent, because this repository runs solo often enough that a
   coordinator-only guard would be missing exactly when it matters. Contention,
   however, blocks.
3. **Pre-push compare-and-swap** against ``origin/main`` -- the only layer a
   process that never asked cannot bypass. On a losing race the pass aborts.
   ``--force-with-lease`` was rejected: a lease that succeeds still overwrites
   another writer's commit, and at a sync point losing the race is information.

The lock must also be released on every exit path, including the paths that
block, or a solo failure would wedge every later pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SUITE_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _SUITE_DIR.parents[1]
for _extra in (
    _SKILLS_DIR / "merge-pull-requests" / "scripts",
    _SKILLS_DIR / "project-context-runtime" / "scripts",
    _SKILLS_DIR / "shared",
):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import main_convergence as mc  # noqa: E402

MERGED_SHA = "a" * 40
OTHER_SHA = "b" * 40


class _Recorder:
    """A command runner double that records argv and replays canned results."""

    def __init__(self, results: dict[str, mc.CommandResult] | None = None) -> None:
        self.results = results or {}
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv, cwd):  # noqa: ANN001
        parts = tuple(str(a) for a in argv)
        self.calls.append(parts)
        for key, result in self.results.items():
            if key in " ".join(parts):
                return result
        return mc.CommandResult(argv=parts, returncode=0, stdout="")


def _identity() -> mc.ConvergenceIdentity:
    return mc.ConvergenceIdentity(
        repository_id="repo", merged_revision=MERGED_SHA, operation_id="pcr-" + "0" * 24
    )


# --------------------------------------------------------------------------- #
# Layer 1 -- active agents
# --------------------------------------------------------------------------- #
def test_active_agents_block_the_sync_point(tmp_path: Path) -> None:
    guard = mc.check_active_agents(tmp_path, checker=lambda root: (False, ["agent-a"]))

    assert guard.allowed is False
    assert guard.layer is mc.GuardLayer.ACTIVE_AGENTS
    assert "agent-a" in guard.reason


def test_no_active_agents_permits_the_sync_point(tmp_path: Path) -> None:
    guard = mc.check_active_agents(tmp_path, checker=lambda root: (True, []))

    assert guard.allowed is True
    assert guard.layer is mc.GuardLayer.ACTIVE_AGENTS


def test_an_unavailable_active_agent_check_blocks_rather_than_assumes(
    tmp_path: Path,
) -> None:
    """Unknown is not clear. A guard that cannot run has not run."""

    def _explode(root):  # noqa: ANN001, ARG001
        raise RuntimeError("registry unreadable")

    guard = mc.check_active_agents(tmp_path, checker=_explode)

    assert guard.allowed is False
    assert guard.warnings != ()


# --------------------------------------------------------------------------- #
# Layer 2 -- coordinator lock
# --------------------------------------------------------------------------- #
def test_coordinator_lock_acquired_permits_and_reports_the_hold() -> None:
    guard = mc.acquire_coordinator_lock(
        agent_id="a", acquirer=lambda **kw: {"status": "ok", "operation": "try_lock"}
    )

    assert guard.allowed is True
    assert guard.lock_acquired is True
    assert guard.warnings == ()


def test_absent_coordinator_degrades_with_a_warning_and_never_blocks() -> None:
    guard = mc.acquire_coordinator_lock(
        agent_id="a",
        acquirer=lambda **kw: {
            "status": "skipped",
            "operation": "try_lock",
            "reason": "coordinator_unavailable",
        },
    )

    assert guard.allowed is True
    assert guard.lock_acquired is False
    assert any("coordinator_unavailable" in w for w in guard.warnings)


def test_lock_contention_blocks() -> None:
    guard = mc.acquire_coordinator_lock(
        agent_id="a",
        acquirer=lambda **kw: {"status": "error", "operation": "try_lock", "status_code": 409},
    )

    assert guard.allowed is False
    assert guard.layer is mc.GuardLayer.COORDINATOR_LOCK


def test_a_raising_lock_client_degrades_rather_than_blocking() -> None:
    def _explode(**kw):  # noqa: ANN003
        raise RuntimeError("transport blew up")

    guard = mc.acquire_coordinator_lock(agent_id="a", acquirer=_explode)

    assert guard.allowed is True
    assert guard.lock_acquired is False
    assert guard.warnings != ()


def test_the_lock_key_is_the_documented_sync_point_key() -> None:
    seen: dict = {}

    def _capture(**kw):  # noqa: ANN003
        seen.update(kw)
        return {"status": "ok"}

    mc.acquire_coordinator_lock(agent_id="a", acquirer=_capture)

    assert seen["file_path"] == mc.COORDINATOR_LOCK_KEY
    assert mc.COORDINATOR_LOCK_KEY == "sync-point:main-convergence"


# --------------------------------------------------------------------------- #
# Layer 3 -- pre-push compare-and-swap
# --------------------------------------------------------------------------- #
def test_matching_origin_main_permits_the_push(tmp_path: Path) -> None:
    runner = _Recorder({"rev-parse": mc.CommandResult(argv=(), returncode=0, stdout=MERGED_SHA)})

    guard = mc.verify_push_target(tmp_path, _identity(), runner=runner)

    assert guard.allowed is True
    assert guard.observed_revision == MERGED_SHA


def test_a_lost_push_race_aborts_and_never_forces(tmp_path: Path) -> None:
    runner = _Recorder({"rev-parse": mc.CommandResult(argv=(), returncode=0, stdout=OTHER_SHA)})

    guard = mc.verify_push_target(tmp_path, _identity(), runner=runner)

    assert guard.allowed is False
    assert guard.layer is mc.GuardLayer.PUSH_COMPARE_AND_SWAP
    assert guard.observed_revision == OTHER_SHA
    flat = [" ".join(call) for call in runner.calls]
    assert not any("--force" in line for line in flat)
    assert not any("--force-with-lease" in line for line in flat)
    assert not any("push" in line for line in flat)


def test_an_unreadable_push_target_blocks(tmp_path: Path) -> None:
    """A failed read blocks *as unreadable*, not incidentally as a lost race.

    The distinction is load-bearing: git echoes text on stdout while exiting
    non-zero, so a driver that only compared strings would classify a broken
    read as a race -- and, when the echoed text happened to match, as agreement.
    """
    runner = _Recorder(
        {"rev-parse": mc.CommandResult(argv=(), returncode=128, stdout=MERGED_SHA)}
    )

    guard = mc.verify_push_target(tmp_path, _identity(), runner=runner)

    assert guard.allowed is False
    assert guard.reason.startswith("push_target_unreadable")


def test_an_empty_push_target_read_blocks(tmp_path: Path) -> None:
    runner = _Recorder({"rev-parse": mc.CommandResult(argv=(), returncode=0, stdout="")})

    guard = mc.verify_push_target(tmp_path, _identity(), runner=runner)

    assert guard.allowed is False
    assert guard.reason.startswith("push_target_unreadable")


def test_a_failed_fetch_blocks_rather_than_comparing_a_stale_ref(tmp_path: Path) -> None:
    runner = _Recorder(
        {
            "fetch": mc.CommandResult(argv=(), returncode=1, stderr="network down"),
            "rev-parse": mc.CommandResult(argv=(), returncode=0, stdout=MERGED_SHA),
        }
    )

    guard = mc.verify_push_target(tmp_path, _identity(), runner=runner)

    assert guard.allowed is False
    assert guard.reason.startswith("push_target_unreadable")
    assert not any("rev-parse" in " ".join(call) for call in runner.calls)


# --------------------------------------------------------------------------- #
# The apparatus cannot issue a history-overwriting command at all
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "argv",
    [
        ["git", "push", "--force", "origin", "main"],
        ["git", "push", "--force-with-lease", "origin", "main"],
        ["git", "push", "-f", "origin", "main"],
        ["git", "revert", "--no-edit", "HEAD"],
        ["git", "reset", "--hard", "origin/main"],
        ["gh", "pr", "close", "42"],
        ["gh", "pr", "reopen", "42"],
    ],
)
def test_history_overwriting_commands_are_refused_before_dispatch(argv, tmp_path) -> None:  # noqa: ANN001
    assert mc.reverses_merge(argv) is True

    def _never_called(a, c):  # noqa: ANN001, ARG001
        raise AssertionError("the guarded runner must not dispatch this command")

    with pytest.raises(mc.MergeReversalError):
        mc.guarded_runner(_never_called)(argv, tmp_path)


@pytest.mark.parametrize(
    "argv",
    [
        ["git", "push", "origin", "HEAD:main"],
        ["git", "fetch", "origin", "main"],
        ["git", "commit", "-m", "chore(context): converge main"],
        ["make", "architecture-refresh"],
    ],
)
def test_ordinary_convergence_commands_pass_the_guard(argv, tmp_path: Path) -> None:  # noqa: ANN001
    assert mc.reverses_merge(argv) is False
    runner = _Recorder()
    assert mc.guarded_runner(runner)(argv, tmp_path).returncode == 0


# --------------------------------------------------------------------------- #
# Composite acquire/release
# --------------------------------------------------------------------------- #
def test_all_three_layers_hold_on_the_happy_path(tmp_path: Path) -> None:
    runner = _Recorder({"rev-parse": mc.CommandResult(argv=(), returncode=0, stdout=MERGED_SHA)})
    state = mc.acquire_sync_point_guards(
        tmp_path,
        agent_id="a",
        active_agent_checker=lambda root: (True, []),
        lock_acquirer=lambda **kw: {"status": "ok"},
    )

    assert state.allowed is True
    assert state.lock_acquired is True

    swap = mc.verify_push_target(tmp_path, _identity(), runner=runner)
    assert swap.allowed is True


def test_layer_one_failure_never_reaches_the_coordinator(tmp_path: Path) -> None:
    def _lock(**kw):  # noqa: ANN003
        raise AssertionError("layer 2 must not run after layer 1 blocked")

    state = mc.acquire_sync_point_guards(
        tmp_path,
        agent_id="a",
        active_agent_checker=lambda root: (False, ["agent-a"]),
        lock_acquirer=_lock,
    )

    assert state.allowed is False
    assert state.blocked_by is mc.GuardLayer.ACTIVE_AGENTS
    assert state.lock_acquired is False


def test_the_lock_is_released_even_when_a_later_layer_blocks(tmp_path: Path) -> None:
    released: list[str] = []
    state = mc.acquire_sync_point_guards(
        tmp_path,
        agent_id="agent-x",
        active_agent_checker=lambda root: (True, []),
        lock_acquirer=lambda **kw: {"status": "ok"},
    )
    assert state.lock_acquired is True

    mc.release_sync_point_guards(
        state,
        agent_id="agent-x",
        releaser=lambda **kw: released.append(kw["file_path"]) or {"status": "ok"},
    )

    assert released == [mc.COORDINATOR_LOCK_KEY]


def test_release_is_a_no_op_when_no_lock_was_held(tmp_path: Path) -> None:
    def _release(**kw):  # noqa: ANN003
        raise AssertionError("nothing was locked, so nothing may be released")

    state = mc.acquire_sync_point_guards(
        tmp_path,
        agent_id="a",
        active_agent_checker=lambda root: (True, []),
        lock_acquirer=lambda **kw: {"status": "skipped", "reason": "coordinator_unavailable"},
    )
    assert state.lock_acquired is False

    assert mc.release_sync_point_guards(state, agent_id="a", releaser=_release) == ()


def test_release_failure_is_a_warning_not_an_exception(tmp_path: Path) -> None:
    def _release(**kw):  # noqa: ANN003
        raise RuntimeError("coordinator went away")

    state = mc.acquire_sync_point_guards(
        tmp_path,
        agent_id="a",
        active_agent_checker=lambda root: (True, []),
        lock_acquirer=lambda **kw: {"status": "ok"},
    )

    warnings = mc.release_sync_point_guards(state, agent_id="a", releaser=_release)

    assert warnings != ()

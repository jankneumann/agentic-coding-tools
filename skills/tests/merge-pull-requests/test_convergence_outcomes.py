"""Convergence outcomes, and the one thing convergence may never do (ri-11 D6).

A merge is terminal. Convergence is strictly downstream of it, so no convergence
outcome -- not a failed producer, not a lost push race, not a wedged coordinator
-- may revert, close, or reopen a pull request, and none may block the merge from
being reported. Reverting a merge to fix a *derived artifact* would trade
reviewed, CI-green product code for a regeneration problem.

That is asserted three ways here, because a comment saying so is worth nothing:

* structurally, on the module source -- no merge-reversing command literal exists
  in it at all;
* by dispatch, on every command actually issued in every failure scenario;
* by outcome, that each failure path still returns a result the pass can report
  alongside its merges rather than in place of them.

The outcome table itself is D6's. Exit 2 must still commit: ``degraded`` is the
NORMAL result whenever the semantic index is deferred or an optional owner is
absent, so treating it as failure would mean convergence never commits on a
machine without the semantic stack. A ``failed`` refresh still commits the
already-staged cleanup output but must not sweep the failed run's partial
artifacts in with it.
"""

from __future__ import annotations

import json
import re
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
CONVERGED_SHA = "c" * 40
FOREIGN_SHA = "f" * 40

REFRESH_SUMMARY = {
    "operation_id": "pcr-" + "1" * 24,
    "outcome": "degraded",
    "manifest_path": ".git-context/context-refresh-manifest.json",
    "manifest_sha256": "d" * 64,
    "semantic_index": {
        "status": "pending",
        "requested_revision": MERGED_SHA,
        "operation_id": None,
        "registry_record_id": None,
        "indexed_revision": None,
        "fallback": {"kind": "exact-search", "reason": "deferred"},
    },
    "producer_results": [
        {
            "producer_id": "documentation.inventory",
            "producer_version": "1",
            "status": "fresh",
            "artifacts": [],
            "validations": [],
            "remediation": [],
            "owner": "docs-team",
        }
    ],
}


class _FakeRepo:
    """A scripted git/make/refresh environment that records every command."""

    def __init__(
        self,
        *,
        head: str = MERGED_SHA,
        refresh_exit: int = 0,
        refresh_stdout: str | None = None,
        origin_main: str | None = None,
        staged: bool = True,
        push_returncode: int = 0,
        architecture_returncode: int = 0,
        trailer_sha: str | None = None,
        trailer_operation_id: str | None = None,
    ) -> None:
        self.head = head
        self.refresh_exit = refresh_exit
        self.refresh_stdout = (
            refresh_stdout if refresh_stdout is not None else json.dumps(REFRESH_SUMMARY)
        )
        self.origin_main = origin_main or head
        self.staged = staged
        self.push_returncode = push_returncode
        self.architecture_returncode = architecture_returncode
        self.trailer_sha = trailer_sha
        self.trailer_operation_id = trailer_operation_id
        self.calls: list[tuple[str, ...]] = []
        self.commit_messages: list[str] = []

    # -- helpers ---------------------------------------------------------- #
    @property
    def flat(self) -> list[str]:
        return [" ".join(call) for call in self.calls]

    def issued(self, fragment: str) -> list[str]:
        return [line for line in self.flat if fragment in line]

    def __call__(self, argv, cwd):  # noqa: ANN001
        parts = tuple(str(a) for a in argv)
        self.calls.append(parts)
        line = " ".join(parts)

        def ok(stdout: str = "", rc: int = 0) -> mc.CommandResult:
            return mc.CommandResult(argv=parts, returncode=rc, stdout=stdout)

        if "architecture-refresh" in line:
            return ok(rc=self.architecture_returncode)
        if "refresh" in line and "--sync-point" in line:
            return mc.CommandResult(
                argv=parts, returncode=self.refresh_exit, stdout=self.refresh_stdout
            )
        if parts[:2] == ("git", "log") and any(p.startswith("--grep=") for p in parts):
            return ok(self.trailer_sha or "")
        if parts[:2] == ("git", "log"):
            if self.trailer_operation_id:
                return ok(
                    "chore(context): converge main\n\n"
                    f"{mc.CONVERGENCE_TRAILER}: {self.trailer_operation_id}\n"
                )
            return ok("")
        if parts[:3] == ("git", "rev-parse", "--show-toplevel"):
            return ok(str(cwd))
        if parts[:3] == ("git", "rev-parse", "HEAD"):
            return ok(self.head)
        if parts[:2] == ("git", "rev-parse"):
            return ok(self.origin_main)
        if parts[:2] == ("git", "fetch"):
            return ok()
        if parts[:2] == ("git", "add"):
            return ok()
        if parts[:2] == ("git", "diff"):
            # ``--quiet`` exits 1 when the index differs from HEAD.
            return ok(rc=1 if self.staged else 0)
        if parts[:2] == ("git", "commit"):
            self.commit_messages.append(parts[parts.index("-m") + 1])
            self.head = CONVERGED_SHA
            return ok()
        if parts[:2] == ("git", "push"):
            return ok(rc=self.push_returncode)
        return ok()


def _prs(*numbers: int) -> tuple[mc.MergedPullRequest, ...]:
    return tuple(
        mc.MergedPullRequest(number=n, origin="openspec", change_id=f"change-{n}")
        for n in numbers
    )


class _NoStore:
    """A ledger with no record for anything: conclusive, not converged."""

    base_dir = "/nonexistent-ledger"

    def load(self, operation_id: str):  # noqa: ANN201
        raise RuntimeError("no operation record")


def _converge(repo: Path, fake: _FakeRepo, **kwargs):  # noqa: ANN201
    kwargs.setdefault("store", _NoStore())
    kwargs.setdefault("active_agent_checker", lambda root: (True, []))
    kwargs.setdefault("lock_acquirer", lambda **kw: {"status": "ok"})
    kwargs.setdefault("lock_releaser", lambda **kw: {"status": "ok"})
    kwargs.setdefault("semantic_enqueuer", lambda repository, revision: None)
    kwargs.setdefault("merged_pull_requests", _prs(42))
    kwargs.setdefault("merged_revision", MERGED_SHA)
    return mc.converge(repo, runner=fake, **kwargs)


# --------------------------------------------------------------------------- #
# The structural guarantee
# --------------------------------------------------------------------------- #
def test_the_module_contains_no_merge_reversing_command_at_all() -> None:
    source = (_SKILLS_DIR / "merge-pull-requests" / "scripts" / "main_convergence.py").read_text(
        encoding="utf-8"
    )
    # Strip the declared deny-list and the guard's own docstrings: the point is
    # that no *call site* constructs one of these, not that the words are absent.
    body = source.split("def reverses_merge", 1)[1]
    body = body.split("def guarded_runner", 1)[1]
    for forbidden in ('"revert"', '"close"', '"reopen"', '"--force"', '"--force-with-lease"'):
        assert forbidden not in body, f"convergence must never construct {forbidden}"


@pytest.mark.parametrize(
    "scenario",
    ["happy", "degraded", "refresh_failed", "push_race", "blocked_agents", "already_converged"],
)
def test_no_scenario_issues_a_merge_reversing_command(tmp_path: Path, scenario: str) -> None:
    fake = _FakeRepo(
        refresh_exit={"refresh_failed": 1, "degraded": 2}.get(scenario, 0),
        origin_main=FOREIGN_SHA if scenario == "push_race" else None,
    )
    kwargs = {}
    if scenario == "blocked_agents":
        kwargs["active_agent_checker"] = lambda root: (False, ["agent-a"])
    if scenario == "already_converged":
        fake.trailer_sha = CONVERGED_SHA
        fake.trailer_operation_id = mc.derive_convergence_identity(
            tmp_path, merged_revision=MERGED_SHA, environ={}
        ).operation_id

    _converge(tmp_path, fake, environ={}, **kwargs)

    for call in fake.calls:
        assert mc.reverses_merge(call) is False, f"issued {call}"


# --------------------------------------------------------------------------- #
# D8 -- exactly one convergence per pass, and none at all for k = 0
# --------------------------------------------------------------------------- #
def test_a_pass_that_merged_nothing_converges_nothing(tmp_path: Path) -> None:
    fake = _FakeRepo()

    result = _converge(tmp_path, fake, merged_pull_requests=(), environ={})

    assert result.status is mc.ConvergenceStatus.NO_MERGES
    assert result.convergence_commit is None
    assert fake.issued("commit") == []
    assert fake.issued("push") == []


def test_two_merged_prs_produce_exactly_one_commit_and_one_push(tmp_path: Path) -> None:
    fake = _FakeRepo()

    result = _converge(tmp_path, fake, merged_pull_requests=_prs(42, 43), environ={})

    assert result.status is mc.ConvergenceStatus.CONVERGED
    assert len(fake.issued("git commit")) == 1
    assert len(fake.issued("git push")) == 1
    assert len(fake.issued("architecture-refresh")) == 1
    assert len(fake.issued("--sync-point")) == 1


def test_the_convergence_commit_carries_the_operation_trailer(tmp_path: Path) -> None:
    fake = _FakeRepo()

    result = _converge(tmp_path, fake, environ={})

    assert len(fake.commit_messages) == 1
    message = fake.commit_messages[0]
    assert f"{mc.CONVERGENCE_TRAILER}: {result.identity.operation_id}" in message
    trailer_lines = [
        line for line in message.splitlines() if line.startswith(mc.CONVERGENCE_TRAILER)
    ]
    assert len(trailer_lines) == 1


def test_the_refresh_is_invoked_with_both_sync_point_flags(tmp_path: Path) -> None:
    fake = _FakeRepo()

    _converge(tmp_path, fake, environ={})

    refresh = [call for call in fake.calls if "--sync-point" in call]
    assert len(refresh) == 1
    assert "--defer-semantic-index" in refresh[0]
    assert "refresh" in refresh[0]


def test_the_staged_architecture_target_is_used_not_the_generation_target(
    tmp_path: Path,
) -> None:
    """Provenance is written only by the staged target; ri-10 routes missing
    provenance to drift, so `make architecture` would leave the gate red."""
    fake = _FakeRepo()

    _converge(tmp_path, fake, environ={})

    assert ("make", "architecture-refresh") in fake.calls
    assert ("make", "architecture") not in fake.calls


# --------------------------------------------------------------------------- #
# D6 -- the outcome table
# --------------------------------------------------------------------------- #
def test_a_succeeded_refresh_commits_and_exits_zero(tmp_path: Path) -> None:
    result = _converge(tmp_path, _FakeRepo(refresh_exit=0), environ={})

    assert result.status is mc.ConvergenceStatus.CONVERGED
    assert result.refresh_status == "succeeded"
    assert result.convergence_commit == CONVERGED_SHA
    assert result.exit_code() == 0


def test_a_degraded_refresh_still_commits_and_pushes(tmp_path: Path) -> None:
    """Exit 2 is the NORMAL outcome for a deferred index. It must still land."""
    fake = _FakeRepo(refresh_exit=2)

    result = _converge(tmp_path, fake, environ={})

    assert result.status is mc.ConvergenceStatus.CONVERGED
    assert result.refresh_status == "degraded"
    assert len(fake.issued("git commit")) == 1
    assert len(fake.issued("git push")) == 1
    assert result.exit_code() == 2


def test_a_failed_refresh_commits_cleanup_only_and_never_unmerges(tmp_path: Path) -> None:
    fake = _FakeRepo(refresh_exit=1)

    result = _converge(tmp_path, fake, environ={})

    assert result.refresh_status == "failed"
    assert len(fake.issued("git commit")) == 1
    # The failed run's partial artifacts are NOT swept into the commit.
    assert fake.issued("git add -A") == []
    assert result.warnings != ()
    assert result.exit_code() == 1
    assert fake.issued("revert") == []


def test_a_succeeded_refresh_does_sweep_its_output_into_the_commit(tmp_path: Path) -> None:
    fake = _FakeRepo(refresh_exit=0)

    _converge(tmp_path, fake, environ={})

    assert fake.issued("git add -A") != []


def test_an_architecture_failure_degrades_with_a_warning(tmp_path: Path) -> None:
    fake = _FakeRepo(architecture_returncode=1)

    result = _converge(tmp_path, fake, environ={})

    assert result.status is mc.ConvergenceStatus.CONVERGED
    assert any("architecture" in w for w in result.warnings)


def test_a_lost_push_race_aborts_without_pushing_and_leaves_work_resumable(
    tmp_path: Path,
) -> None:
    fake = _FakeRepo(origin_main=FOREIGN_SHA)

    result = _converge(tmp_path, fake, environ={})

    assert result.status is mc.ConvergenceStatus.BLOCKED
    assert "push_race_lost" in (result.reason or "")
    assert fake.issued("git push") == []
    assert not any("--force" in line for line in fake.flat)


def test_a_failed_push_is_reported_and_never_retried_with_force(tmp_path: Path) -> None:
    fake = _FakeRepo(push_returncode=1)

    result = _converge(tmp_path, fake, environ={})

    assert result.status is mc.ConvergenceStatus.BLOCKED
    assert len(fake.issued("git push")) == 1
    assert not any("--force" in line for line in fake.flat)


def test_active_agents_block_before_anything_is_written(tmp_path: Path) -> None:
    fake = _FakeRepo()

    result = _converge(tmp_path, fake, environ={}, active_agent_checker=lambda root: (False, ["a"]))

    assert result.status is mc.ConvergenceStatus.BLOCKED
    assert fake.issued("git commit") == []
    assert fake.issued("git push") == []
    assert fake.issued("architecture-refresh") == []


def test_nothing_to_commit_still_reports_converged_and_pushes_nothing(
    tmp_path: Path,
) -> None:
    fake = _FakeRepo(staged=False)

    result = _converge(tmp_path, fake, environ={})

    assert result.status is mc.ConvergenceStatus.CONVERGED
    assert result.convergence_commit is None
    assert fake.issued("git commit") == []
    assert fake.issued("git push") == []


# --------------------------------------------------------------------------- #
# Idempotence, end to end
# --------------------------------------------------------------------------- #
def test_a_retry_after_a_landed_convergence_does_nothing(tmp_path: Path) -> None:
    identity = mc.derive_convergence_identity(tmp_path, merged_revision=MERGED_SHA, environ={})
    fake = _FakeRepo(trailer_sha=CONVERGED_SHA, trailer_operation_id=identity.operation_id)

    result = _converge(tmp_path, fake, environ={})

    assert result.status is mc.ConvergenceStatus.ALREADY_CONVERGED
    assert result.identity == identity
    assert result.convergence_commit == CONVERGED_SHA
    assert fake.issued("git commit") == []
    assert fake.issued("git push") == []
    assert fake.issued("--sync-point") == []
    assert result.exit_code() == 0


def test_an_inconclusive_idempotence_check_blocks_rather_than_converging_twice(
    tmp_path: Path,
) -> None:
    class _UnreadableStore:
        def load(self, operation_id: str):  # noqa: ANN201, ARG002
            raise OSError("ledger unreadable")

    fake = _FakeRepo()

    def _runner(argv, cwd):  # noqa: ANN001
        parts = tuple(str(a) for a in argv)
        if parts[:2] == ("git", "log"):
            fake.calls.append(parts)
            return mc.CommandResult(argv=parts, returncode=128)
        return fake(argv, cwd)

    result = mc.converge(
        tmp_path,
        runner=_runner,
        store=_UnreadableStore(),
        environ={},
        merged_revision=MERGED_SHA,
        merged_pull_requests=_prs(42),
        active_agent_checker=lambda root: (True, []),
        lock_acquirer=lambda **kw: {"status": "ok"},
        lock_releaser=lambda **kw: {"status": "ok"},
        semantic_enqueuer=lambda repository, revision: None,
    )

    assert result.status is mc.ConvergenceStatus.BLOCKED
    assert "inconclusive" in (result.reason or "")
    assert fake.issued("git commit") == []
    assert fake.issued("git push") == []


# --------------------------------------------------------------------------- #
# The lock is never leaked
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"origin_main": FOREIGN_SHA},
        {"refresh_exit": 1},
        {"push_returncode": 1},
    ],
)
def test_the_coordinator_lock_is_released_on_every_exit_path(tmp_path: Path, kwargs) -> None:  # noqa: ANN001
    released: list[str] = []
    fake = _FakeRepo(**kwargs)

    _converge(
        tmp_path,
        fake,
        environ={},
        lock_releaser=lambda **kw: released.append(kw["file_path"]) or {"status": "ok"},
    )

    assert released == [mc.COORDINATOR_LOCK_KEY]


def test_a_crashing_phase_still_releases_the_lock_and_reports(tmp_path: Path) -> None:
    released: list[str] = []

    def _explode(argv, cwd):  # noqa: ANN001
        if "architecture-refresh" in " ".join(str(a) for a in argv):
            raise OSError("make is not installed")
        return _FakeRepo()(argv, cwd)

    result = mc.converge(
        tmp_path,
        runner=_explode,
        store=_NoStore(),
        environ={},
        merged_revision=MERGED_SHA,
        merged_pull_requests=_prs(42),
        active_agent_checker=lambda root: (True, []),
        lock_acquirer=lambda **kw: {"status": "ok"},
        lock_releaser=lambda **kw: released.append(kw["file_path"]) or {"status": "ok"},
        semantic_enqueuer=lambda repository, revision: None,
    )

    assert released == [mc.COORDINATOR_LOCK_KEY]
    assert result.status is mc.ConvergenceStatus.BLOCKED


# --------------------------------------------------------------------------- #
# Semantic index: enqueued for the pushed revision, never awaited (D7)
# --------------------------------------------------------------------------- #
class _FakeStore:
    """Records every enqueue, so "exactly one" is measurable."""

    def __init__(self, *, explode: bool = False) -> None:
        self.explode = explode
        self.enqueued: list[tuple[str, str]] = []

    base_dir = "/nonexistent-ledger"

    def load(self, operation_id: str):  # noqa: ANN201, ARG002
        raise RuntimeError("no operation record")

    def create_or_load(self, repository_id: str, source_revision: str):  # noqa: ANN201
        if self.explode:
            raise RuntimeError("the indexing service is unreachable")
        self.enqueued.append((repository_id, source_revision))

        class _Record:
            operation_id = "pcr-" + "9" * 24

        return _Record()


def test_the_index_is_enqueued_for_the_pushed_revision_not_the_merged_one(
    tmp_path: Path,
) -> None:
    """The convergence commit moves main's tip; indexing the pre-convergence
    revision would be stale on arrival and force a second index."""
    store = _FakeStore()

    reference = mc.enqueue_semantic_index(
        tmp_path, CONVERGED_SHA, repository_id="repo", store=store
    )

    assert store.enqueued == [("repo", CONVERGED_SHA)]
    assert CONVERGED_SHA != MERGED_SHA
    assert reference.status == "pending"
    assert reference.requested_revision == CONVERGED_SHA
    assert reference.operation_id == "pcr-" + "9" * 24
    assert reference.fallback and "exact" in reference.fallback


def test_an_unavailable_index_service_never_reports_success(tmp_path: Path) -> None:
    """Never fail open: an enqueue that did not happen is not 'pending'."""
    reference = mc.enqueue_semantic_index(
        tmp_path, CONVERGED_SHA, repository_id="repo", store=_FakeStore(explode=True)
    )

    assert reference.status == "failed"
    assert reference.operation_id is None
    assert reference.fallback


def test_an_unavailable_index_service_still_lets_the_pass_complete(tmp_path: Path) -> None:
    fake = _FakeRepo()
    store = _FakeStore(explode=True)

    result = mc.converge(
        tmp_path,
        runner=fake,
        store=store,
        environ={},
        merged_revision=MERGED_SHA,
        merged_pull_requests=_prs(42),
        active_agent_checker=lambda root: (True, []),
        lock_acquirer=lambda **kw: {"status": "ok"},
        lock_releaser=lambda **kw: {"status": "ok"},
    )

    assert result.status is mc.ConvergenceStatus.CONVERGED
    assert len(fake.issued("git push")) == 1
    assert result.record["semantic_index"]["status"] == "failed"


def test_exactly_one_index_request_per_pass(tmp_path: Path) -> None:
    fake = _FakeRepo()
    store = _FakeStore()

    mc.converge(
        tmp_path,
        runner=fake,
        store=store,
        environ={},
        merged_revision=MERGED_SHA,
        merged_pull_requests=_prs(42, 43, 44),
        active_agent_checker=lambda root: (True, []),
        lock_acquirer=lambda **kw: {"status": "ok"},
        lock_releaser=lambda **kw: {"status": "ok"},
    )

    assert len(store.enqueued) == 1
    assert store.enqueued[0][1] == CONVERGED_SHA


def test_a_retry_makes_no_second_index_request(tmp_path: Path) -> None:
    identity = mc.derive_convergence_identity(tmp_path, merged_revision=MERGED_SHA, environ={})
    fake = _FakeRepo(trailer_sha=CONVERGED_SHA, trailer_operation_id=identity.operation_id)
    store = _FakeStore()

    result = mc.converge(
        tmp_path,
        runner=fake,
        store=store,
        environ={},
        merged_revision=MERGED_SHA,
        merged_pull_requests=_prs(42),
        active_agent_checker=lambda root: (True, []),
        lock_acquirer=lambda **kw: {"status": "ok"},
        lock_releaser=lambda **kw: {"status": "ok"},
    )

    assert result.status is mc.ConvergenceStatus.ALREADY_CONVERGED
    assert store.enqueued == []


def test_a_blocked_pass_makes_no_index_request(tmp_path: Path) -> None:
    fake = _FakeRepo(origin_main=FOREIGN_SHA)
    store = _FakeStore()

    mc.converge(
        tmp_path,
        runner=fake,
        store=store,
        environ={},
        merged_revision=MERGED_SHA,
        merged_pull_requests=_prs(42),
        active_agent_checker=lambda root: (True, []),
        lock_acquirer=lambda **kw: {"status": "ok"},
        lock_releaser=lambda **kw: {"status": "ok"},
    )

    assert store.enqueued == []


# --------------------------------------------------------------------------- #
# Dry run (D12)
# --------------------------------------------------------------------------- #
def test_a_dry_run_writes_nothing_at_all(tmp_path: Path) -> None:
    """A dry run that dirties main is not a dry run. The mutating refresh path
    writes producer output into the working tree, so it must not be reached."""
    fake = _FakeRepo()

    result = mc.converge(
        tmp_path,
        runner=fake,
        store=_NoStore(),
        environ={},
        merged_pull_requests=_prs(42),
        dry_run=True,
    )

    assert result.status is mc.ConvergenceStatus.DRY_RUN
    assert fake.issued("git commit") == []
    assert fake.issued("git push") == []
    assert fake.issued("git add") == []
    assert fake.issued("architecture-refresh") == []
    assert fake.issued("--sync-point") == []
    assert not (tmp_path / mc.CONVERGENCE_RECORD_PATH).exists()
    assert result.exit_code() == 0


def test_a_dry_run_reports_the_identity_it_would_have_used(tmp_path: Path) -> None:
    fake = _FakeRepo()

    result = mc.dry_run(tmp_path, runner=fake, store=_NoStore(), environ={})

    assert result.identity is not None
    assert result.identity.merged_revision == MERGED_SHA
    assert result.identity.operation_id.startswith("pcr-")
    assert result.prior is not None
    assert result.prior.found is False


def test_a_dry_run_reports_an_existing_convergence(tmp_path: Path) -> None:
    identity = mc.derive_convergence_identity(tmp_path, merged_revision=MERGED_SHA, environ={})
    fake = _FakeRepo(trailer_sha=CONVERGED_SHA, trailer_operation_id=identity.operation_id)

    result = mc.dry_run(tmp_path, runner=fake, store=_NoStore(), environ={})

    assert result.prior.found is True
    assert result.prior.convergence_commit == CONVERGED_SHA


def test_a_dry_run_runs_the_read_only_drift_gate(tmp_path: Path) -> None:
    fake = _FakeRepo()

    result = mc.dry_run(tmp_path, runner=fake, store=_NoStore(), environ={})

    assert ("make", "context-drift-gate") in fake.calls
    assert result.drift is not None
    assert result.drift["exit_code"] == 0
    assert result.drift["verdict"] == "fresh"


def test_a_dry_run_reports_drift_without_failing(tmp_path: Path) -> None:
    class _Drifted(_FakeRepo):
        def __call__(self, argv, cwd):  # noqa: ANN001
            parts = tuple(str(a) for a in argv)
            if parts == ("make", "context-drift-gate"):
                self.calls.append(parts)
                return mc.CommandResult(argv=parts, returncode=2)
            return super().__call__(argv, cwd)

    fake = _Drifted()
    result = mc.dry_run(tmp_path, runner=fake, store=_NoStore(), environ={})

    assert result.drift["verdict"] == "drift"
    assert result.exit_code() == 0


def test_a_dry_run_never_treats_an_unreadable_gate_as_fresh(tmp_path: Path) -> None:
    class _Broken(_FakeRepo):
        def __call__(self, argv, cwd):  # noqa: ANN001
            parts = tuple(str(a) for a in argv)
            if parts == ("make", "context-drift-gate"):
                self.calls.append(parts)
                return mc.CommandResult(argv=parts, returncode=1)
            return super().__call__(argv, cwd)

    result = mc.dry_run(tmp_path, runner=_Broken(), store=_NoStore(), environ={})

    assert result.drift["verdict"] == "apparatus-failure"


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #
def test_the_commit_message_is_deterministic_for_one_input(tmp_path: Path) -> None:
    first = _FakeRepo()
    second = _FakeRepo()
    _converge(tmp_path, first, environ={}, merged_pull_requests=_prs(43, 42))
    _converge(tmp_path, second, environ={}, merged_pull_requests=_prs(43, 42))

    assert first.commit_messages == second.commit_messages
    assert not re.search(r"\d{4}-\d{2}-\d{2}T", first.commit_messages[0])

"""Merge-queue path: detection, enqueue, outcome polling, backend selection.

``gh pr merge`` has no queue flag. A queue-required branch takes no strategy
and enqueues; these tests pin that contract and the rule that a PR the queue
drops is reported as failed, never merged directly.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "merge-pull-requests" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import merge_backend as mb
import merge_pr as mp


def _proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


def _no_sleep(_seconds: float) -> None:
    return None


class TestMergeQueueRequired:
    def test_true_when_rule_present(self) -> None:
        rules = json.dumps([{"type": "pull_request"}, {"type": "merge_queue"}])
        with patch.object(mp, "run_gh", return_value=rules) as run:
            assert mp.merge_queue_required("main") is True
        assert run.call_args.args[0] == ["api", "repos/:owner/:repo/rules/branches/main"]

    def test_false_without_rule(self) -> None:
        with patch.object(mp, "run_gh", return_value='[{"type": "pull_request"}]'):
            assert mp.merge_queue_required("main") is False

    @pytest.mark.parametrize("raw", ["not json", "{}", "null"])
    def test_false_on_unexpected_payload(self, raw: str) -> None:
        with patch.object(mp, "run_gh", return_value=raw):
            assert mp.merge_queue_required("main") is False

    @pytest.mark.parametrize(
        "exc", [RuntimeError("403"), subprocess.TimeoutExpired("gh", 1)]
    )
    def test_false_on_lookup_failure(self, exc: Exception) -> None:
        with patch.object(mp, "run_gh", side_effect=exc):
            assert mp.merge_queue_required("main") is False

    def test_false_for_empty_branch(self) -> None:
        with patch.object(mp, "run_gh") as run:
            assert mp.merge_queue_required("") is False
        run.assert_not_called()

    def test_has_merge_queue_resolves_base_branch(self) -> None:
        with patch.object(mp, "run_gh", return_value="release\n"), \
                patch.object(mp, "merge_queue_required", return_value=True) as req:
            assert mp._has_merge_queue(7) is True
        req.assert_called_once_with("release")

    def test_has_merge_queue_false_when_base_lookup_fails(self) -> None:
        with patch.object(mp, "run_gh", side_effect=RuntimeError("boom")):
            assert mp._has_merge_queue(7) is False


class TestAwaitQueueOutcome:
    @staticmethod
    def _views(*views: dict):
        """Successive ``gh pr view`` payloads, the last one repeating."""
        it = iter(views)
        last: list[dict] = []

        def fake(*_a, **_k):
            try:
                last[:] = [next(it)]
            except StopIteration:
                pass
            return json.dumps(last[0])

        return fake

    OPEN = {"state": "OPEN", "autoMergeRequest": None}
    ARMED = {"state": "OPEN", "autoMergeRequest": {"enabledAt": "t"}}

    def _wait(self, views, membership, **kw):
        answers = iter(membership)
        with patch.object(mp, "run_gh", self._views(*views)), \
                patch.object(mp, "_in_merge_queue", lambda _n: next(answers)):
            return mp._await_queue_outcome(1, kw.pop("poll", 60), sleep=_no_sleep, **kw)

    def test_merged(self) -> None:
        out = self._wait([self.OPEN, {"state": "MERGED"}], [True])
        assert out == ("merged", "merged")

    def test_closed(self) -> None:
        assert self._wait([{"state": "CLOSED"}], [])[0] == "closed"

    def test_removed_after_membership_then_two_misses(self) -> None:
        out = self._wait([self.OPEN], [True, False, False])
        assert out == ("removed", "removed")

    def test_single_miss_is_not_removal(self) -> None:
        out = self._wait([self.OPEN], [True, False, True, False, True, True])
        assert out == ("pending", "enqueued")

    def test_never_seen_in_queue_is_never_removal(self) -> None:
        """Auto-merge armed, checks pending: the PR is not queued yet."""
        out = self._wait([self.ARMED], [False] * 6)
        assert out == ("pending", "auto_merge_pending")

    def test_armed_then_queued_then_merged(self) -> None:
        out = self._wait(
            [self.ARMED, self.ARMED, {"state": "MERGED"}], [False, True],
        )
        assert out == ("merged", "merged")

    def test_unavailable_membership_never_means_removal(self) -> None:
        out = self._wait([self.OPEN], [None] * 6)
        assert out == ("pending", "enqueued")

    def test_state_lookup_errors_are_skipped(self) -> None:
        with patch.object(mp, "run_gh", side_effect=RuntimeError("flaky")):
            out = mp._await_queue_outcome(1, 30, sleep=_no_sleep)
        assert out == ("pending", "enqueued")

    def test_sleeps_between_polls_and_stops_at_deadline(self) -> None:
        sleeps: list[float] = []
        with patch.object(mp, "run_gh", self._views(self.OPEN)), \
                patch.object(mp, "_in_merge_queue", return_value=True):
            mp._await_queue_outcome(1, 30, sleep=sleeps.append, interval=10)
        assert sleeps == [10, 10, 10]


class TestInMergeQueue:
    def test_reads_graphql_flag(self) -> None:
        payload = {"data": {"repository": {"pullRequest": {"isInMergeQueue": True}}}}
        with patch.object(mp, "run_gh", return_value=json.dumps(payload)) as run:
            assert mp._in_merge_queue(5) is True
        args = run.call_args.args[0]
        assert args[:3] == ["api", "graphql", "-f"]
        assert "number=5" in args

    @pytest.mark.parametrize(
        "raw", ["not json", "{}", '{"errors": [{"message": "x"}], "data": null}']
    )
    def test_none_when_answer_unavailable(self, raw: str) -> None:
        with patch.object(mp, "run_gh", return_value=raw):
            assert mp._in_merge_queue(5) is None

    def test_none_when_gh_fails(self) -> None:
        with patch.object(mp, "run_gh", side_effect=RuntimeError("HTTP 403")):
            assert mp._in_merge_queue(5) is None


class TestTryMergeQueue:
    def _run(self, proc: MagicMock, outcome=("pending", "enqueued"), **kw):
        with patch.object(mp, "run_gh_unchecked", return_value=proc) as gh, \
                patch.object(mp, "_await_queue_outcome", return_value=outcome) as wait, \
                patch.object(mp, "_delete_remote_branch_via_api",
                             return_value={"deleted": True}) as delete:
            result = mp._try_merge_queue(9, "squash", False, branch="feat", **kw)
        return result, gh, wait, delete

    def test_enqueues_without_strategy_or_delete_flags(self) -> None:
        """gh prints nothing when piped, so stdout is deliberately empty."""
        result, gh, _wait, _del = self._run(_proc())
        assert gh.call_args.args[0] == ["pr", "merge", "9"]
        assert result["success"] is True
        assert result["status"] == "enqueued"
        assert result["merge_queue"] is True

    def test_status_comes_from_polled_state_not_cli_output(self) -> None:
        result, *_ = self._run(
            _proc(stdout="added to the merge queue"),
            ("pending", "auto_merge_pending"),
        )
        assert result["status"] == "auto_merge_pending"
        assert "Auto-merge enabled" in result["note"]

    def test_merged_during_wait_deletes_branch(self) -> None:
        result, _gh, _wait, delete = self._run(_proc(), ("merged", "merged"))
        assert result["status"] == "merged"
        assert result["success"] is True
        delete.assert_called_once_with("feat")

    def test_fork_pr_keeps_remote_branch(self) -> None:
        with patch.object(mp, "run_gh_unchecked", return_value=_proc()), \
                patch.object(mp, "_await_queue_outcome", return_value=("merged", "merged")), \
                patch.object(mp, "_delete_remote_branch_via_api") as delete:
            result = mp._try_merge_queue(9, "squash", True, branch="feat")
        delete.assert_not_called()
        assert "Fork PR" in result["note"]

    @pytest.mark.parametrize("outcome", ["removed", "closed"])
    def test_dropped_pr_is_failure_not_direct_merge(self, outcome: str) -> None:
        result, gh, _wait, _del = self._run(_proc(), (outcome, outcome))
        assert result["success"] is False
        assert result["status"] == outcome
        assert gh.call_count == 1

    def test_still_queued_at_deadline_is_nonterminal(self) -> None:
        result, *_ = self._run(_proc())
        assert result["success"] is True
        assert result["status"] == "enqueued"

    def test_nonzero_exit_but_already_merged(self) -> None:
        with patch.object(mp, "run_gh_unchecked",
                          return_value=_proc(1, stderr="local branch update failed")), \
                patch.object(mp, "get_pr_status", return_value={"state": "MERGED"}), \
                patch.object(mp, "_delete_remote_branch_via_api",
                             return_value={"deleted": True}):
            result = mp._try_merge_queue(9, "squash", False, branch="feat")
        assert result["success"] is True
        assert result["status"] == "merged"
        assert "warning" in result

    def test_nonzero_exit_open_pr_fails(self) -> None:
        with patch.object(mp, "run_gh_unchecked",
                          return_value=_proc(1, stderr="not mergeable")), \
                patch.object(mp, "get_pr_status", return_value={"state": "OPEN"}):
            result = mp._try_merge_queue(9, "squash", False)
        assert result["success"] is False
        assert result["error"] == "not mergeable"

    def test_timeout_reports_failure(self) -> None:
        with patch.object(mp, "run_gh_unchecked",
                          side_effect=subprocess.TimeoutExpired("gh", 60)):
            result = mp._try_merge_queue(9, "squash", False)
        assert result["success"] is False

    def test_poll_window_defaults_to_module_setting(self) -> None:
        _r, _gh, wait, _del = self._run(_proc())
        assert wait.call_args.args[1] == mp.MERGE_QUEUE_POLL_SECONDS

    def test_poll_window_override(self) -> None:
        _r, _gh, wait, _del = self._run(_proc(), poll_seconds=20)
        assert wait.call_args.args[1] == 20


class TestTryMergeRouting:
    def test_required_queue_owns_the_outcome(self) -> None:
        queued = {"success": False, "status": "removed"}
        with patch.object(mp, "_has_merge_queue", return_value=True), \
                patch.object(mp, "_try_merge_queue", return_value=queued) as q, \
                patch.object(mp, "run_gh_unchecked") as direct:
            assert mp._try_merge(3, "squash", False, branch="b") is queued
        q.assert_called_once_with(3, "squash", False, branch="b")
        direct.assert_not_called()

    def test_no_queue_uses_direct_merge(self) -> None:
        with patch.object(mp, "_has_merge_queue", return_value=False), \
                patch.object(mp, "_try_merge_queue") as q, \
                patch.object(mp, "run_gh_unchecked", return_value=_proc()) as direct:
            result = mp._try_merge(3, "squash", False, branch="b")
        q.assert_not_called()
        assert direct.call_args.args[0][:4] == ["pr", "merge", "3", "--squash"]
        assert result["status"] == "merged"


class TestBackendDetection:
    def test_queue_backend_only_when_rule_present(self) -> None:
        with patch.object(mb.subprocess, "run",
                          return_value=_proc(stdout="main\n")), \
                patch.object(mb, "merge_queue_required", return_value=True) as req:
            assert mb._has_github_merge_queue() is True
        req.assert_called_once_with("main")

    def test_repo_without_queue_is_not_queue_backend(self) -> None:
        with patch.object(mb.subprocess, "run",
                          return_value=_proc(stdout="main\n")), \
                patch.object(mb, "merge_queue_required", return_value=False):
            assert mb._has_github_merge_queue() is False

    def test_false_when_repo_lookup_fails(self) -> None:
        with patch.object(mb.subprocess, "run", return_value=_proc(1)), \
                patch.object(mb, "merge_queue_required") as req:
            assert mb._has_github_merge_queue() is False
        req.assert_not_called()

    def test_false_when_gh_missing(self) -> None:
        with patch.object(mb.subprocess, "run", side_effect=OSError):
            assert mb._has_github_merge_queue() is False

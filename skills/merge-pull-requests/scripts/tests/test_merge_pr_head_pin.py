"""The merge is pinned to the head the review predicate saw.

Without ``--match-head-commit`` a push landing between the review check and
``gh pr merge`` would merge code no reviewer saw. These tests pin the gh
arguments and the live head surfaced by ``get_pr_status``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import merge_pr as merge_pr_module

SHA = "d" * 40


class _Recorder:
    def __init__(self, returncode: int = 0, stderr: str = "") -> None:
        self.calls: list[list[str]] = []
        self.returncode = returncode
        self.stderr = stderr

    def __call__(self, args, timeout=None):
        self.calls.append(list(args))
        return subprocess.CompletedProcess(args, self.returncode, stdout="", stderr=self.stderr)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    rec = _Recorder()
    monkeypatch.setattr(merge_pr_module, "run_gh_unchecked", rec)
    monkeypatch.setattr(merge_pr_module, "_has_merge_queue", lambda: False)
    return rec


def _pin(args: list[str]) -> str | None:
    if "--match-head-commit" not in args:
        return None
    return args[args.index("--match-head-commit") + 1]


def test_direct_merge_is_pinned_to_expected_head(recorder: _Recorder) -> None:
    result = merge_pr_module._try_merge(7, "rebase", False, branch="f", expected_head_sha=SHA)
    assert result["success"] is True
    assert _pin(recorder.calls[0]) == SHA


def test_queue_merge_is_pinned_to_expected_head(recorder: _Recorder) -> None:
    result = merge_pr_module._try_merge_queue(7, "rebase", False, branch="f", expected_head_sha=SHA)
    assert result["success"] is True
    assert "--merge-queue" in recorder.calls[0]
    assert _pin(recorder.calls[0]) == SHA


def test_queue_first_path_forwards_the_pin(recorder: _Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(merge_pr_module, "_has_merge_queue", lambda: True)
    merge_pr_module._try_merge(7, "squash", False, expected_head_sha=SHA)
    assert "--merge-queue" in recorder.calls[0]
    assert _pin(recorder.calls[0]) == SHA


@pytest.mark.parametrize("call", ["_try_merge", "_try_merge_queue"])
def test_unpinned_merge_args_are_unchanged(recorder: _Recorder, call: str) -> None:
    getattr(merge_pr_module, call)(7, "rebase", False, branch="f")
    assert "--match-head-commit" not in recorder.calls[0]


def test_head_mismatch_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _Recorder(returncode=1, stderr="GraphQL: Head branch was modified. Review and try the merge again.")
    monkeypatch.setattr(merge_pr_module, "run_gh_unchecked", rec)
    monkeypatch.setattr(merge_pr_module, "_has_merge_queue", lambda: False)
    monkeypatch.setattr(merge_pr_module, "get_pr_status", lambda _n: {"state": "OPEN"})

    result = merge_pr_module._try_merge(7, "rebase", False, branch="f", expected_head_sha=SHA)

    assert result["success"] is False
    assert result["head_mismatch"] is True


def test_merge_pr_forwards_pin_to_try_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}
    validation = {
        "can_merge": True, "checks_pending": False, "checks_failed": False,
        "approval_required": False, "approved": True, "approval_may_be_stale": False,
        "mergeable": "MERGEABLE", "is_draft": False, "has_conflicts": False,
        "is_fork": False, "branch": "feature", "pending_reviewers": [],
    }

    def fake_try_merge(pr_number, strategy, is_fork, branch="", expected_head_sha=None):
        seen["expected_head_sha"] = expected_head_sha
        return {"action": "merge", "success": True, "status": "enqueued", "pr_number": pr_number}

    monkeypatch.setattr(merge_pr_module, "capture_head", lambda: {"branch": "main", "sha": "a" * 40})
    monkeypatch.setattr(merge_pr_module, "validate_pr", lambda _n: dict(validation))
    monkeypatch.setattr(merge_pr_module, "_try_merge", fake_try_merge)

    merge_pr_module.merge_pr(7, "rebase", expected_head_sha=SHA)

    assert seen["expected_head_sha"] == SHA


def test_get_pr_status_requests_and_surfaces_head_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[list[str]] = []

    def fake_run_gh(args, timeout=None):
        requested.append(list(args))
        return json.dumps({"state": "OPEN", "headRefName": "feature", "headRefOid": SHA})

    monkeypatch.setattr(merge_pr_module, "run_gh", fake_run_gh)

    status = merge_pr_module.get_pr_status(7)

    fields = requested[0][requested[0].index("--json") + 1].split(",")
    assert "headRefOid" in fields
    assert status["head_sha"] == SHA

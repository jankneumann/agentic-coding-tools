"""Every successful merge is recorded, with or without --pipeline.

Before 2026-08-25 the merge event was hook 1 of ``post_merge_pipeline``, which
runs only behind ``--pipeline`` -- the same flag that enables auto-cascading
rebase and a 15-minute CI rollback monitor. Nobody passes an opt-in flag whose
other two effects mutate unrelated PRs just to get a metrics row, so no merge
was ever recorded: the log held 28 rows, all test fixtures, and zero ``merge``
events, making ``revert_rate`` 2 reverts over 0 merges.

These tests pin the property that was missing rather than the wiring that
happened to implement it: call the plain merge path, get a merge event.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import merge_pr as merge_pr_module
from merge_events import load_events


@pytest.fixture()
def _merge_succeeds():
    """Stub out everything merge_pr does before the merge itself."""
    validation = {
        "can_merge": True,
        "checks_pending": False,
        "checks_failed": False,
        "approval_required": False,
        "approved": True,
        "approval_may_be_stale": False,
        "mergeable": True,
        "is_draft": False,
        "has_conflicts": False,
        "is_fork": False,
        "branch": "feature",
        "pending_reviewers": [],
    }
    with (
        patch.object(
            merge_pr_module, "capture_head",
            return_value={"branch": "main", "sha": "a" * 40},
        ),
        patch.object(merge_pr_module, "validate_pr", return_value=validation),
        patch.object(
            merge_pr_module, "_try_merge",
            return_value={
                "action": "merge", "success": True, "status": "merged",
                "pr_number": 7, "strategy": "rebase",
                "merge_commit_sha": "b" * 40,
            },
        ),
    ):
        yield


def test_plain_merge_records_an_event(
    _merge_succeeds, _redirect_default_merge_log: Path,
) -> None:
    """No --pipeline, no explicit log_path: the merge is still recorded."""
    result = merge_pr_module.merge_pr(7, "rebase", origin="openspec")

    assert result["success"] is True
    assert result["event_emitted"] is True

    events = load_events(log_path=_redirect_default_merge_log)
    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "merge"
    assert event["pr_number"] == 7
    assert event["origin"] == "openspec"
    assert event["strategy"] == "rebase"
    assert event["backend"] == "direct"
    assert event["success"] is True
    # duration_seconds is measured, not the None the pipeline always passed.
    assert isinstance(event["duration_seconds"], float)


def test_dry_run_records_nothing(
    _merge_succeeds, _redirect_default_merge_log: Path,
) -> None:
    """A dry run is not a merge and must not enter the metrics."""
    merge_pr_module.merge_pr(7, "rebase", dry_run=True)
    assert load_events(log_path=_redirect_default_merge_log) == []


def test_failed_merge_records_nothing(_redirect_default_merge_log: Path) -> None:
    """A refused merge must not be counted as one."""
    with patch.object(
        merge_pr_module, "capture_head",
        return_value={"branch": None, "sha": "c" * 40},
    ):
        result = merge_pr_module.merge_pr(7, "rebase")

    assert result["success"] is False
    assert load_events(log_path=_redirect_default_merge_log) == []


def test_metrics_failure_never_fails_the_merge(
    _merge_succeeds, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A full disk must not turn a completed merge into a failed command.

    The merge already happened on GitHub by this point; reporting it as failed
    because a local append broke would be strictly worse than losing the row.
    """
    import merge_events

    def _boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(merge_events, "emit_event", _boom)

    result = merge_pr_module.merge_pr(7, "rebase")

    assert result["success"] is True
    assert result["event_emitted"] is False
    assert "disk full" in result["event_error"]


def test_enqueued_pr_is_not_counted_as_a_merge(
    _redirect_default_merge_log: Path,
) -> None:
    """A queued PR is not a merged one.

    Raised as a P2 on PR #418 by chatgpt-codex-connector. When the repository
    has a merge queue, ``_try_merge`` returns ``_try_merge_queue``'s
    ``{"success": True, "status": "enqueued"}`` -- the PR is admitted to the
    queue, not merged, and can still fail required checks and be ejected.
    Guarding on ``success`` alone recorded it as a completed merge, inflating
    merge_count, deflating revert_rate, polluting duration percentiles with a
    queue-admission time, and labelling it ``backend="direct"``.
    """
    validation = {
        "can_merge": True, "checks_pending": False, "checks_failed": False,
        "approval_required": False, "approved": True,
        "approval_may_be_stale": False, "mergeable": True, "is_draft": False,
        "has_conflicts": False, "is_fork": False, "branch": "feature",
        "pending_reviewers": [],
    }
    with (
        patch.object(
            merge_pr_module, "capture_head",
            return_value={"branch": "main", "sha": "a" * 40},
        ),
        patch.object(merge_pr_module, "validate_pr", return_value=validation),
        patch.object(
            merge_pr_module, "_try_merge",
            return_value={
                "action": "merge", "success": True, "status": "enqueued",
                "pr_number": 7, "strategy": "rebase",
            },
        ),
    ):
        result = merge_pr_module.merge_pr(7, "rebase")

    # The command still reports success -- the PR really was enqueued.
    assert result["success"] is True
    assert result["status"] == "enqueued"
    # But nothing is recorded: the merge has not happened yet.
    assert "event_emitted" not in result
    assert load_events(log_path=_redirect_default_merge_log) == []

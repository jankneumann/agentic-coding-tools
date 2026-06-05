"""Integration test for the full merge lifecycle.

Covers:
- merge-infrastructure: Full pipeline end-to-end with mocked externals
- merge-infrastructure.1: Solo-dev backward compatibility
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestFullMergeLifecycle:
    """Test the complete merge → rebase → rollback → metrics flow."""

    @patch("post_merge_pipeline.monitor_ci_for_rollback")
    @patch("post_merge_pipeline.auto_cascade_rebase")
    @patch("post_merge_pipeline.emit_event")
    def test_merge_with_pipeline_full_flow(
        self,
        mock_emit,
        mock_rebase,
        mock_rollback,
    ) -> None:
        from merge_backend import DirectMergeBackend
        from merge_pr import merge_with_pipeline

        mock_rebase.return_value = {
            "refreshed": [{"pr_number": 45, "success": True}],
            "conflicting": [],
            "remaining": 0,
        }
        mock_rollback.return_value = {"action": "stable"}

        with patch("merge_pr.merge_pr") as mock_merge_fn:
            mock_merge_fn.return_value = {
                "action": "merge",
                "success": True,
                "pr_number": 42,
                "strategy": "rebase",
            }
            with patch(
                "merge_backend.detect_merge_backend",
                return_value=DirectMergeBackend(),
            ):
                with patch(
                    "check_staleness.get_pr_changed_files",
                    return_value=["src/api.py"],
                ):
                    result = merge_with_pipeline(
                        42, "rebase", origin="openspec",
                    )

        assert result["success"] is True
        assert "post_merge" in result
        assert result["post_merge"]["event_emitted"] is True
        mock_rebase.assert_called_once()
        # Rollback is skipped when merge_sha is not in the merge result
        # (gh pr merge doesn't return the merge commit SHA directly)
        assert result["post_merge"]["rollback"]["skipped"] is True

    @patch("merge_pr.merge_pr")
    def test_pipeline_skipped_on_merge_failure(self, mock_merge_pr) -> None:
        from merge_pr import merge_with_pipeline

        mock_merge_pr.return_value = {
            "action": "merge",
            "success": False,
            "pr_number": 42,
            "reason": "PR has merge conflicts",
        }

        result = merge_with_pipeline(42, "squash")

        assert result["success"] is False
        assert "post_merge" not in result

    @patch("merge_pr.merge_pr")
    def test_pipeline_skipped_on_dry_run(self, mock_merge_pr) -> None:
        from merge_pr import merge_with_pipeline

        mock_merge_pr.return_value = {
            "action": "merge",
            "dry_run": True,
            "pr_number": 42,
            "would_merge": True,
        }

        result = merge_with_pipeline(42, "squash", dry_run=True)

        assert "post_merge" not in result


class TestSoloDevBackwardCompatibility:
    """Verify merge works without coordinator or GitHub queue."""

    def test_direct_merge_backend_selected_without_coordinator(self) -> None:
        from merge_backend import DirectMergeBackend, detect_merge_backend

        with patch(
            "merge_backend._get_coordinator_status",
            return_value={"COORDINATOR_AVAILABLE": False, "CAN_QUEUE_WORK": False},
        ):
            with patch("merge_backend._has_github_merge_queue", return_value=False):
                backend = detect_merge_backend()

        assert isinstance(backend, DirectMergeBackend)
        assert backend.name == "direct"
        assert backend.supports_train() is False

    def test_merge_strategy_resolution_unchanged(self) -> None:
        from merge_pr import get_default_strategy, resolve_strategy

        assert get_default_strategy("openspec") == "rebase"
        assert get_default_strategy("dependabot") == "squash"
        assert resolve_strategy(None, None) == "squash"
        assert resolve_strategy("merge", "openspec") == "merge"

    @patch("merge_pr._try_merge")
    @patch("merge_pr.validate_pr")
    def test_existing_merge_pr_works_without_pipeline(
        self, mock_validate, mock_try_merge,
    ) -> None:
        from merge_pr import merge_pr

        mock_validate.return_value = {
            "pr_number": 42,
            "title": "test",
            "branch": "feat/test",
            "base_branch": "main",
            "is_draft": False,
            "is_fork": False,
            "mergeable": "MERGEABLE",
            "has_conflicts": False,
            "check_summary": "passing",
            "checks_passing": True,
            "checks_pending": False,
            "checks_failed": False,
            "check_details": [],
            "review_decision": "APPROVED",
            "approved": True,
            "approval_required": True,
            "approval_may_be_stale": False,
            "pending_reviewers": [],
            "can_merge": True,
        }
        mock_try_merge.return_value = {
            "action": "merge",
            "success": True,
            "pr_number": 42,
            "strategy": "squash",
        }

        result = merge_pr(42, "squash")

        assert result["success"] is True
        assert "post_merge" not in result

    def test_merge_events_work_standalone(self, tmp_path: Path) -> None:
        from merge_events import MergeEvent, emit_event, load_events

        log_path = tmp_path / "test.jsonl"
        event = MergeEvent(
            event_type="merge",
            pr_number=1,
            backend="direct",
            success=True,
        )
        emit_event(event, log_path=log_path)
        events = load_events(log_path=log_path)
        assert len(events) == 1

    def test_metrics_work_without_coordinator(self, tmp_path: Path) -> None:
        from merge_events import MergeEvent, emit_event
        from merge_metrics import compute_metrics_summary

        log_path = tmp_path / "test.jsonl"
        emit_event(
            MergeEvent(
                event_type="merge", pr_number=1,
                backend="direct", success=True,
            ),
            log_path=log_path,
        )
        summary = compute_metrics_summary(log_path=log_path)
        assert summary["merge_count"] == 1
        assert summary["backend_counts"]["direct"] == 1

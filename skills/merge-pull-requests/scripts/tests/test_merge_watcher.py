"""Tests for background merge watcher.

Covers spec scenarios:
- merge-infrastructure.6: Watcher tick
- merge-infrastructure.6: Watcher idempotency (no-op when empty)

Design decisions:
- D5: Merge watcher as coordinator background task
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from merge_watcher import merge_watcher_tick


class TestMergeWatcherTick:
    """Test single-pass merge watcher behavior."""

    @patch("merge_watcher.monitor_ci_for_rollback")
    @patch("merge_watcher.auto_cascade_rebase")
    @patch("merge_watcher._get_recent_merges")
    @patch("merge_watcher._get_open_prs")
    def test_no_op_when_queue_empty_and_no_recent_merges(
        self, mock_prs, mock_merges, mock_rebase, mock_rollback,
    ) -> None:
        mock_prs.return_value = []
        mock_merges.return_value = []

        result = merge_watcher_tick()

        assert result["action"] == "heartbeat"
        mock_rebase.assert_not_called()
        mock_rollback.assert_not_called()

    @patch("merge_watcher.monitor_ci_for_rollback")
    @patch("merge_watcher.auto_cascade_rebase")
    @patch("merge_watcher._get_recent_merges")
    @patch("merge_watcher._get_open_prs")
    def test_triggers_rollback_monitoring_for_recent_merges(
        self, mock_prs, mock_merges, mock_rebase, mock_rollback,
    ) -> None:
        mock_prs.return_value = []
        mock_merges.return_value = [
            {
                "pr_number": 42,
                "merge_sha": "abc123",
                "title": "feat: API",
                "files": ["src/api.py"],
            },
        ]
        mock_rollback.return_value = {"action": "stable"}

        result = merge_watcher_tick()

        assert result["action"] == "processed"
        mock_rollback.assert_called_once()

    @patch("merge_watcher.auto_cascade_rebase")
    @patch("merge_watcher._get_recent_merges")
    @patch("merge_watcher._get_open_prs")
    def test_triggers_rebase_for_stale_prs(
        self, mock_prs, mock_merges, mock_rebase,
    ) -> None:
        mock_prs.return_value = [
            {"number": 10, "files": ["src/api.py"]},
        ]
        mock_merges.return_value = [
            {
                "pr_number": 42,
                "merge_sha": "abc123",
                "title": "feat: API",
                "files": ["src/api.py"],
            },
        ]
        mock_rebase.return_value = {"refreshed": []}

        with patch("merge_watcher.monitor_ci_for_rollback") as mock_rollback:
            mock_rollback.return_value = {"action": "stable"}
            result = merge_watcher_tick()

        mock_rebase.assert_called_once()

    @patch("merge_watcher.emit_event")
    @patch("merge_watcher._get_recent_merges")
    @patch("merge_watcher._get_open_prs")
    def test_emits_heartbeat_event(
        self, mock_prs, mock_merges, mock_emit,
    ) -> None:
        mock_prs.return_value = []
        mock_merges.return_value = []

        merge_watcher_tick()

        mock_emit.assert_called_once()

    @patch("merge_watcher._get_recent_merges")
    @patch("merge_watcher._get_open_prs")
    def test_catches_exceptions_without_crashing(
        self, mock_prs, mock_merges,
    ) -> None:
        mock_prs.side_effect = RuntimeError("API timeout")
        mock_merges.return_value = []

        result = merge_watcher_tick()

        assert result["action"] == "error"
        assert "error" in result

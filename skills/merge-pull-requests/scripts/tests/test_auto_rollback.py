"""Tests for auto rollback with CI monitoring and revert creation.

Covers spec scenarios:
- merge-infrastructure.4: Breakage detection and attribution
- merge-infrastructure.4: Auto revert creation
- merge-infrastructure.4: No false positive revert (no file overlap)
- merge-infrastructure.4: Monitoring window timeout

Design decisions:
- D4: Auto-rollback attribution via file overlap
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from auto_rollback import (
    ROLLBACK_MONITOR_MINUTES,
    attribute_breakage,
    create_revert_pr,
    monitor_ci_for_rollback,
)


class TestAttributeBreakage:
    """Test breakage attribution via file overlap heuristic."""

    def test_attributes_when_files_overlap(self) -> None:
        merged_files = ["src/api.py", "src/models.py"]
        failing_files = ["src/api.py", "tests/test_api.py"]
        result = attribute_breakage(merged_files, failing_files)
        assert result["attributed"] is True
        assert "src/api.py" in result["overlapping_files"]

    def test_no_attribution_when_no_overlap(self) -> None:
        merged_files = ["src/api.py"]
        failing_files = ["src/auth.py", "tests/test_auth.py"]
        result = attribute_breakage(merged_files, failing_files)
        assert result["attributed"] is False
        assert result["overlapping_files"] == []

    def test_empty_merged_files(self) -> None:
        result = attribute_breakage([], ["src/api.py"])
        assert result["attributed"] is False

    def test_empty_failing_files(self) -> None:
        result = attribute_breakage(["src/api.py"], [])
        assert result["attributed"] is False


class TestCreateRevertPR:
    """Test revert PR creation."""

    @patch("auto_rollback._run_gh")
    @patch("auto_rollback._run_cmd")
    def test_creates_revert_commit_and_pr(
        self, mock_cmd, mock_gh,
    ) -> None:
        mock_cmd.return_value = ""
        mock_gh.side_effect = [
            json.dumps({
                "url": "https://github.com/org/repo/pull/100",
                "number": 100,
            }),
            "",  # auto-merge call
        ]

        result = create_revert_pr(
            merge_sha="abc123",
            original_pr_number=42,
            original_pr_title="feat: add API",
        )

        assert result["success"] is True
        assert result["revert_pr_number"] == 100

    @patch("auto_rollback._run_cmd")
    def test_handles_revert_conflict(self, mock_cmd) -> None:
        mock_cmd.side_effect = RuntimeError("conflict during revert")

        result = create_revert_pr(
            merge_sha="abc123",
            original_pr_number=42,
            original_pr_title="feat: add API",
        )

        assert result["success"] is False
        assert "conflict" in result["error"].lower()


class TestMonitorCIForRollback:
    """Test CI monitoring and auto-revert triggering."""

    @patch("auto_rollback.create_revert_pr")
    @patch("auto_rollback._get_main_ci_status")
    @patch("auto_rollback._get_failing_test_files")
    def test_reverts_when_ci_fails_with_overlap(
        self, mock_failing_files, mock_ci_status, mock_revert,
    ) -> None:
        mock_ci_status.return_value = {"status": "failure"}
        mock_failing_files.return_value = ["src/api.py"]
        mock_revert.return_value = {
            "success": True,
            "revert_pr_number": 100,
        }

        result = monitor_ci_for_rollback(
            merge_sha="abc123",
            pr_number=42,
            pr_title="feat: add API",
            merged_files=["src/api.py"],
            poll_interval=0,
            max_polls=1,
        )

        assert result["action"] == "reverted"
        assert result["revert_pr_number"] == 100
        mock_revert.assert_called_once()

    @patch("auto_rollback._get_main_ci_status")
    @patch("auto_rollback._get_failing_test_files")
    def test_no_revert_when_no_file_overlap(
        self, mock_failing_files, mock_ci_status,
    ) -> None:
        mock_ci_status.return_value = {"status": "failure"}
        mock_failing_files.return_value = ["src/auth.py"]

        result = monitor_ci_for_rollback(
            merge_sha="abc123",
            pr_number=42,
            pr_title="feat: add API",
            merged_files=["src/api.py"],
            poll_interval=0,
            max_polls=1,
        )

        assert result["action"] == "no_revert"
        assert result["reason"] == "no_file_overlap"

    @patch("auto_rollback._get_main_ci_status")
    def test_stable_when_ci_passes(self, mock_ci_status) -> None:
        mock_ci_status.return_value = {"status": "success"}

        result = monitor_ci_for_rollback(
            merge_sha="abc123",
            pr_number=42,
            pr_title="feat: add API",
            merged_files=["src/api.py"],
            poll_interval=0,
            max_polls=1,
        )

        assert result["action"] == "stable"

    @patch("auto_rollback._get_main_ci_status")
    def test_timeout_when_ci_pending(self, mock_ci_status) -> None:
        mock_ci_status.return_value = {"status": "pending"}

        result = monitor_ci_for_rollback(
            merge_sha="abc123",
            pr_number=42,
            pr_title="feat: add API",
            merged_files=["src/api.py"],
            poll_interval=0,
            max_polls=2,
        )

        assert result["action"] == "timeout"

    @patch("auto_rollback.create_revert_pr")
    @patch("auto_rollback._get_main_ci_status")
    @patch("auto_rollback._get_failing_test_files")
    def test_emits_revert_event(
        self, mock_failing_files, mock_ci_status, mock_revert,
    ) -> None:
        mock_ci_status.return_value = {"status": "failure"}
        mock_failing_files.return_value = ["src/api.py"]
        mock_revert.return_value = {
            "success": True,
            "revert_pr_number": 100,
        }

        with patch("auto_rollback.emit_event") as mock_emit:
            result = monitor_ci_for_rollback(
                merge_sha="abc123",
                pr_number=42,
                pr_title="feat: add API",
                merged_files=["src/api.py"],
                poll_interval=0,
                max_polls=1,
            )

        mock_emit.assert_called_once()
        event = mock_emit.call_args[0][0]
        assert event.event_type == "revert"
        assert event.pr_number == 42

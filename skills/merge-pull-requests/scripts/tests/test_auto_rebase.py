"""Tests for auto cascading rebase after merge.

Covers spec scenarios:
- merge-infrastructure.3: Auto rebase for non-conflicting overlap
- merge-infrastructure.3: Rate limiting (max 5 per merge)
- merge-infrastructure.3: Conflicting overlap skip

Design decisions:
- D3: Auto-rebase rate limiting (MAX_AUTO_REBASE_PER_MERGE=5)
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from auto_rebase import (
    MAX_AUTO_REBASE_PER_MERGE,
    auto_cascade_rebase,
    find_overlapping_prs,
)


class TestFindOverlappingPRs:
    """Test identification of queued PRs with file overlap."""

    def test_finds_prs_with_overlapping_files(self) -> None:
        merged_files = ["src/api.py", "src/models.py"]
        queued_prs = [
            {"number": 10, "files": ["src/api.py", "src/utils.py"]},
            {"number": 11, "files": ["docs/README.md"]},
            {"number": 12, "files": ["src/models.py"]},
        ]
        result = find_overlapping_prs(merged_files, queued_prs)
        assert len(result) == 2
        assert {pr["number"] for pr in result} == {10, 12}

    def test_no_overlap_returns_empty(self) -> None:
        merged_files = ["src/api.py"]
        queued_prs = [
            {"number": 10, "files": ["docs/README.md"]},
        ]
        result = find_overlapping_prs(merged_files, queued_prs)
        assert result == []

    def test_empty_queued_prs(self) -> None:
        result = find_overlapping_prs(["src/api.py"], [])
        assert result == []

    def test_empty_merged_files(self) -> None:
        result = find_overlapping_prs([], [{"number": 10, "files": ["src/api.py"]}])
        assert result == []


class TestAutoCascadeRebase:
    """Test auto_cascade_rebase() end-to-end behavior."""

    @patch("auto_rebase._refresh_pr_branch")
    @patch("auto_rebase._get_queued_prs_with_files")
    def test_refreshes_overlapping_prs(
        self, mock_get_queued, mock_refresh,
    ) -> None:
        mock_get_queued.return_value = [
            {"number": 10, "files": ["src/api.py", "src/utils.py"]},
            {"number": 11, "files": ["docs/README.md"]},
        ]
        mock_refresh.return_value = {"success": True, "pr_number": 10}

        result = auto_cascade_rebase(
            merged_pr_number=42,
            merged_files=["src/api.py"],
        )

        assert len(result["refreshed"]) == 1
        assert result["refreshed"][0]["pr_number"] == 10
        mock_refresh.assert_called_once_with(10)

    @patch("auto_rebase._refresh_pr_branch")
    @patch("auto_rebase._get_queued_prs_with_files")
    def test_rate_limits_to_max(
        self, mock_get_queued, mock_refresh,
    ) -> None:
        queued = [
            {"number": i, "files": ["shared.py"]} for i in range(20)
        ]
        mock_get_queued.return_value = queued
        mock_refresh.return_value = {"success": True}

        result = auto_cascade_rebase(
            merged_pr_number=42,
            merged_files=["shared.py"],
        )

        assert len(result["refreshed"]) == MAX_AUTO_REBASE_PER_MERGE
        assert result["remaining"] == 20 - MAX_AUTO_REBASE_PER_MERGE

    @patch("auto_rebase._refresh_pr_branch")
    @patch("auto_rebase._get_queued_prs_with_files")
    def test_skips_conflicting_prs(
        self, mock_get_queued, mock_refresh,
    ) -> None:
        mock_get_queued.return_value = [
            {"number": 10, "files": ["src/api.py"]},
        ]
        mock_refresh.return_value = {
            "success": False,
            "pr_number": 10,
            "reason": "merge conflict",
        }

        result = auto_cascade_rebase(
            merged_pr_number=42,
            merged_files=["src/api.py"],
        )

        assert len(result["conflicting"]) == 1
        assert result["conflicting"][0]["pr_number"] == 10

    @patch("auto_rebase._get_queued_prs_with_files")
    def test_no_op_when_no_overlap(self, mock_get_queued) -> None:
        mock_get_queued.return_value = [
            {"number": 10, "files": ["docs/README.md"]},
        ]

        result = auto_cascade_rebase(
            merged_pr_number=42,
            merged_files=["src/api.py"],
        )

        assert result["refreshed"] == []
        assert result["conflicting"] == []

    @patch("auto_rebase._refresh_pr_branch")
    @patch("auto_rebase._get_queued_prs_with_files")
    def test_refresh_failure_doesnt_stop_remaining(
        self, mock_get_queued, mock_refresh,
    ) -> None:
        mock_get_queued.return_value = [
            {"number": 10, "files": ["shared.py"]},
            {"number": 11, "files": ["shared.py"]},
        ]
        mock_refresh.side_effect = [
            {"success": False, "pr_number": 10, "reason": "API error"},
            {"success": True, "pr_number": 11},
        ]

        result = auto_cascade_rebase(
            merged_pr_number=42,
            merged_files=["shared.py"],
        )

        assert len(result["refreshed"]) == 1
        assert len(result["conflicting"]) == 1

    @patch("auto_rebase._get_queued_prs_with_files")
    def test_custom_rate_limit(self, mock_get_queued) -> None:
        queued = [
            {"number": i, "files": ["shared.py"]} for i in range(10)
        ]
        mock_get_queued.return_value = queued

        with patch("auto_rebase._refresh_pr_branch") as mock_refresh:
            mock_refresh.return_value = {"success": True}
            result = auto_cascade_rebase(
                merged_pr_number=42,
                merged_files=["shared.py"],
                max_rebase=2,
            )

        assert len(result["refreshed"]) == 2
        assert result["remaining"] == 8

    @patch("auto_rebase._get_queued_prs_with_files")
    def test_disabled_when_max_rebase_zero(self, mock_get_queued) -> None:
        mock_get_queued.return_value = [
            {"number": 10, "files": ["shared.py"]},
        ]

        result = auto_cascade_rebase(
            merged_pr_number=42,
            merged_files=["shared.py"],
            max_rebase=0,
        )

        assert result["refreshed"] == []
        assert result["remaining"] == 1

"""Tests for refresh_branch and ci_merge_base_stale.

Covers:
- refresh_branch dry-run returns correct message
- refresh_branch handles missing PR head SHA
- _get_ci_merge_base_staleness detects stale merge base
- _get_ci_merge_base_staleness reports fresh when SHAs match
- _get_ci_merge_base_staleness handles API errors gracefully
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

# Add scripts dir to path so we can import the modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from merge_pr import refresh_branch


class TestRefreshBranchDryRun:
    """Dry-run mode returns the expected message without calling the API."""

    @patch("merge_pr.run_gh")
    def test_dry_run_returns_message(self, mock_run_gh) -> None:
        mock_run_gh.return_value = json.dumps({
            "headRefOid": "abc123def456",
            "baseRefName": "main",
        })
        result = refresh_branch(42, dry_run=True)

        assert result["action"] == "refresh-branch"
        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["pr_number"] == 42
        assert "abc123de" in result["message"]
        assert "main" in result["message"]

    @patch("merge_pr.run_gh")
    def test_missing_head_sha_returns_error(self, mock_run_gh) -> None:
        mock_run_gh.return_value = json.dumps({
            "headRefOid": "",
            "baseRefName": "main",
        })
        result = refresh_branch(99)

        assert result["success"] is False
        assert "head SHA" in result["error"]

    @patch("merge_pr.run_gh")
    def test_pr_fetch_error_returns_error(self, mock_run_gh) -> None:
        mock_run_gh.side_effect = RuntimeError("API timeout")
        result = refresh_branch(99)

        assert result["success"] is False
        assert "Could not fetch PR" in result["error"]


class TestRefreshBranchLive:
    """Live calls through run_gh_unchecked."""

    @patch("merge_pr.run_gh_unchecked")
    @patch("merge_pr.run_gh")
    def test_successful_refresh(self, mock_run_gh, mock_unchecked) -> None:
        mock_run_gh.return_value = json.dumps({
            "headRefOid": "abc123def456",
            "baseRefName": "main",
        })
        mock_unchecked.return_value = type("R", (), {
            "returncode": 0, "stdout": "{}", "stderr": "",
        })()

        result = refresh_branch(42)

        assert result["success"] is True
        assert result["was_stale"] is True
        assert "fresh CI" in result["message"]
        # Verify the API was called with the correct args
        call_args = mock_unchecked.call_args[0][0]
        assert "update-branch" in " ".join(call_args)
        assert "abc123def456" in " ".join(call_args)

    @patch("merge_pr.run_gh_unchecked")
    @patch("merge_pr.run_gh")
    def test_already_up_to_date(self, mock_run_gh, mock_unchecked) -> None:
        mock_run_gh.return_value = json.dumps({
            "headRefOid": "abc123def456",
            "baseRefName": "main",
        })
        mock_unchecked.return_value = type("R", (), {
            "returncode": 1,
            "stdout": "",
            "stderr": "merge-upstream is not behind the upstream",
        })()

        result = refresh_branch(42)

        assert result["success"] is True
        assert result["was_stale"] is False
        assert "up to date" in result["message"]


class TestCiMergeBaseStaleness:
    """Tests for _get_ci_merge_base_staleness in check_staleness.py."""

    @patch("check_staleness.run_cmd")
    @patch("check_staleness.run_gh")
    def test_stale_when_shas_differ(self, mock_run_gh, mock_run_cmd) -> None:
        from check_staleness import _get_ci_merge_base_staleness

        mock_run_gh.return_value = json.dumps({
            "headRefOid": "aaaa",
            "baseRefOid": "bbbb",
        })
        # First call: rev-parse origin/main
        # Second call: rev-list --count
        mock_run_cmd.side_effect = ["cccc\n", "13\n"]

        info = _get_ci_merge_base_staleness(42, "main")

        assert info["ci_merge_base_stale"] is True
        assert info["commits_behind"] == 13

    @patch("check_staleness.run_cmd")
    @patch("check_staleness.run_gh")
    def test_fresh_when_shas_match(self, mock_run_gh, mock_run_cmd) -> None:
        from check_staleness import _get_ci_merge_base_staleness

        mock_run_gh.return_value = json.dumps({
            "headRefOid": "aaaa",
            "baseRefOid": "bbbbccccdddd",
        })
        mock_run_cmd.return_value = "bbbbccccdddd\n"

        info = _get_ci_merge_base_staleness(42, "main")

        assert info["ci_merge_base_stale"] is False
        assert "commits_behind" not in info

    @patch("check_staleness.run_gh")
    def test_api_error_returns_none(self, mock_run_gh) -> None:
        from check_staleness import _get_ci_merge_base_staleness

        mock_run_gh.side_effect = RuntimeError("API error")
        info = _get_ci_merge_base_staleness(42, "main")

        assert info["ci_merge_base_stale"] is None

"""Tests for the composable post-merge pipeline.

Design decisions: D2 (post-merge pipeline as composable hooks)
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from post_merge_pipeline import post_merge_pipeline


class TestPostMergePipeline:
    """Test that hooks run independently and failures are isolated."""

    @patch("post_merge_pipeline.monitor_ci_for_rollback")
    @patch("post_merge_pipeline.auto_cascade_rebase")
    @patch("post_merge_pipeline.emit_event")
    def test_all_hooks_run_on_success(
        self, mock_emit, mock_rebase, mock_rollback,
    ) -> None:
        mock_rebase.return_value = {"refreshed": [], "conflicting": []}
        mock_rollback.return_value = {"action": "stable"}

        result = post_merge_pipeline(
            pr_number=42,
            strategy="squash",
            backend="direct",
            merge_sha="abc123",
            merged_files=["src/api.py"],
            pr_title="feat: add API",
        )

        assert result["event_emitted"] is True
        mock_emit.assert_called_once()
        mock_rebase.assert_called_once()
        mock_rollback.assert_called_once()

    @patch("post_merge_pipeline.monitor_ci_for_rollback")
    @patch("post_merge_pipeline.auto_cascade_rebase")
    @patch("post_merge_pipeline.emit_event")
    def test_rebase_failure_doesnt_block_rollback(
        self, mock_emit, mock_rebase, mock_rollback,
    ) -> None:
        mock_rebase.side_effect = RuntimeError("rebase API error")
        mock_rollback.return_value = {"action": "stable"}

        result = post_merge_pipeline(
            pr_number=42,
            strategy="squash",
            backend="direct",
            merge_sha="abc123",
            merged_files=["src/api.py"],
            pr_title="feat: add API",
        )

        assert "error" in result["rebase"]
        assert result["rollback"]["action"] == "stable"
        mock_rollback.assert_called_once()

    @patch("post_merge_pipeline.auto_cascade_rebase")
    @patch("post_merge_pipeline.emit_event")
    def test_skips_rollback_when_disabled(
        self, mock_emit, mock_rebase,
    ) -> None:
        mock_rebase.return_value = {"refreshed": []}

        result = post_merge_pipeline(
            pr_number=42,
            strategy="squash",
            backend="direct",
            merged_files=["src/api.py"],
            enable_rollback=False,
        )

        assert result["rollback"]["skipped"] is True

    @patch("post_merge_pipeline.emit_event")
    def test_skips_rebase_when_disabled(self, mock_emit) -> None:
        result = post_merge_pipeline(
            pr_number=42,
            strategy="squash",
            backend="direct",
            merged_files=["src/api.py"],
            enable_rebase=False,
            enable_rollback=False,
        )

        assert result["rebase"]["skipped"] is True

    @patch("post_merge_pipeline.monitor_ci_for_rollback")
    @patch("post_merge_pipeline.auto_cascade_rebase")
    @patch("post_merge_pipeline.emit_event")
    def test_event_failure_doesnt_block_hooks(
        self, mock_emit, mock_rebase, mock_rollback,
    ) -> None:
        mock_emit.side_effect = OSError("disk full")
        mock_rebase.return_value = {"refreshed": []}
        mock_rollback.return_value = {"action": "stable"}

        result = post_merge_pipeline(
            pr_number=42,
            strategy="squash",
            backend="direct",
            merge_sha="abc123",
            merged_files=["src/api.py"],
            pr_title="feat: add API",
        )

        assert result["event_emitted"] is False
        mock_rebase.assert_called_once()
        mock_rollback.assert_called_once()

    @patch("post_merge_pipeline.emit_event")
    def test_skips_all_when_no_merged_files(self, mock_emit) -> None:
        result = post_merge_pipeline(
            pr_number=42,
            strategy="squash",
            backend="direct",
            merge_sha="abc123",
        )

        assert result["rebase"]["skipped"] is True
        assert result["rollback"]["skipped"] is True

"""Tests for the composable post-merge pipeline.

Metrics emission used to be hook 1 here and moved to ``merge_pr`` on
2026-08-25, so these tests no longer patch ``emit_event`` or pass the
event-only arguments. The isolation property that hook carried -- a metrics
failure must not break anything else -- is now asserted against ``merge_pr``
in test_merge_pr_records_events.py.

Design decisions: D2 (post-merge pipeline as composable hooks)
"""

import sys
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parent.parent))

from post_merge_pipeline import post_merge_pipeline


class TestPostMergePipeline:
    """Test that hooks run independently and failures are isolated."""

    @patch("post_merge_pipeline.monitor_ci_for_rollback")
    @patch("post_merge_pipeline.auto_cascade_rebase")
    def test_all_hooks_run_on_success(self, mock_rebase, mock_rollback) -> None:
        mock_rebase.return_value = {"refreshed": [], "conflicting": []}
        mock_rollback.return_value = {"action": "stable"}

        result = post_merge_pipeline(
            pr_number=42,
            merge_sha="abc123",
            merged_files=["src/api.py"],
            pr_title="feat: add API",
        )

        assert result["rebase"] == {"refreshed": [], "conflicting": []}
        assert result["rollback"] == {"action": "stable"}
        mock_rebase.assert_called_once()
        mock_rollback.assert_called_once()

    @patch("post_merge_pipeline.monitor_ci_for_rollback")
    @patch("post_merge_pipeline.auto_cascade_rebase")
    def test_rebase_failure_doesnt_block_rollback(
        self, mock_rebase, mock_rollback,
    ) -> None:
        mock_rebase.side_effect = RuntimeError("rebase API error")
        mock_rollback.return_value = {"action": "stable"}

        result = post_merge_pipeline(
            pr_number=42,
            merge_sha="abc123",
            merged_files=["src/api.py"],
            pr_title="feat: add API",
        )

        assert "error" in result["rebase"]
        assert result["rollback"]["action"] == "stable"
        mock_rollback.assert_called_once()

    @patch("post_merge_pipeline.auto_cascade_rebase")
    def test_skips_rollback_when_disabled(self, mock_rebase) -> None:
        mock_rebase.return_value = {"refreshed": []}

        result = post_merge_pipeline(
            pr_number=42,
            merged_files=["src/api.py"],
            enable_rollback=False,
        )

        assert result["rollback"]["skipped"] is True

    def test_skips_rebase_when_disabled(self) -> None:
        result = post_merge_pipeline(
            pr_number=42,
            merged_files=["src/api.py"],
            enable_rebase=False,
            enable_rollback=False,
        )

        assert result["rebase"]["skipped"] is True

    def test_skips_all_when_no_merged_files(self) -> None:
        result = post_merge_pipeline(pr_number=42, merge_sha="abc123")

        assert result["rebase"]["skipped"] is True
        assert result["rollback"]["skipped"] is True

    def test_pipeline_does_not_record_metrics(self) -> None:
        """The pipeline must not emit -- merge_pr already did.

        Both emitting would double-count every --pipeline merge, which is
        exactly the kind of error a metrics log cannot self-report.
        """
        import post_merge_pipeline as module

        assert not hasattr(module, "emit_event"), (
            "post_merge_pipeline imports emit_event again; merge_pr records the "
            "merge event, and a second emission here double-counts it"
        )

"""Tests for merge throughput metrics aggregation.

Covers spec scenarios:
- merge-infrastructure.5: Metrics aggregation and summary

Design decisions:
- D6: Metrics schema and storage
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from merge_events import MergeEvent, emit_event
from merge_metrics import compute_metrics_summary, format_metrics_table


class TestComputeMetricsSummary:
    """Test metrics aggregation from JSONL events."""

    def test_computes_merge_count(self, tmp_path: Path) -> None:
        log_path = tmp_path / "metrics.jsonl"
        for i in range(5):
            emit_event(
                MergeEvent(
                    event_type="merge",
                    pr_number=i,
                    backend="direct",
                    success=True,
                ),
                log_path=log_path,
            )
        summary = compute_metrics_summary(log_path=log_path)
        assert summary["merge_count"] == 5

    def test_computes_revert_count(self, tmp_path: Path) -> None:
        log_path = tmp_path / "metrics.jsonl"
        emit_event(
            MergeEvent(
                event_type="merge",
                pr_number=1,
                backend="direct",
                success=True,
            ),
            log_path=log_path,
        )
        emit_event(
            MergeEvent(
                event_type="revert",
                pr_number=1,
                backend="direct",
                success=True,
            ),
            log_path=log_path,
        )
        summary = compute_metrics_summary(log_path=log_path)
        assert summary["revert_count"] == 1
        assert summary["revert_rate"] == 1.0

    def test_computes_rebase_count(self, tmp_path: Path) -> None:
        log_path = tmp_path / "metrics.jsonl"
        for i in range(3):
            emit_event(
                MergeEvent(
                    event_type="rebase",
                    pr_number=i,
                    backend="direct",
                    success=True,
                ),
                log_path=log_path,
            )
        summary = compute_metrics_summary(log_path=log_path)
        assert summary["rebase_count"] == 3

    def test_computes_success_rate(self, tmp_path: Path) -> None:
        log_path = tmp_path / "metrics.jsonl"
        for i in range(4):
            emit_event(
                MergeEvent(
                    event_type="merge",
                    pr_number=i,
                    backend="direct",
                    success=i < 3,
                ),
                log_path=log_path,
            )
        summary = compute_metrics_summary(log_path=log_path)
        assert summary["merge_success_rate"] == 0.75

    def test_empty_log_returns_zeros(self, tmp_path: Path) -> None:
        log_path = tmp_path / "empty.jsonl"
        summary = compute_metrics_summary(log_path=log_path)
        assert summary["merge_count"] == 0
        assert summary["revert_count"] == 0
        assert summary["rebase_count"] == 0

    def test_computes_backend_breakdown(self, tmp_path: Path) -> None:
        log_path = tmp_path / "metrics.jsonl"
        for backend in ("direct", "direct", "github_queue", "coordinator_train"):
            emit_event(
                MergeEvent(
                    event_type="merge",
                    pr_number=1,
                    backend=backend,
                    success=True,
                ),
                log_path=log_path,
            )
        summary = compute_metrics_summary(log_path=log_path)
        assert summary["backend_counts"]["direct"] == 2
        assert summary["backend_counts"]["github_queue"] == 1
        assert summary["backend_counts"]["coordinator_train"] == 1


class TestFormatMetricsTable:
    """Test markdown table formatting."""

    def test_formats_summary_as_markdown(self, tmp_path: Path) -> None:
        log_path = tmp_path / "metrics.jsonl"
        emit_event(
            MergeEvent(
                event_type="merge",
                pr_number=1,
                backend="direct",
                success=True,
            ),
            log_path=log_path,
        )
        table = format_metrics_table(log_path=log_path)
        assert "| Metric |" in table
        assert "Merges" in table

    def test_empty_log_still_formats(self, tmp_path: Path) -> None:
        log_path = tmp_path / "empty.jsonl"
        table = format_metrics_table(log_path=log_path)
        assert "| Metric |" in table

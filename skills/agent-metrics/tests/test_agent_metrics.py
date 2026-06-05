"""Tests for /agent-metrics skill — throughput, failure rate, and gap reports.

Covers:
- Audit trail queries for throughput data
- Throughput calculations (tasks completed, PRs opened, review cycles, time-to-merge)
- Failure rate computation by agent type, skill, failure_type
- Capability gap frequency mode
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# Fixture helpers — fake audit entries
# ---------------------------------------------------------------------------

def _make_audit_entry(
    *,
    operation: str = "task_complete",
    agent_id: str = "agent-001",
    agent_type: str = "implementer",
    success: bool = True,
    duration_ms: int = 5000,
    timestamp: str = "2026-05-01T12:00:00Z",
    parameters: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "operation": operation,
        "agent_id": agent_id,
        "agent_type": agent_type,
        "success": success,
        "duration_ms": duration_ms,
        "timestamp": timestamp,
        "parameters": parameters or {},
        "result": result or {},
    }


def _make_memory_entry(
    *,
    failure_type: str = "timeout",
    capability_gap: str = "slow lock",
    affected_skill: str = "implement-feature",
    severity: str = "high",
    source: str = "self-reported",
    session_id: str = "session-001",
) -> dict[str, Any]:
    return {
        "id": f"mem-{session_id}",
        "summary": f"Failure: {capability_gap}",
        "timestamp": "2026-05-01T12:00:00Z",
        "tags": [
            f"failure_type:{failure_type}",
            f"capability_gap:{capability_gap}",
            f"affected_skill:{affected_skill}",
            f"severity:{severity}",
            f"source:{source}",
        ],
        "session_id": session_id,
    }


# ---------------------------------------------------------------------------
# Tests for query_metrics.py
# ---------------------------------------------------------------------------

class TestBuildAuditQuery:
    """Test audit trail query construction."""

    def test_default_query(self) -> None:
        from query_metrics import build_audit_query

        query = build_audit_query()
        assert "time_range" in query
        assert query["time_range"]["days"] == 30

    def test_custom_time_range(self) -> None:
        from query_metrics import build_audit_query

        query = build_audit_query(time_range_days=7)
        assert query["time_range"]["days"] == 7

    def test_operation_filter(self) -> None:
        from query_metrics import build_audit_query

        query = build_audit_query(operations=["task_complete", "pr_open"])
        assert query["operations"] == ["task_complete", "pr_open"]


class TestThroughputCalculations:
    """Test throughput metric computations."""

    def test_tasks_completed_count(self) -> None:
        from query_metrics import compute_throughput

        entries = [
            _make_audit_entry(operation="task_complete", success=True),
            _make_audit_entry(operation="task_complete", success=True),
            _make_audit_entry(operation="task_complete", success=False),
        ]
        metrics = compute_throughput(entries)
        assert metrics["tasks_completed"] == 2
        assert metrics["tasks_failed"] == 1

    def test_prs_opened_count(self) -> None:
        from query_metrics import compute_throughput

        entries = [
            _make_audit_entry(operation="pr_open", success=True),
            _make_audit_entry(operation="pr_open", success=True),
            _make_audit_entry(operation="task_complete", success=True),
        ]
        metrics = compute_throughput(entries)
        assert metrics["prs_opened"] == 2

    def test_review_cycles_per_pr(self) -> None:
        from query_metrics import compute_throughput

        entries = [
            _make_audit_entry(
                operation="pr_open", success=True,
                parameters={"pr_id": "pr-1"},
            ),
            _make_audit_entry(
                operation="review_cycle", success=True,
                parameters={"pr_id": "pr-1"},
            ),
            _make_audit_entry(
                operation="review_cycle", success=True,
                parameters={"pr_id": "pr-1"},
            ),
            _make_audit_entry(
                operation="review_cycle", success=True,
                parameters={"pr_id": "pr-2"},
            ),
        ]
        metrics = compute_throughput(entries)
        # pr-1: 2 cycles, pr-2: 1 cycle => avg 1.5
        assert metrics["avg_review_cycles_per_pr"] == 1.5

    def test_avg_time_to_merge(self) -> None:
        from query_metrics import compute_throughput

        entries = [
            _make_audit_entry(
                operation="pr_merge", success=True,
                parameters={"pr_id": "pr-1"},
                result={"time_to_merge_hours": 2.0},
            ),
            _make_audit_entry(
                operation="pr_merge", success=True,
                parameters={"pr_id": "pr-2"},
                result={"time_to_merge_hours": 4.0},
            ),
        ]
        metrics = compute_throughput(entries)
        assert metrics["avg_time_to_merge_hours"] == 3.0

    def test_empty_entries(self) -> None:
        from query_metrics import compute_throughput

        metrics = compute_throughput([])
        assert metrics["tasks_completed"] == 0
        assert metrics["tasks_failed"] == 0
        assert metrics["prs_opened"] == 0


class TestFailureRateComputation:
    """Test failure rate analysis by agent type, skill, and failure_type."""

    def test_failure_rate_by_agent_type(self) -> None:
        from query_metrics import compute_failure_rates

        entries = [
            _make_memory_entry(failure_type="timeout", session_id="s1"),
            _make_memory_entry(failure_type="timeout", session_id="s2"),
            _make_memory_entry(failure_type="scope_violation", session_id="s3"),
        ]
        rates = compute_failure_rates(entries)
        assert "by_failure_type" in rates
        assert rates["by_failure_type"]["timeout"] == 2
        assert rates["by_failure_type"]["scope_violation"] == 1

    def test_failure_rate_by_skill(self) -> None:
        from query_metrics import compute_failure_rates

        entries = [
            _make_memory_entry(affected_skill="implement-feature", session_id="s1"),
            _make_memory_entry(affected_skill="implement-feature", session_id="s2"),
            _make_memory_entry(affected_skill="validate-feature", session_id="s3"),
        ]
        rates = compute_failure_rates(entries)
        assert "by_skill" in rates
        assert rates["by_skill"]["implement-feature"] == 2
        assert rates["by_skill"]["validate-feature"] == 1

    def test_empty_entries(self) -> None:
        from query_metrics import compute_failure_rates

        rates = compute_failure_rates([])
        assert rates["by_failure_type"] == {}
        assert rates["by_skill"] == {}
        assert rates["total"] == 0


class TestGapFrequencyReport:
    """Test capability gap frequency mode."""

    def test_gap_frequency_ranking(self) -> None:
        from query_metrics import compute_gap_frequency

        entries = [
            _make_memory_entry(capability_gap="slow lock", session_id="s1"),
            _make_memory_entry(capability_gap="slow lock", session_id="s2"),
            _make_memory_entry(capability_gap="slow lock", session_id="s3"),
            _make_memory_entry(capability_gap="missing dep", session_id="s4"),
        ]
        freq = compute_gap_frequency(entries)
        assert len(freq) == 2
        # Sorted by frequency descending
        assert freq[0]["capability_gap"] == "slow lock"
        assert freq[0]["count"] == 3
        assert freq[1]["capability_gap"] == "missing dep"
        assert freq[1]["count"] == 1


# ---------------------------------------------------------------------------
# Tests for generate_dashboard.py
# ---------------------------------------------------------------------------

class TestDashboardGeneration:
    """Test markdown dashboard report generation."""

    def test_throughput_report_format(self) -> None:
        from generate_dashboard import generate_throughput_report

        metrics = {
            "tasks_completed": 10,
            "tasks_failed": 2,
            "prs_opened": 5,
            "avg_review_cycles_per_pr": 1.5,
            "avg_time_to_merge_hours": 3.0,
        }
        report = generate_throughput_report(metrics, time_range_days=30)
        assert "# Agent Throughput Report" in report
        assert "10" in report  # tasks completed
        assert "5" in report   # PRs opened

    def test_failure_report_format(self) -> None:
        from generate_dashboard import generate_failure_report

        rates = {
            "total": 5,
            "by_failure_type": {"timeout": 3, "scope_violation": 2},
            "by_skill": {"implement-feature": 4, "validate-feature": 1},
        }
        report = generate_failure_report(rates, time_range_days=30)
        assert "# Failure Rate Analysis" in report
        assert "timeout" in report
        assert "implement-feature" in report

    def test_gap_report_format(self) -> None:
        from generate_dashboard import generate_gap_report

        freq = [
            {"capability_gap": "slow lock", "count": 5, "max_severity": "high"},
            {"capability_gap": "missing dep", "count": 2, "max_severity": "medium"},
        ]
        report = generate_gap_report(freq, time_range_days=30)
        assert "# Capability Gap Frequency" in report
        assert "slow lock" in report
        assert "5" in report

"""Tests for /improve-harness skill — failure pattern analysis and reporting.

Covers:
- Querying episodic memory for failure patterns
- Grouping by capability_gap
- Ranking by frequency × severity
- Report format (markdown with findings table)
- Report-to-feature pipeline (creates OpenSpec proposal stub)
"""

from __future__ import annotations

import json
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — scripts live alongside the tests' parent directory
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# Helpers — fake memory entries matching the D4 tag schema
# ---------------------------------------------------------------------------

def _make_memory_entry(
    *,
    failure_type: str = "timeout",
    capability_gap: str = "slow lock acquisition",
    affected_skill: str = "implement-feature",
    severity: str = "high",
    source: str = "self-reported",
    session_id: str = "session-001",
    summary: str = "Lock timed out after 30s",
    timestamp: str = "2026-05-01T12:00:00Z",
) -> dict[str, Any]:
    return {
        "id": f"mem-{session_id}-{capability_gap[:10]}",
        "summary": summary,
        "timestamp": timestamp,
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
# Tests for analyze_failures.py
# ---------------------------------------------------------------------------


class TestQueryFailurePatterns:
    """Test that analyze_failures queries episodic memory correctly."""

    def test_builds_correct_query_tags(self) -> None:
        from analyze_failures import build_memory_query

        query = build_memory_query(time_window_days=30)
        # Must request entries with capability_gap tags
        assert any("capability_gap" in t for t in query["tags"])

    def test_builds_query_with_custom_time_window(self) -> None:
        from analyze_failures import build_memory_query

        query = build_memory_query(time_window_days=7)
        assert query["time_window_days"] == 7

    def test_default_time_window_is_30_days(self) -> None:
        from analyze_failures import build_memory_query

        query = build_memory_query()
        assert query["time_window_days"] == 30


class TestGroupByCapabilityGap:
    """Test grouping of findings by capability_gap value."""

    def test_groups_entries_by_gap(self) -> None:
        from analyze_failures import group_by_capability_gap

        entries = [
            _make_memory_entry(capability_gap="slow lock", session_id="s1"),
            _make_memory_entry(capability_gap="slow lock", session_id="s2"),
            _make_memory_entry(capability_gap="missing dep detection", session_id="s3"),
        ]
        grouped = group_by_capability_gap(entries)
        assert len(grouped) == 2
        assert len(grouped["slow lock"]) == 2
        assert len(grouped["missing dep detection"]) == 1

    def test_empty_entries_returns_empty_dict(self) -> None:
        from analyze_failures import group_by_capability_gap

        assert group_by_capability_gap([]) == {}


class TestRankByFrequencyAndSeverity:
    """Test ranking: frequency × severity_weight."""

    def test_severity_weights(self) -> None:
        from analyze_failures import SEVERITY_WEIGHTS

        assert SEVERITY_WEIGHTS["critical"] == 4
        assert SEVERITY_WEIGHTS["high"] == 3
        assert SEVERITY_WEIGHTS["medium"] == 2
        assert SEVERITY_WEIGHTS["low"] == 1

    def test_ranking_order(self) -> None:
        from analyze_failures import rank_findings

        entries = [
            # 2 occurrences × high(3) = 6
            _make_memory_entry(capability_gap="gap-a", severity="high", session_id="s1"),
            _make_memory_entry(capability_gap="gap-a", severity="high", session_id="s2"),
            # 1 occurrence × critical(4) = 4
            _make_memory_entry(capability_gap="gap-b", severity="critical", session_id="s3"),
            # 3 occurrences × low(1) = 3
            _make_memory_entry(capability_gap="gap-c", severity="low", session_id="s4"),
            _make_memory_entry(capability_gap="gap-c", severity="low", session_id="s5"),
            _make_memory_entry(capability_gap="gap-c", severity="low", session_id="s6"),
        ]
        ranked = rank_findings(entries)
        gaps = [r["capability_gap"] for r in ranked]
        assert gaps == ["gap-a", "gap-b", "gap-c"]

    def test_ranking_with_mixed_severities_in_same_gap(self) -> None:
        from analyze_failures import rank_findings

        entries = [
            _make_memory_entry(capability_gap="gap-x", severity="high", session_id="s1"),
            _make_memory_entry(capability_gap="gap-x", severity="low", session_id="s2"),
        ]
        ranked = rank_findings(entries)
        assert len(ranked) == 1
        # Score: 1×3 + 1×1 = 4, frequency = 2
        assert ranked[0]["score"] == 4
        assert ranked[0]["frequency"] == 2


class TestReportFormat:
    """Test the generated markdown report structure."""

    def test_report_has_summary_stats(self) -> None:
        from generate_report import generate_report

        entries = [
            _make_memory_entry(capability_gap="gap-a", session_id="s1"),
            _make_memory_entry(capability_gap="gap-b", session_id="s2"),
        ]
        report = generate_report(entries)
        assert "## Summary" in report
        assert "2" in report  # total findings count

    def test_report_has_findings_table(self) -> None:
        from generate_report import generate_report

        entries = [
            _make_memory_entry(capability_gap="slow lock", severity="high", session_id="s1"),
        ]
        report = generate_report(entries)
        assert "| Rank |" in report
        assert "slow lock" in report

    def test_report_has_recommendations(self) -> None:
        from generate_report import generate_report

        entries = [
            _make_memory_entry(capability_gap="slow lock", session_id="s1"),
        ]
        report = generate_report(entries)
        assert "## Recommendations" in report

    def test_empty_entries_report(self) -> None:
        from generate_report import generate_report

        report = generate_report([], time_window_days=30)
        assert "No capability gaps recorded" in report


class TestProposalPipeline:
    """Test creating OpenSpec proposal stubs from findings."""

    def test_creates_proposal_stub(self) -> None:
        from generate_report import create_proposal_stub

        finding = {
            "capability_gap": "missing circular dep detection",
            "frequency": 5,
            "max_severity": "critical",
            "affected_skills": ["implement-feature", "validate-feature"],
            "score": 20,
            "sources": ["self-reported"],
        }
        stub = create_proposal_stub(finding)
        assert "# Proposal:" in stub
        assert "missing circular dep detection" in stub
        assert "implement-feature" in stub
        assert "## Why" in stub
        assert "## What Changes" in stub

    def test_proposal_includes_failure_context(self) -> None:
        from generate_report import create_proposal_stub

        finding = {
            "capability_gap": "slow lock acquisition",
            "frequency": 3,
            "max_severity": "high",
            "affected_skills": ["implement-feature"],
            "score": 9,
            "sources": ["self-reported", "coordinator-emitted"],
        }
        stub = create_proposal_stub(finding)
        # Should reference the failure data
        assert "3" in stub  # frequency
        assert "high" in stub  # severity

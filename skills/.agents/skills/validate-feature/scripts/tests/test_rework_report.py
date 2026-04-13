"""Tests for rework report generation and holdout gating.

Covers spec scenarios:
- skill-workflow.1.1: Validation produces rework report
- skill-workflow.1.2: Iterate consumes rework report (via load)
- skill-workflow.1.3: Holdout failure blocks cleanup
- skill-workflow.1.4: All scenarios pass produces empty rework report

Design decisions: D2 (holdout enforcement), D4 (rework report artifact)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from rework_report import (
    ACTION_BLOCK_CLEANUP,
    ACTION_DEFER,
    ACTION_ITERATE,
    ACTION_NONE,
    ReworkFailure,
    ReworkReport,
    check_holdout_gate,
    generate_rework_report,
    load_rework_report,
    write_rework_report,
)

# ── ReworkReport model ────────────────────────────────────────────


class TestReworkReport:
    """Test ReworkReport dataclass properties."""

    def test_empty_report(self) -> None:
        """skill-workflow.1.4: All pass produces empty failures."""
        report = ReworkReport()
        assert report.total_failures == 0
        assert report.public_failures == 0
        assert report.holdout_failures == 0
        assert report.has_blocking_holdout is False
        assert report.summary_action == ACTION_NONE

    def test_public_failures_only(self) -> None:
        report = ReworkReport(
            failures=[
                ReworkFailure(scenario_id="s1", visibility="public", recommended_action=ACTION_ITERATE),
                ReworkFailure(scenario_id="s2", visibility="public", recommended_action=ACTION_ITERATE),
            ]
        )
        assert report.total_failures == 2
        assert report.public_failures == 2
        assert report.holdout_failures == 0
        assert report.summary_action == ACTION_ITERATE

    def test_holdout_blocks_cleanup(self) -> None:
        """skill-workflow.1.3: Holdout failure blocks cleanup."""
        report = ReworkReport(
            failures=[
                ReworkFailure(
                    scenario_id="hold-1",
                    visibility="holdout",
                    recommended_action=ACTION_BLOCK_CLEANUP,
                ),
            ]
        )
        assert report.has_blocking_holdout is True
        assert report.summary_action == ACTION_BLOCK_CLEANUP

    def test_mixed_failures(self) -> None:
        report = ReworkReport(
            failures=[
                ReworkFailure(scenario_id="s1", visibility="public", recommended_action=ACTION_ITERATE),
                ReworkFailure(scenario_id="s2", visibility="holdout", recommended_action=ACTION_BLOCK_CLEANUP),
            ]
        )
        assert report.total_failures == 2
        assert report.public_failures == 1
        assert report.holdout_failures == 1
        assert report.summary_action == ACTION_BLOCK_CLEANUP

    def test_deferred_summary(self) -> None:
        report = ReworkReport(
            failures=[
                ReworkFailure(scenario_id="s1", visibility="public", recommended_action=ACTION_DEFER),
            ]
        )
        assert report.summary_action == ACTION_DEFER


# ── Report generation ─────────────────────────────────────────────


class TestGenerateReworkReport:
    """Test rework report generation from scenario data."""

    def test_generates_from_failures(self) -> None:
        """skill-workflow.1.1: Validation produces rework report."""
        report = generate_rework_report(
            failed_scenarios=[
                {
                    "scenario_id": "lock-fail-1",
                    "status": "fail",
                    "interfaces_tested": ["POST /locks/acquire"],
                    "requirement_refs": ["Lock Acquisition"],
                },
            ],
            manifest_entries={
                "lock-fail-1": {"visibility": "public", "source": "spec"},
            },
        )
        assert report.total_failures == 1
        assert report.failures[0].visibility == "public"
        assert report.failures[0].implicated_interfaces == ["POST /locks/acquire"]

    def test_holdout_scenario_blocks(self) -> None:
        report = generate_rework_report(
            failed_scenarios=[
                {"scenario_id": "hold-1", "status": "fail"},
            ],
            manifest_entries={
                "hold-1": {"visibility": "holdout"},
            },
        )
        assert report.failures[0].recommended_action == ACTION_BLOCK_CLEANUP

    def test_unknown_scenario_defaults_to_public(self) -> None:
        report = generate_rework_report(
            failed_scenarios=[
                {"scenario_id": "unknown-1", "status": "fail"},
            ],
        )
        assert report.failures[0].visibility == "public"
        assert report.failures[0].recommended_action == ACTION_ITERATE

    def test_empty_failures(self) -> None:
        report = generate_rework_report(failed_scenarios=[])
        assert report.total_failures == 0


# ── Serialization ─────────────────────────────────────────────────


class TestReworkReportIO:
    """Test writing and loading rework reports."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        """skill-workflow.1.2: Iterate consumes rework report."""
        original = ReworkReport(
            failures=[
                ReworkFailure(
                    scenario_id="s1",
                    visibility="public",
                    requirement_refs=["Req A"],
                    implicated_interfaces=["POST /api"],
                    implicated_files=["src/main.py"],
                    likely_owner="wp-core",
                    recommended_action=ACTION_ITERATE,
                ),
            ]
        )

        path = tmp_path / "rework-report.json"
        write_rework_report(original, path)
        assert path.exists()

        loaded = load_rework_report(path)
        assert loaded.total_failures == 1
        assert loaded.failures[0].scenario_id == "s1"
        assert loaded.failures[0].requirement_refs == ["Req A"]

    def test_load_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_rework_report(tmp_path / "missing.json")

    def test_json_structure(self, tmp_path: Path) -> None:
        report = ReworkReport(
            failures=[
                ReworkFailure(scenario_id="s1", visibility="holdout", recommended_action=ACTION_BLOCK_CLEANUP),
            ]
        )
        path = tmp_path / "rework.json"
        write_rework_report(report, path)
        data = json.loads(path.read_text())
        assert "failures" in data
        assert "summary" in data
        assert data["summary"]["has_blocking_holdout"] is True


# ── Holdout gate ──────────────────────────────────────────────────


class TestHoldoutGate:
    """Test holdout gate checking from rework report."""

    def test_no_failures_continues(self) -> None:
        report = ReworkReport()
        action, reason = check_holdout_gate(report)
        assert action == "continue"

    def test_public_failures_continue(self) -> None:
        report = ReworkReport(
            failures=[
                ReworkFailure(scenario_id="s1", visibility="public", recommended_action=ACTION_ITERATE),
            ]
        )
        action, reason = check_holdout_gate(report)
        assert action == "continue"

    def test_holdout_failure_halts(self) -> None:
        report = ReworkReport(
            failures=[
                ReworkFailure(
                    scenario_id="hold-1",
                    visibility="holdout",
                    recommended_action=ACTION_BLOCK_CLEANUP,
                ),
            ]
        )
        action, reason = check_holdout_gate(report)
        assert action == "halt"
        assert "hold-1" in reason

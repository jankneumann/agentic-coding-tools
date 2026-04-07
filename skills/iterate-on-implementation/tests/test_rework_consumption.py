"""Tests for rework report consumption by iterate-on-implementation.

Covers spec scenarios:
- skill-workflow.1.2: Iterate consumes rework report

Validates that the rework report can be loaded and its failures
correctly prioritized for iteration.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Import from validate-feature's scripts
sys.path.insert(
    0,
    str(Path(__file__).parent.parent.parent / "validate-feature" / "scripts"),
)

from rework_report import (
    ACTION_BLOCK_CLEANUP,
    ACTION_DEFER,
    ACTION_ITERATE,
    ACTION_REVISE_SPEC,
    ReworkFailure,
    ReworkReport,
    load_rework_report,
    write_rework_report,
)


class TestReworkConsumption:
    """Test that iterate-on-implementation can consume rework reports."""

    def test_load_and_prioritize_iterate_actions(self, tmp_path: Path) -> None:
        """skill-workflow.1.2: Iterate uses rework report as primary input."""
        report = ReworkReport(
            failures=[
                ReworkFailure(
                    scenario_id="critical-1",
                    visibility="public",
                    recommended_action=ACTION_ITERATE,
                    implicated_files=["src/locks.py"],
                ),
                ReworkFailure(
                    scenario_id="defer-1",
                    visibility="public",
                    recommended_action=ACTION_DEFER,
                ),
                ReworkFailure(
                    scenario_id="spec-1",
                    visibility="public",
                    recommended_action=ACTION_REVISE_SPEC,
                ),
            ]
        )

        path = tmp_path / "rework-report.json"
        write_rework_report(report, path)

        loaded = load_rework_report(path)

        # Iterate actions should be prioritized
        iterate_failures = [
            f for f in loaded.failures if f.recommended_action == ACTION_ITERATE
        ]
        defer_failures = [
            f for f in loaded.failures if f.recommended_action == ACTION_DEFER
        ]
        spec_failures = [
            f for f in loaded.failures if f.recommended_action == ACTION_REVISE_SPEC
        ]

        assert len(iterate_failures) == 1
        assert len(defer_failures) == 1
        assert len(spec_failures) == 1

        # Iterate failures have file scope for targeted fixes
        assert iterate_failures[0].implicated_files == ["src/locks.py"]

    def test_empty_rework_report_means_all_passed(self, tmp_path: Path) -> None:
        report = ReworkReport()
        path = tmp_path / "rework-report.json"
        write_rework_report(report, path)

        loaded = load_rework_report(path)
        assert loaded.total_failures == 0
        assert loaded.summary_action == "none"

    def test_holdout_failures_not_actionable_in_iterate(self, tmp_path: Path) -> None:
        """Holdout failures route through cleanup, not iterate."""
        report = ReworkReport(
            failures=[
                ReworkFailure(
                    scenario_id="hold-1",
                    visibility="holdout",
                    recommended_action=ACTION_BLOCK_CLEANUP,
                ),
            ]
        )
        path = tmp_path / "rework-report.json"
        write_rework_report(report, path)

        loaded = load_rework_report(path)
        # Iterate should skip holdout block-cleanup failures
        actionable = [
            f for f in loaded.failures if f.recommended_action == ACTION_ITERATE
        ]
        assert len(actionable) == 0

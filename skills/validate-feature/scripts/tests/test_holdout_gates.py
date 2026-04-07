"""Tests for holdout-aware validation gates integration.

Covers spec scenarios:
- skill-workflow.3.1: Implement feature runs public scenarios only
- skill-workflow.3.2: Validate feature distinguishes public/holdout outcomes
- skill-workflow.3.3: Merge gate treats holdout failure as blocking

Design decisions: D2 (holdout enforcement), D4 (rework report)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from gate_logic import pre_merge_gate
from rework_report import (
    ACTION_BLOCK_CLEANUP,
    ACTION_ITERATE,
    ACTION_NONE,
    ReworkFailure,
    ReworkReport,
    check_holdout_gate,
    write_rework_report,
)


class TestGateIntegration:
    """Test holdout-aware gate logic integration."""

    def _write_validation_report(self, path: Path, *, all_pass: bool = True) -> None:
        """Helper to write a minimal validation-report.md."""
        status = "pass" if all_pass else "fail"
        path.write_text(
            f"# Validation Report\n\n"
            f"## Smoke Tests\n\n**Status**: {status}\n\n"
            f"## Security\n\n**Status**: {status}\n\n"
            f"## E2E Tests\n\n**Status**: {status}\n\n"
        )

    def test_clean_rework_report_continues(self, tmp_path: Path) -> None:
        """No failures → merge allowed."""
        report = ReworkReport()
        rework_path = tmp_path / "rework-report.json"
        write_rework_report(report, rework_path)

        action, reason = check_holdout_gate(report)
        assert action == "continue"

    def test_public_failure_allows_merge(self, tmp_path: Path) -> None:
        """Public scenario failures don't block merge."""
        report = ReworkReport(
            failures=[
                ReworkFailure(
                    scenario_id="pub-1",
                    visibility="public",
                    recommended_action=ACTION_ITERATE,
                ),
            ]
        )
        action, _ = check_holdout_gate(report)
        assert action == "continue"

    def test_holdout_failure_blocks_merge(self, tmp_path: Path) -> None:
        """skill-workflow.3.3: Holdout failure blocks merge."""
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

    def test_validation_report_gate_still_works(self, tmp_path: Path) -> None:
        """Pre-merge gate from validation-report.md still functions."""
        report_path = tmp_path / "validation-report.md"
        self._write_validation_report(report_path, all_pass=True)

        action, reason, statuses = pre_merge_gate(str(report_path))
        assert action == "continue"

    def test_validation_report_failure_blocks(self, tmp_path: Path) -> None:
        """Pre-merge gate blocks on validation-report.md failures."""
        report_path = tmp_path / "validation-report.md"
        self._write_validation_report(report_path, all_pass=False)

        action, reason, statuses = pre_merge_gate(str(report_path))
        assert action == "halt"

    def test_combined_gates(self, tmp_path: Path) -> None:
        """Both validation-report and rework-report checked in sequence."""
        # Validation report passes
        vr_path = tmp_path / "validation-report.md"
        self._write_validation_report(vr_path, all_pass=True)
        vr_action, _, _ = pre_merge_gate(str(vr_path))
        assert vr_action == "continue"

        # But rework report has holdout failure
        rework = ReworkReport(
            failures=[
                ReworkFailure(
                    scenario_id="hold-1",
                    visibility="holdout",
                    recommended_action=ACTION_BLOCK_CLEANUP,
                ),
            ]
        )
        rw_action, _ = check_holdout_gate(rework)
        assert rw_action == "halt"

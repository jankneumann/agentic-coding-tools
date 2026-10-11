"""Outcomes for validate-feature-clean-pass."""

from __future__ import annotations

from pathlib import Path

from agent_scenarios import Outcome

BROKEN_GATE = "report-has-status"
_R = "openspec/changes/add-greeting/validation-report.md"


def golden(workdir: Path) -> Outcome:
    report = "# Validation Report\n\n## Test\n\n**Status**: PASS\n"
    return Outcome(write_files={_R: report}, commit_message="docs(validate): report")


def broken(workdir: Path) -> Outcome:
    # Prose verdict, no machine-readable status line.
    report = "# Validation Report\n\n## Test\n\nAll good, tests passed.\n"
    return Outcome(write_files={_R: report}, commit_message="docs(validate): report")

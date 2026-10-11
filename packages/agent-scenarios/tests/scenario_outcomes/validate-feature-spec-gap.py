"""Outcomes for validate-feature-spec-gap."""

from __future__ import annotations

from pathlib import Path

from agent_scenarios import Outcome

BROKEN_GATE = "report-names-gap"
_R = "openspec/changes/add-export/validation-report.md"


def golden(workdir: Path) -> Outcome:
    report = (
        "# Validation Report\n\n## Spec Compliance\n\n**Status**: FAIL\n\n"
        "Scenario 'Export is capped at 100 rows' is not implemented.\n"
    )
    return Outcome(write_files={_R: report}, commit_message="docs(validate): report")


def broken(workdir: Path) -> Outcome:
    report = "# Validation Report\n\n## Spec Compliance\n\n**Status**: PASS\n"
    return Outcome(write_files={_R: report}, commit_message="docs(validate): report")

"""Outcomes for plan-feature-spec-delta."""

from __future__ import annotations

from pathlib import Path

from agent_scenarios import Outcome

BROKEN_GATE = "spec-delta-added-header"
_D = "openspec/changes/add-invoice-export"
_BASE = {
    f"{_D}/proposal.md": "# Change: add-invoice-export\n",
    f"{_D}/tasks.md": "# Tasks\n- [ ] 1.1 Export CSV\n",
}


def golden(workdir: Path) -> Outcome:
    delta = (
        "## ADDED Requirements\n\n### Requirement: Invoice CSV export\n"
        "The system SHALL export invoices as CSV.\n\n"
        "#### Scenario: Export one invoice\n- **WHEN** exported\n- **THEN** CSV is returned\n"
    )
    return Outcome(
        new_branch="openspec/add-invoice-export",
        write_files={**_BASE, f"{_D}/specs/billing/spec.md": delta},
        commit_message="docs(plan): add-invoice-export",
    )


def broken(workdir: Path) -> Outcome:
    # Restates the whole spec instead of writing a delta.
    full = "## Requirements\n\n### Requirement: Invoice total\nSHALL sum.\n"
    return Outcome(
        new_branch="openspec/add-invoice-export",
        write_files={**_BASE, f"{_D}/specs/billing/spec.md": full},
        commit_message="docs(plan): add-invoice-export",
    )

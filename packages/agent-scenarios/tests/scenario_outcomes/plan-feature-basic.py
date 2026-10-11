"""Outcomes for plan-feature-basic."""

from __future__ import annotations

from pathlib import Path

from agent_scenarios import Outcome

BROKEN_GATE = "proposal-exists"
_D = "openspec/changes/add-health-check-endpoint"


def golden(workdir: Path) -> Outcome:
    return Outcome(
        new_branch="openspec/add-health-check-endpoint",
        write_files={
            f"{_D}/proposal.md": "# Change: add-health-check-endpoint\n\nAdd a health check.\n",
            f"{_D}/tasks.md": "# Tasks\n- [ ] 1.1 Add /health\n",
        },
        commit_message="docs(plan): add-health-check-endpoint proposal",
    )


def broken(workdir: Path) -> Outcome:
    # Wrong place: nothing scaffolded under the change directory.
    return Outcome(
        new_branch="openspec/add-health-check-endpoint",
        write_files={"NOTES.md": "plan: add health\n"},
        commit_message="docs: notes",
    )

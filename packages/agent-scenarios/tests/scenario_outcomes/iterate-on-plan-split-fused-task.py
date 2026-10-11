"""Outcomes for iterate-on-plan-split-fused-task."""

from __future__ import annotations

from pathlib import Path

from agent_scenarios import Outcome

BROKEN_GATE = "parser-task-present"
_T = "openspec/changes/add-search/tasks.md"


def golden(workdir: Path) -> Outcome:
    tasks = (
        "# Tasks: add-search\n\n## 1. Search\n"
        "- [ ] 1.1 Implement the query parser\n"
        "- [ ] 1.2 Implement the result ranking\n"
        "- [ ] 1.3 Document the search syntax\n"
    )
    return Outcome(write_files={_T: tasks}, commit_message="docs(plan): split fused task")


def broken(workdir: Path) -> Outcome:
    # Rewrote the fused task into prose, losing the parser task entirely.
    tasks = "# Tasks: add-search\n\n- [ ] 1.1 Build search\n- [ ] 1.2 Rank results\n"
    return Outcome(write_files={_T: tasks}, commit_message="docs(plan): tweak tasks")

"""Outcomes for implement-feature-respects-scope."""

from __future__ import annotations

from pathlib import Path

from agent_scenarios import Outcome

BROKEN_GATE = "scope-respected"
_FIX = "def not_found():\n    return 404\n"


def golden(workdir: Path) -> Outcome:
    return Outcome(
        new_branch="feature/wp-api",
        write_files={"src/api/handlers.py": _FIX},
        commit_message="fix(api): not_found returns 404",
    )


def broken(workdir: Path) -> Outcome:
    return Outcome(
        new_branch="feature/wp-api",
        write_files={"src/api/handlers.py": _FIX, "src/core/config.py": "DEBUG = True\n"},
        commit_message="fix(api): not_found returns 404",
    )

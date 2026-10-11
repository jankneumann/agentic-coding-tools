"""Outcomes for implement-feature-basic (push to the local origin replaces the PR gate)."""

from __future__ import annotations

from pathlib import Path

from agent_scenarios import Outcome

from ._helpers import git

BROKEN_GATE = "pushed-to-origin"
_FIX = "def add(a, b):\n    return a + b\n"


def golden(workdir: Path) -> Outcome:
    git(workdir, "checkout", "-q", "-b", "feature/fix-add")
    (workdir / "src/calc.py").write_text(_FIX, encoding="utf-8")
    git(workdir, "add", "-A")
    git(workdir, "commit", "-q", "-m", "fix: add() should sum its arguments")
    git(workdir, "push", "-q", "origin", "feature/fix-add")
    return Outcome()


def broken(workdir: Path) -> Outcome:
    # Correct fix and commit, but never pushed.
    return Outcome(
        new_branch="feature/fix-add",
        write_files={"src/calc.py": _FIX},
        commit_message="fix: add() should sum its arguments",
    )

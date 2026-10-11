"""Outcomes for merge-pull-requests-local-merge."""

from __future__ import annotations

from pathlib import Path

from agent_scenarios import Outcome

from ._helpers import git

BROKEN_GATE = "pr-content-on-origin-main"


def golden(workdir: Path) -> Outcome:
    git(workdir, "checkout", "-q", "main")
    git(workdir, "merge", "--no-ff", "-q", "-m", "Merge pull request #5", "feature/add-greeting")
    git(workdir, "push", "-q", "origin", "main")
    return Outcome()


def broken(workdir: Path) -> Outcome:
    # Reviewed but never merged.
    return Outcome()

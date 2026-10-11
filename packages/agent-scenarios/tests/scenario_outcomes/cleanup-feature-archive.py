"""Outcomes for cleanup-feature-archive."""

from __future__ import annotations

from pathlib import Path

from agent_scenarios import Outcome

from ._helpers import git

BROKEN_GATE = "change-archived-on-origin"


def _merge(workdir: Path) -> None:
    git(workdir, "checkout", "-q", "main")
    git(workdir, "merge", "--no-ff", "-q", "-m", "Merge pull request #3", "openspec/add-greeting")


def golden(workdir: Path) -> Outcome:
    _merge(workdir)
    (workdir / "openspec/changes/archive").mkdir(parents=True, exist_ok=True)
    archived = "openspec/changes/archive/2026-10-11-add-greeting"
    git(workdir, "mv", "openspec/changes/add-greeting", archived)
    git(workdir, "commit", "-q", "-m", "chore(openspec): archive add-greeting")
    git(workdir, "push", "-q", "origin", "main")
    git(workdir, "branch", "-q", "-d", "openspec/add-greeting")
    git(workdir, "push", "-q", "origin", "--delete", "openspec/add-greeting")
    return Outcome()


def broken(workdir: Path) -> Outcome:
    # Merged and pushed, but the change was never archived and branches were left.
    _merge(workdir)
    git(workdir, "push", "-q", "origin", "main")
    return Outcome()

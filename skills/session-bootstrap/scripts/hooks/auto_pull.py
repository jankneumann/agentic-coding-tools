#!/usr/bin/env python3
"""Opt-in SessionStart auto-pull helper.

Runs `git pull --rebase --autostash` on the current branch when
AGENTIC_AUTO_PULL=1 is set. No-ops otherwise.

Behavior:
  - Unset / != "1":      exit 0 immediately, no git invocation
  - Tree dirty:          skip pull, log reason, exit 0
  - Network failure:     log, exit 0 (never block session start)
  - Pull succeeded:      exit 0
  - Not in a git repo:   exit 0 (we can't and shouldn't manage non-git dirs)

Wired from:
  - .claude/settings.json SessionStart hooks block (Claude Code)
  - skills/session-bootstrap/scripts/bootstrap-cloud.sh (Codex Maintenance Script)

Both wiring points invoke this single helper so the env-var gate is
consistent across runtimes.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PREFIX = "[auto_pull]"
PULL_TIMEOUT_SECONDS = 20


def _log(msg: str) -> None:
    print(f"{PREFIX} {msg}", file=sys.stderr)


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, check=False,
        timeout=PULL_TIMEOUT_SECONDS,
    )


def _is_git_repo(cwd: Path) -> bool:
    try:
        r = _run(["git", "rev-parse", "--is-inside-work-tree"], cwd)
        return r.returncode == 0 and r.stdout.strip() == "true"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _is_dirty(cwd: Path) -> bool:
    r = _run(["git", "status", "--porcelain"], cwd)
    if r.returncode != 0:
        return True
    return bool(r.stdout.strip())


def _current_branch(cwd: Path) -> str | None:
    r = _run(["git", "branch", "--show-current"], cwd)
    if r.returncode != 0:
        return None
    branch = r.stdout.strip()
    return branch or None


def auto_pull(cwd: Path, env: dict[str, str]) -> int:
    """Return exit code. Always 0 unless a programming error occurs."""
    if env.get("AGENTIC_AUTO_PULL") != "1":
        return 0

    if not _is_git_repo(cwd):
        _log("not in a git repository, skipping")
        return 0

    if _is_dirty(cwd):
        _log("working tree has uncommitted changes, skipping pull")
        return 0

    branch = _current_branch(cwd)
    if branch is None:
        _log("detached HEAD or no branch, skipping")
        return 0

    _log(f"pulling origin/{branch} with rebase+autostash")
    try:
        r = _run(["git", "pull", "--rebase", "--autostash", "origin", branch], cwd)
        if r.returncode == 0:
            _log("pull succeeded")
        else:
            _log(f"pull failed ({r.returncode}): {r.stderr.strip()}")
    except subprocess.TimeoutExpired:
        _log(f"pull timed out after {PULL_TIMEOUT_SECONDS}s, continuing session")

    # Always exit 0 — auto-pull is advisory; never block session start.
    return 0


def main() -> int:
    cwd = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd()))
    return auto_pull(cwd, dict(os.environ))


if __name__ == "__main__":
    sys.exit(main())

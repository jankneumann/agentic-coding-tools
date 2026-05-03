"""Shared fixtures for the prototype-prefix worktree tests.

We import the canonical ``worktree`` module from ``skills/worktree/scripts/``
by injecting that path into ``sys.path``. The existing in-tree test suite
(`skills/worktree/scripts/tests/test_worktree.py`) does the same — these
new tests live outside the skill tree per the project convention that
runtime mirrors should not ship test code.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# Inject canonical worktree script onto sys.path. Going up four levels:
# this file → tests/worktree/ → tests/ → skills/, then into worktree/scripts/.
SKILL_SCRIPTS = Path(__file__).resolve().parents[2] / "worktree" / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo for testing.

    Mirrors the fixture used by the in-tree worktree tests so behavior is
    identical. Repo-local config only — never touches the user's global
    git config — and disables commit signing for sandboxed CI.
    """
    subprocess.run(
        ["git", "init", str(tmp_path)], check=True, capture_output=True
    )
    for key, value in [
        ("user.email", "test@test.com"),
        ("user.name", "Test"),
        ("commit.gpgsign", "false"),
        ("tag.gpgsign", "false"),
    ]:
        subprocess.run(
            ["git", "config", key, value],
            cwd=str(tmp_path),
            check=True,
            capture_output=True,
        )
    (tmp_path / "README.md").write_text("test")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "--no-gpg-sign", "-m", "init"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "branch", "-M", "main"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    return tmp_path

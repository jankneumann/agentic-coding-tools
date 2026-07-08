"""Shared fixtures for agent-scenarios tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCENARIOS_DIR = Path(__file__).resolve().parents[1] / "scenarios"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, check=True)


@pytest.fixture
def git_workspace(tmp_path: Path) -> Path:
    """A minimal initialized git repo with one fixture commit on ``main``."""
    root = tmp_path / "ws"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("def handler():\n    return 'ok'\n", encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t.local")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture: initial state")
    return root


@pytest.fixture
def scenarios_dir() -> Path:
    return SCENARIOS_DIR

"""Tests for skills/session-bootstrap/scripts/hooks/auto_pull.py.

Spec scenarios:
- skill-runtime-sync.d (auto-pull clean)
- skill-runtime-sync.e (auto-pull dirty)
- skill-runtime-sync.f (auto-pull disabled)
- skill-runtime-sync.i (both runtimes wired)
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "skills" / "session-bootstrap" / "scripts" / "hooks" / "auto_pull.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("auto_pull", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auto_pull = _load_module()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Clean git repo with an origin."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(repo)], check=True, capture_output=True
    )
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "tag.gpgsign", "false")
    _git(repo, "config", "gpg.format", "openpgp")
    _git(repo, "remote", "add", "origin", str(origin))
    (repo / "readme.md").write_text("initial\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "push", "-u", "origin", "main")
    return repo


def test_disabled_is_noop(repo: Path) -> None:
    """Env unset or !=1 -> exit 0 without invoking git."""
    assert auto_pull.auto_pull(repo, env={}) == 0
    assert auto_pull.auto_pull(repo, env={"AGENTIC_AUTO_PULL": "0"}) == 0
    assert auto_pull.auto_pull(repo, env={"AGENTIC_AUTO_PULL": "yes"}) == 0


def test_clean_tree_pulls_successfully(repo: Path) -> None:
    """Env=1 + clean tree + reachable origin -> exit 0 after successful pull."""
    rc = auto_pull.auto_pull(repo, env={"AGENTIC_AUTO_PULL": "1"})
    assert rc == 0


def test_dirty_tree_skips_pull(repo: Path, capsys) -> None:
    """Env=1 + dirty tree -> skip pull, log skip reason, exit 0."""
    (repo / "new.md").write_text("uncommitted\n")
    rc = auto_pull.auto_pull(repo, env={"AGENTIC_AUTO_PULL": "1"})
    assert rc == 0
    captured = capsys.readouterr()
    assert "uncommitted" in captured.err.lower() or "skipping" in captured.err.lower()


def test_network_failure_exits_zero(repo: Path, capsys) -> None:
    """Env=1 + unreachable origin -> pull fails internally, still exit 0."""
    _git(repo, "remote", "set-url", "origin", "file:///does/not/exist.git")
    rc = auto_pull.auto_pull(repo, env={"AGENTIC_AUTO_PULL": "1"})
    assert rc == 0  # Always advisory; never blocks session start


def test_not_a_git_repo_exits_zero(tmp_path: Path, capsys) -> None:
    """Not a git repo + env=1 -> exit 0, skip silently."""
    rc = auto_pull.auto_pull(tmp_path, env={"AGENTIC_AUTO_PULL": "1"})
    assert rc == 0


def test_both_runtimes_wired() -> None:
    """Spec scenario skill-runtime-sync.i: auto_pull.py is invoked from both
    .claude/settings.json SessionStart block AND
    skills/session-bootstrap/scripts/bootstrap-cloud.sh."""
    # Claude Code wiring
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
    session_start_hooks = settings.get("hooks", {}).get("SessionStart", [])
    found_claude = False
    for block in session_start_hooks:
        for hook in block.get("hooks", []):
            if "auto_pull.py" in hook.get("command", ""):
                found_claude = True
    assert found_claude, "auto_pull.py not wired in .claude/settings.json SessionStart block"

    # Codex wiring
    bootstrap = (ROOT / "skills" / "session-bootstrap" / "scripts" / "bootstrap-cloud.sh").read_text()
    assert "auto_pull.py" in bootstrap, "auto_pull.py not invoked from bootstrap-cloud.sh"

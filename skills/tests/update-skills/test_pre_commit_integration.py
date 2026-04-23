"""Integration test: simulate a pre-commit context and verify the hook rejects drift.

We don't require pre-commit itself to be installed in the test env — we invoke
the hook's entry command directly (matches what the pre-commit framework runs).

Spec scenarios:
- skill-runtime-sync.4 (drift rejection)
- skill-runtime-sync.5 (in-sync pass)
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "update-skills" / "scripts" / "sync_agents_md.py"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "CLAUDE.md").write_text("# CLAUDE\nproject context\n")
    return tmp_path


def _run_hook(repo_path: Path) -> subprocess.CompletedProcess[str]:
    """Simulate what pre-commit framework invokes: the hook's entry command."""
    return subprocess.run(
        ["python3", str(SCRIPT), "--check"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )


def test_drift_rejects_commit(repo: Path) -> None:
    (repo / "AGENTS.md").write_text("stale content\n")
    result = _run_hook(repo)
    assert result.returncode != 0
    assert "CLAUDE.md" in result.stderr or "AGENTS.md" in result.stderr
    assert "sync_agents_md.py" in result.stderr or "update-skills" in result.stderr


def test_in_sync_passes_commit(repo: Path) -> None:
    (repo / "AGENTS.md").write_bytes((repo / "CLAUDE.md").read_bytes())
    result = _run_hook(repo)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_pre_commit_config_exists_and_parses() -> None:
    """Sanity: .pre-commit-config.yaml at repo root is valid YAML and declares our hook."""
    import yaml

    repo_root = Path(__file__).resolve().parents[3]
    cfg = yaml.safe_load((repo_root / ".pre-commit-config.yaml").read_text())
    assert "repos" in cfg
    hook_ids = {h["id"] for repo in cfg["repos"] for h in repo.get("hooks", [])}
    assert "agents-md-sync" in hook_ids


def test_install_hooks_script_is_executable() -> None:
    """Sanity: install-hooks.sh at repo root has a shebang and is executable."""
    import os
    import stat

    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "install-hooks.sh"
    assert script.exists()
    mode = script.stat().st_mode
    assert bool(mode & stat.S_IXUSR), f"install-hooks.sh must be executable: mode={oct(mode)}"
    assert script.read_text().startswith("#!/")

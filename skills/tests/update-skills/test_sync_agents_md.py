"""Tests for skills/update-skills/scripts/sync_agents_md.py.

Spec scenarios:
- skill-runtime-sync.5 (sync script as standalone tool):
    regenerate, check drift, check in-sync, missing source
- skill-runtime-sync.3 (AGENTS.md byte-identity, pre-commit behavior):
    pre-commit drift rejection, pre-commit in-sync passes
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "update-skills" / "scripts" / "sync_agents_md.py"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A tmp "repo root" with CLAUDE.md present."""
    (tmp_path / "CLAUDE.md").write_text("# CLAUDE\nproject context\n")
    return tmp_path


def test_regenerate_copies_content(repo: Path) -> None:
    """Default invocation copies CLAUDE.md -> AGENTS.md byte-for-byte."""
    result = _run([], cwd=repo)
    assert result.returncode == 0, result.stderr
    assert (repo / "AGENTS.md").read_bytes() == (repo / "CLAUDE.md").read_bytes()


def test_regenerate_overwrites_existing_agents_md(repo: Path) -> None:
    (repo / "AGENTS.md").write_text("stale content")
    result = _run([], cwd=repo)
    assert result.returncode == 0
    assert (repo / "AGENTS.md").read_text() == (repo / "CLAUDE.md").read_text()


def test_check_reports_in_sync(repo: Path) -> None:
    (repo / "AGENTS.md").write_bytes((repo / "CLAUDE.md").read_bytes())
    result = _run(["--check"], cwd=repo)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_check_reports_drift(repo: Path) -> None:
    (repo / "AGENTS.md").write_text("# CLAUDE\nstale content\n")
    result = _run(["--check"], cwd=repo)
    assert result.returncode == 2
    assert "---" in result.stderr or "+++" in result.stderr or "@@" in result.stderr


def test_check_missing_agents_md_is_drift(repo: Path) -> None:
    """If AGENTS.md doesn't exist at all, --check treats it as drift (exit 2)."""
    assert not (repo / "AGENTS.md").exists()
    result = _run(["--check"], cwd=repo)
    assert result.returncode == 2


def test_missing_source(tmp_path: Path) -> None:
    """CLAUDE.md missing -> exit 1, error names the path."""
    result = _run([], cwd=tmp_path)
    assert result.returncode == 1
    assert "CLAUDE.md" in result.stderr


def test_missing_source_check_mode(tmp_path: Path) -> None:
    """Same in --check mode."""
    result = _run(["--check"], cwd=tmp_path)
    assert result.returncode == 1
    assert "CLAUDE.md" in result.stderr


def test_pre_commit_drift_rejection_message(repo: Path) -> None:
    """Drift diagnostic includes remediation hint."""
    (repo / "AGENTS.md").write_text("drifted\n")
    result = _run(["--check"], cwd=repo)
    assert result.returncode == 2
    assert "sync_agents_md.py" in result.stderr or "update-skills" in result.stderr

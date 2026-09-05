"""Unit tests for simplify/scripts/verify_behavior_preservation.py."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "simplify-implementation" / "scripts"


def _load():
    import sys

    path = SCRIPTS / "verify_behavior_preservation.py"
    name = "simplify_implementation_verify_behavior_preservation"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "ok.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (repo / "ok.sh").chmod(0o755)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


def test_dual_run_both_pass(git_repo: Path, tmp_path: Path):
    mod = _load()
    base = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, text=True
    ).strip()
    (git_repo / "note.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "second"],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )
    report_path = tmp_path / "report.json"
    code = mod.main(
        [
            "--baseline",
            base,
            "--repo",
            str(git_repo),
            "--test-cmd",
            "true",
            "--report",
            str(report_path),
        ]
    )
    assert code == 0
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["both_passed"] is True
    assert data["baseline_run"]["passed"] is True
    assert data["head_run"]["passed"] is True


def test_head_fail_exits_two(git_repo: Path, tmp_path: Path):
    mod = _load()
    base = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, text=True
    ).strip()
    report_path = tmp_path / "report.json"
    code = mod.main(
        [
            "--baseline",
            base,
            "--repo",
            str(git_repo),
            "--test-cmd",
            "false",
            "--report",
            str(report_path),
            "--skip-baseline-run",
        ]
    )
    assert code == 2
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["both_passed"] is False
    assert data["head_run"]["passed"] is False

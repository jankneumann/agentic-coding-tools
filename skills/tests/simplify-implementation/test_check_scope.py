"""Unit tests for simplify/scripts/check_scope.py."""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "simplify-implementation" / "scripts"


def _load():
    import sys

    path = SCRIPTS / "check_scope.py"
    name = "simplify_implementation_check_scope"
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
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


def _commit(repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def test_within_limit_exits_zero(git_repo: Path):
    mod = _load()
    base = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, text=True
    ).strip()
    (git_repo / "a.py").write_text("x = 2\n", encoding="utf-8")
    _commit(git_repo, "small change")
    assert mod.main(["--base", base, "--repo", str(git_repo)]) == 0


def test_over_file_limit_exits_two(git_repo: Path):
    mod = _load()
    base = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, text=True
    ).strip()
    for i in range(6):
        (git_repo / f"f{i}.py").write_text(f"v = {i}\n", encoding="utf-8")
    _commit(git_repo, "six files")
    assert (
        mod.main(
            [
                "--base",
                base,
                "--repo",
                str(git_repo),
                "--max-files",
                "5",
                "--max-lines",
                "500",
            ]
        )
        == 2
    )


def test_allow_codemod_permits_oversize(git_repo: Path):
    mod = _load()
    base = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, text=True
    ).strip()
    for i in range(6):
        (git_repo / f"f{i}.py").write_text(f"v = {i}\n", encoding="utf-8")
    _commit(git_repo, "six files")
    assert (
        mod.main(
            [
                "--base",
                base,
                "--repo",
                str(git_repo),
                "--allow-codemod",
                "--max-files",
                "5",
            ]
        )
        == 0
    )


def test_over_line_limit(git_repo: Path):
    mod = _load()
    base = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, text=True
    ).strip()
    (git_repo / "big.py").write_text("\n".join(f"line_{i} = {i}" for i in range(40)) + "\n", encoding="utf-8")
    _commit(git_repo, "many lines")
    assert (
        mod.main(
            [
                "--base",
                base,
                "--repo",
                str(git_repo),
                "--max-lines",
                "10",
                "--max-files",
                "50",
            ]
        )
        == 2
    )


def test_uncommitted_churn_is_measured(git_repo: Path):
    """Dirty working tree must not report a silent 0-file pass for large edits."""
    mod = _load()
    base = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, text=True
    ).strip()
    for i in range(6):
        (git_repo / f"u{i}.py").write_text(f"v = {i}\n", encoding="utf-8")
    # uncommitted
    code = mod.main(
        [
            "--base",
            base,
            "--repo",
            str(git_repo),
            "--max-files",
            "5",
            "--max-lines",
            "500",
        ]
    )
    assert code == 2

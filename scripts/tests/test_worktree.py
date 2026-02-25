"""Tests for scripts/worktree.py."""

import argparse
import os
import subprocess
from pathlib import Path

import pytest

# Import the module under test
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import worktree


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo for testing."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    # Create initial commit so we have a main branch
    (tmp_path / "README.md").write_text("test")
    subprocess.run(
        ["git", "add", "README.md"], cwd=str(tmp_path), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    # Ensure we're on main
    subprocess.run(
        ["git", "branch", "-M", "main"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    return tmp_path


class TestResolveMainRepo:
    def test_from_main_repo(self, git_repo: Path) -> None:
        result = worktree.resolve_main_repo(str(git_repo))
        assert result == git_repo

    def test_from_worktree(self, git_repo: Path) -> None:
        wt_path = git_repo / ".git-worktrees" / "test-wt"
        wt_path.parent.mkdir(parents=True)
        subprocess.run(
            ["git", "branch", "test-branch", "main"],
            cwd=str(git_repo),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "worktree", "add", str(wt_path), "test-branch"],
            cwd=str(git_repo),
            check=True,
            capture_output=True,
        )
        result = worktree.resolve_main_repo(str(wt_path))
        assert result == git_repo


class TestWorktreePath:
    def test_without_prefix(self, tmp_path: Path) -> None:
        result = worktree.worktree_path(tmp_path, "my-feature")
        assert result == tmp_path / ".git-worktrees" / "my-feature"

    def test_with_prefix(self, tmp_path: Path) -> None:
        result = worktree.worktree_path(tmp_path, "2026-02-24", prefix="fix-scrub")
        assert result == tmp_path / ".git-worktrees" / "fix-scrub" / "2026-02-24"


class TestLegacyWorktreePath:
    def test_without_prefix(self, tmp_path: Path) -> None:
        repo = tmp_path / "my-repo"
        repo.mkdir()
        result = worktree.legacy_worktree_path(repo, "my-feature")
        assert result == tmp_path / "my-repo.worktrees" / "my-feature"

    def test_with_prefix(self, tmp_path: Path) -> None:
        repo = tmp_path / "my-repo"
        repo.mkdir()
        result = worktree.legacy_worktree_path(repo, "2026-02-24", prefix="fix-scrub")
        assert result == tmp_path / "my-repo.worktrees" / "fix-scrub" / "2026-02-24"


class TestCmdSetup:
    def test_creates_worktree(self, git_repo: Path) -> None:
        args = _make_args("setup", change_id="test-feature")
        with _chdir(git_repo):
            result = worktree.cmd_setup(args)
        assert result == 0
        wt_path = git_repo / ".git-worktrees" / "test-feature"
        assert wt_path.is_dir()
        # Check branch was created
        branches = subprocess.run(
            ["git", "branch", "--list", "openspec/test-feature"],
            cwd=str(git_repo),
            capture_output=True,
            text=True,
        )
        assert "openspec/test-feature" in branches.stdout

    def test_creates_worktree_with_prefix(self, git_repo: Path) -> None:
        args = _make_args(
            "setup", change_id="2026-02-24", prefix="fix-scrub", branch="fix-scrub/2026-02-24"
        )
        with _chdir(git_repo):
            result = worktree.cmd_setup(args)
        assert result == 0
        wt_path = git_repo / ".git-worktrees" / "fix-scrub" / "2026-02-24"
        assert wt_path.is_dir()

    def test_idempotent_rerun(self, git_repo: Path) -> None:
        args = _make_args("setup", change_id="test-feature")
        with _chdir(git_repo):
            worktree.cmd_setup(args)
            # Second run should not fail
            result = worktree.cmd_setup(args)
        assert result == 0

    def test_custom_branch(self, git_repo: Path) -> None:
        args = _make_args("setup", change_id="test-feature", branch="custom/branch")
        with _chdir(git_repo):
            result = worktree.cmd_setup(args)
        assert result == 0
        branches = subprocess.run(
            ["git", "branch", "--list", "custom/branch"],
            cwd=str(git_repo),
            capture_output=True,
            text=True,
        )
        assert "custom/branch" in branches.stdout

    def test_output_contains_worktree_path(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        args = _make_args("setup", change_id="test-feature")
        with _chdir(git_repo):
            worktree.cmd_setup(args)
        captured = capsys.readouterr()
        expected = str(git_repo / ".git-worktrees" / "test-feature")
        assert f"WORKTREE_PATH={expected}" in captured.out


class TestCmdTeardown:
    def test_removes_worktree(self, git_repo: Path) -> None:
        # Setup first
        setup_args = _make_args("setup", change_id="test-feature")
        with _chdir(git_repo):
            worktree.cmd_setup(setup_args)
        wt_path = git_repo / ".git-worktrees" / "test-feature"
        assert wt_path.is_dir()

        # Teardown
        teardown_args = _make_args("teardown", change_id="test-feature")
        with _chdir(git_repo):
            result = worktree.cmd_teardown(teardown_args)
        assert result == 0
        assert not wt_path.is_dir()

    def test_removes_legacy_worktree(self, git_repo: Path) -> None:
        # Create a worktree at the legacy location
        legacy_path = git_repo.parent / f"{git_repo.name}.worktrees" / "test-feature"
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "branch", "openspec/test-feature", "main"],
            cwd=str(git_repo),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "worktree", "add", str(legacy_path), "openspec/test-feature"],
            cwd=str(git_repo),
            check=True,
            capture_output=True,
        )
        assert legacy_path.is_dir()

        # Teardown should find it at legacy location
        teardown_args = _make_args("teardown", change_id="test-feature")
        with _chdir(git_repo):
            result = worktree.cmd_teardown(teardown_args)
        assert result == 0
        assert not legacy_path.is_dir()

    def test_not_found_returns_error(self, git_repo: Path) -> None:
        teardown_args = _make_args("teardown", change_id="nonexistent")
        with _chdir(git_repo):
            result = worktree.cmd_teardown(teardown_args)
        assert result == 1


class TestCmdStatus:
    def test_specific_worktree_exists(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        setup_args = _make_args("setup", change_id="test-feature")
        with _chdir(git_repo):
            worktree.cmd_setup(setup_args)

        status_args = _make_args("status", change_id="test-feature")
        with _chdir(git_repo):
            result = worktree.cmd_status(status_args)
        assert result == 0
        captured = capsys.readouterr()
        assert "EXISTS=true" in captured.out
        assert "LOCATION=new" in captured.out

    def test_specific_worktree_not_found(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        status_args = _make_args("status", change_id="nonexistent")
        with _chdir(git_repo):
            result = worktree.cmd_status(status_args)
        assert result == 1
        captured = capsys.readouterr()
        assert "EXISTS=false" in captured.out

    def test_list_all(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        status_args = _make_args("status", change_id=None)
        with _chdir(git_repo):
            result = worktree.cmd_status(status_args)
        assert result == 0
        captured = capsys.readouterr()
        assert str(git_repo) in captured.out


class TestCmdDetect:
    def test_from_main_repo(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        detect_args = _make_args("detect")
        with _chdir(git_repo):
            result = worktree.cmd_detect(detect_args)
        assert result == 0
        captured = capsys.readouterr()
        assert "IN_WORKTREE=false" in captured.out
        assert f"MAIN_REPO={git_repo}" in captured.out
        assert "OPENSPEC_PATH=openspec" in captured.out

    def test_from_worktree(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        setup_args = _make_args("setup", change_id="test-feature")
        with _chdir(git_repo):
            worktree.cmd_setup(setup_args)

        wt_path = git_repo / ".git-worktrees" / "test-feature"
        detect_args = _make_args("detect")
        with _chdir(wt_path):
            capsys.readouterr()  # Clear previous output
            result = worktree.cmd_detect(detect_args)
        assert result == 0
        captured = capsys.readouterr()
        assert "IN_WORKTREE=true" in captured.out
        assert f"MAIN_REPO={git_repo}" in captured.out
        assert f"OPENSPEC_PATH={git_repo}/openspec" in captured.out


# --- Helpers ---

class _chdir:
    """Context manager to temporarily change directory."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.prev: str | None = None

    def __enter__(self) -> None:
        self.prev = os.getcwd()
        os.chdir(self.path)

    def __exit__(self, *args: object) -> None:
        if self.prev:
            os.chdir(self.prev)


def _make_args(command: str, **kwargs: object) -> argparse.Namespace:
    """Create a mock argparse.Namespace for testing."""
    defaults = {
        "command": command,
        "change_id": None,
        "branch": None,
        "prefix": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)

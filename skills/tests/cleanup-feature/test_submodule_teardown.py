"""Tests for worktree teardown with submodules (Issue 1).

Reproduces the failure where ``git worktree remove`` refuses to remove
worktrees containing initialized submodule checkouts, and verifies the
fix: deinit first, then fall back to --force for the specific submodule
error only.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worktree" / "scripts"))
import worktree
from worktree import (
    _SUBMODULE_REMOVE_ERROR,
    _deinit_submodules,
    cmd_teardown,
    load_registry,
    save_registry,
    worktree_path,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
    )


def _init_repo(path: Path) -> Path:
    """Create a minimal git repo with user config and initial commit."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    for key, value in [
        ("user.email", "test@test.com"),
        ("user.name", "Test"),
        ("commit.gpgsign", "false"),
        ("tag.gpgsign", "false"),
        ("protocol.file.allow", "always"),
    ]:
        _git(["config", key, value], str(path))
    (path / "README.md").write_text("test")
    _git(["add", "README.md"], str(path))
    _git(["commit", "--no-gpg-sign", "-m", "init"], str(path))
    _git(["branch", "-M", "main"], str(path))
    return path


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal main git repo."""
    return _init_repo(tmp_path / "main-repo")


def _make_args(change_id: str, agent_id: str | None = None, prefix: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        change_id=change_id,
        agent_id=agent_id,
        prefix=prefix,
    )


def _setup_worktree(main_repo: Path, change_id: str, agent_id: str | None = None) -> Path:
    """Create a worktree and register it."""
    wt = worktree_path(main_repo, change_id, agent_id)
    branch = f"openspec/{change_id}"
    if agent_id:
        branch += f"--{agent_id}"
    _git(["branch", branch, "main"], str(main_repo))
    wt.parent.mkdir(parents=True, exist_ok=True)
    _git(["worktree", "add", str(wt), branch], str(main_repo))

    # Register
    registry = load_registry(main_repo)
    registry["entries"].append({
        "change_id": change_id,
        "agent_id": agent_id,
        "branch": branch,
        "worktree_path": str(wt),
        "created_at": "2026-01-01T00:00:00+00:00",
        "last_heartbeat": "2026-01-01T00:00:00+00:00",
        "pinned": False,
    })
    save_registry(main_repo, registry)
    return wt


# ---------------------------------------------------------------------------
# Tests: basic teardown (no submodules — regression check)
# ---------------------------------------------------------------------------

class TestTeardownNoSubmodules:
    """Verify normal teardown still works identically without submodules."""

    def test_teardown_removes_worktree(self, git_repo: Path) -> None:
        wt = _setup_worktree(git_repo, "no-sub-test")
        assert wt.is_dir()

        with patch.object(worktree, "resolve_main_repo", return_value=git_repo):
            result = cmd_teardown(_make_args("no-sub-test"))

        assert result == 0
        assert not wt.is_dir()

    def test_teardown_updates_registry(self, git_repo: Path) -> None:
        _setup_worktree(git_repo, "reg-test")

        with patch.object(worktree, "resolve_main_repo", return_value=git_repo):
            cmd_teardown(_make_args("reg-test"))

        registry = load_registry(git_repo)
        assert not any(e["change_id"] == "reg-test" for e in registry["entries"])

    def test_teardown_nonexistent_returns_1(self, git_repo: Path) -> None:
        with patch.object(worktree, "resolve_main_repo", return_value=git_repo):
            result = cmd_teardown(_make_args("ghost"))

        assert result == 1


# ---------------------------------------------------------------------------
# Tests: teardown with submodules
# ---------------------------------------------------------------------------

class TestTeardownWithSubmodules:
    """Test the submodule-aware teardown logic."""

    def _add_submodule_to_worktree(self, main_repo: Path, wt: Path) -> Path:
        """Add and initialize a submodule inside the worktree."""
        # Create a separate repo to be the submodule
        sub_origin = main_repo.parent / "sub-origin"
        _init_repo(sub_origin)

        # Add submodule inside the worktree (use -c for protocol in worktree context)
        _git(
            ["-c", "protocol.file.allow=always",
             "submodule", "add", str(sub_origin), "my-sub"],
            str(wt),
        )
        _git(["add", "."], str(wt))
        _git(["commit", "--no-gpg-sign", "-m", "add submodule"], str(wt))
        return wt / "my-sub"

    def test_deinit_submodules_succeeds(self, git_repo: Path) -> None:
        """Verify _deinit_submodules runs without error on a worktree with submodules."""
        wt = _setup_worktree(git_repo, "deinit-test")
        self._add_submodule_to_worktree(git_repo, wt)

        # Should not raise
        _deinit_submodules(wt)

        # Submodule dir should be empty after deinit
        sub_dir = wt / "my-sub"
        # After deinit, the directory exists but content is removed
        if sub_dir.is_dir():
            contents = list(sub_dir.iterdir())
            assert len(contents) == 0

    def test_deinit_submodules_no_submodules(self, git_repo: Path) -> None:
        """Verify _deinit_submodules silently passes when no submodules exist."""
        wt = _setup_worktree(git_repo, "no-sub")
        # Should not raise
        _deinit_submodules(wt)

    def test_teardown_with_submodule_succeeds(self, git_repo: Path) -> None:
        """Full teardown of a worktree that has an initialized submodule."""
        wt = _setup_worktree(git_repo, "sub-teardown")
        self._add_submodule_to_worktree(git_repo, wt)
        assert wt.is_dir()

        with patch.object(worktree, "resolve_main_repo", return_value=git_repo):
            result = cmd_teardown(_make_args("sub-teardown"))

        assert result == 0
        assert not wt.is_dir()

    def test_force_fallback_only_for_submodule_error(self, git_repo: Path) -> None:
        """Verify --force is used only for the submodule-specific error, not others."""
        wt = _setup_worktree(git_repo, "force-test")

        # Simulate a non-submodule error (e.g., dirty tree)
        other_error = subprocess.CalledProcessError(
            128, ["git", "worktree", "remove"],
            "", "fatal: some other error",
        )

        with patch.object(worktree, "resolve_main_repo", return_value=git_repo), \
             patch.object(worktree, "run_git") as mock_git:
            # _deinit_submodules call succeeds (no-op)
            # First run_git call in teardown (the remove) raises non-submodule error
            mock_git.side_effect = [
                None,  # _deinit_submodules: submodule deinit (no-op / passes)
                other_error,  # git worktree remove (non-submodule error)
            ]
            with pytest.raises(subprocess.CalledProcessError) as exc_info:
                cmd_teardown(_make_args("force-test"))

            assert "some other error" in (exc_info.value.stderr or "")

    def test_force_fallback_for_submodule_error(self, git_repo: Path) -> None:
        """Verify --force IS used when the error is the submodule one."""
        wt = _setup_worktree(git_repo, "force-sub")

        submodule_error = subprocess.CalledProcessError(
            128, ["git", "worktree", "remove"],
            "", f"fatal: {_SUBMODULE_REMOVE_ERROR}",
        )

        call_log: list[tuple[str, ...]] = []

        def tracking_run_git(*args: str, cwd: str | None = None, check: bool = True) -> str:
            call_log.append(args)
            if args[:2] == ("worktree", "remove") and "--force" not in args:
                raise submodule_error
            if args[:2] == ("worktree", "remove") and "--force" in args:
                # Simulate successful forced removal
                import shutil
                if wt.is_dir():
                    shutil.rmtree(wt)
                # Also prune the worktree from git's tracking
                subprocess.run(
                    ["git", "worktree", "prune"],
                    cwd=str(git_repo), check=False, capture_output=True,
                )
                return ""
            if args[:2] == ("submodule", "deinit"):
                return ""
            return ""

        with patch.object(worktree, "resolve_main_repo", return_value=git_repo), \
             patch.object(worktree, "run_git", side_effect=tracking_run_git):
            result = cmd_teardown(_make_args("force-sub"))

        assert result == 0
        # Verify --force was used
        force_calls = [c for c in call_log if "worktree" in c and "--force" in c]
        assert len(force_calls) == 1


# ---------------------------------------------------------------------------
# Tests: _SUBMODULE_REMOVE_ERROR constant
# ---------------------------------------------------------------------------

class TestSubmoduleErrorConstant:
    """Verify the error string matches what git actually produces."""

    def test_error_string_is_correct(self) -> None:
        assert "submodules" in _SUBMODULE_REMOVE_ERROR
        assert "moved or removed" in _SUBMODULE_REMOVE_ERROR

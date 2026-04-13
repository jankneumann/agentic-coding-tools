"""Tests for sync_submodules.py (Issue 2: submodule main not fast-forwarded).

Uses real git repos in tmp_path to reproduce the exact failure mode:
parent merges a submodule SHA bump, but the submodule's own main branch
is never fast-forwarded to match.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "cleanup-feature" / "scripts"),
)
from sync_submodules import (
    SubmoduleChange,
    SyncResult,
    detect_changed_submodules,
    detect_submodule_feature_branch,
    sync_submodule,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
    )


def _init_repo(path: Path) -> Path:
    """Create a minimal git repo."""
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


def _sha(cwd: str, ref: str = "HEAD") -> str:
    """Get the SHA of a ref."""
    return _git(["rev-parse", ref], cwd).stdout.strip()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repo_with_submodule(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a parent repo with a submodule, simulating a merge that bumps the submodule SHA.

    Returns (parent_repo, sub_origin, sub_checkout_in_parent).

    State after fixture:
    - sub_origin has main at initial commit
    - parent has main at a commit that records a NEWER submodule SHA
      (from a feature branch commit in the submodule)
    - parent's main@{1} records the OLD submodule SHA
    - The submodule's main has NOT been fast-forwarded (this is the bug)
    """
    # 1. Create the submodule origin repo
    sub_origin = _init_repo(tmp_path / "sub-origin")
    # Allow pushing to this non-bare repo in tests
    _git(["config", "receive.denyCurrentBranch", "ignore"], str(sub_origin))
    initial_sub_sha = _sha(str(sub_origin))

    # 2. Create the parent repo
    parent = _init_repo(tmp_path / "parent")

    # 3. Add submodule to parent
    _git(["-c", "protocol.file.allow=always",
          "submodule", "add", str(sub_origin), "my-sub"], str(parent))
    _git(["add", "."], str(parent))
    _git(["commit", "--no-gpg-sign", "-m", "add submodule"], str(parent))
    sub_in_parent = parent / "my-sub"

    # Record main@{0} = this commit (submodule at initial SHA)
    # We need main@{1} to exist after the next commit

    # 4. Make a change in the submodule (simulating feature work)
    _git(["checkout", "-b", "openspec/test-feature"], str(sub_in_parent))
    (sub_in_parent / "feature.txt").write_text("new feature")
    _git(["add", "feature.txt"], str(sub_in_parent))
    _git(["commit", "--no-gpg-sign", "-m", "feat: add feature"], str(sub_in_parent))
    new_sub_sha = _sha(str(sub_in_parent))

    # Push the feature branch to sub_origin so it has the commit
    _git(["push", "origin", f"openspec/test-feature"], str(sub_in_parent))

    # 5. Bump the submodule SHA in parent (simulating the merge)
    _git(["add", "my-sub"], str(parent))
    _git(["commit", "--no-gpg-sign", "-m", "chore: bump submodule"], str(parent))

    # Now parent main records the new SHA, but sub_origin's main is still at initial_sub_sha
    assert _sha(str(sub_origin), "main") == initial_sub_sha
    assert new_sub_sha != initial_sub_sha

    return parent, sub_origin, sub_in_parent


# ---------------------------------------------------------------------------
# Tests: detect_changed_submodules
# ---------------------------------------------------------------------------

class TestDetectChangedSubmodules:
    def test_detects_bumped_submodule(self, repo_with_submodule: tuple[Path, Path, Path]) -> None:
        parent, sub_origin, sub_in_parent = repo_with_submodule

        changes = detect_changed_submodules(str(parent))
        assert len(changes) == 1
        assert changes[0].path == "my-sub"
        # new_sha should match what parent records
        expected_sha = _git(
            ["ls-tree", "main", "my-sub"], str(parent),
        ).stdout.split()[2]
        assert changes[0].new_sha == expected_sha

    def test_no_changes_returns_empty(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "empty-repo")
        # Create a second commit so main@{1} exists
        (repo / "file.txt").write_text("x")
        _git(["add", "file.txt"], str(repo))
        _git(["commit", "--no-gpg-sign", "-m", "second"], str(repo))

        changes = detect_changed_submodules(str(repo))
        assert changes == []

    def test_reflog_missing_returns_empty(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "no-reflog")
        # Only one commit — main@{1} doesn't exist
        changes = detect_changed_submodules(str(repo))
        assert changes == []


# ---------------------------------------------------------------------------
# Tests: sync_submodule
# ---------------------------------------------------------------------------

class TestSyncSubmodule:
    def test_full_sync_success(self, repo_with_submodule: tuple[Path, Path, Path]) -> None:
        parent, sub_origin, sub_in_parent = repo_with_submodule

        # Get the SHA parent records
        target_sha = _git(
            ["ls-tree", "main", "my-sub"], str(parent),
        ).stdout.split()[2]

        change = SubmoduleChange(
            path="my-sub",
            new_sha=target_sha,
            remote_url=str(sub_origin),
        )

        result = sync_submodule(change, str(parent), feature_branch="openspec/test-feature")

        assert result.success is True
        assert result.ff_done is True
        assert result.pushed is True

        # Verify sub_origin's main is now at target_sha
        assert _sha(str(sub_origin), "main") == target_sha

    def test_ff_only_no_force_merge(self, repo_with_submodule: tuple[Path, Path, Path]) -> None:
        """If submodule main has diverged, ff-only must fail (not force-merge)."""
        parent, sub_origin, sub_in_parent = repo_with_submodule

        # Make a diverging commit on the submodule's LOCAL main branch
        # (not just origin — the sync script switches to local main then
        # tries to ff-only merge target_sha into it)
        _git(["checkout", "main"], str(sub_in_parent))
        (sub_in_parent / "diverge.txt").write_text("diverge")
        _git(["add", "diverge.txt"], str(sub_in_parent))
        _git(["commit", "--no-gpg-sign", "-m", "diverge on local main"], str(sub_in_parent))
        # Push to origin so fetch brings it back
        _git(["push", "origin", "main"], str(sub_in_parent))
        # Go back to feature branch
        _git(["checkout", "openspec/test-feature"], str(sub_in_parent))

        target_sha = _git(
            ["ls-tree", "main", "my-sub"], str(parent),
        ).stdout.split()[2]

        change = SubmoduleChange(
            path="my-sub",
            new_sha=target_sha,
            remote_url=str(sub_origin),
        )

        result = sync_submodule(change, str(parent))

        assert result.success is False
        assert result.ff_done is False
        assert "fast-forward failed" in result.error
        assert len(result.handoff_commands) > 0

    def test_push_auth_failure_handoff(self, repo_with_submodule: tuple[Path, Path, Path]) -> None:
        """On push failure, should log handoff commands and continue."""
        parent, sub_origin, sub_in_parent = repo_with_submodule

        target_sha = _git(
            ["ls-tree", "main", "my-sub"], str(parent),
        ).stdout.split()[2]

        change = SubmoduleChange(
            path="my-sub",
            new_sha=target_sha,
            remote_url="https://private.example.com/sub.git",
        )

        # Set only the push URL to a bad target (fetch still works from sub_origin)
        _git(
            ["remote", "set-url", "--push", "origin",
             "https://private.example.com/sub.git"],
            str(sub_in_parent),
        )

        result = sync_submodule(change, str(parent))

        # FF should succeed locally
        assert result.ff_done is True
        # Push should fail
        assert result.pushed is False
        assert result.success is False
        assert "push failed" in result.error
        assert any("git push origin main" in cmd for cmd in result.handoff_commands)

    def test_feature_branch_cleanup(self, repo_with_submodule: tuple[Path, Path, Path]) -> None:
        """Feature branch in submodule should be deleted after sync."""
        parent, sub_origin, sub_in_parent = repo_with_submodule

        target_sha = _git(
            ["ls-tree", "main", "my-sub"], str(parent),
        ).stdout.split()[2]

        change = SubmoduleChange(
            path="my-sub",
            new_sha=target_sha,
            remote_url=str(sub_origin),
        )

        # Verify the feature branch exists on the remote before sync
        remote_branches = _git(
            ["branch", "-r"], str(sub_in_parent),
        ).stdout
        assert "openspec/test-feature" in remote_branches

        result = sync_submodule(change, str(parent), feature_branch="openspec/test-feature")

        assert result.success is True
        assert result.branch_deleted is True

        # Feature branch should be gone from the remote
        remote_branches_after = _git(
            ["branch", "-r"], str(sub_origin),
        ).stdout
        assert "openspec/test-feature" not in remote_branches_after


# ---------------------------------------------------------------------------
# Tests: detect_submodule_feature_branch
# ---------------------------------------------------------------------------

class TestDetectSubmoduleFeatureBranch:
    def test_finds_matching_branch(self, repo_with_submodule: tuple[Path, Path, Path]) -> None:
        parent, sub_origin, sub_in_parent = repo_with_submodule

        target_sha = _git(
            ["ls-tree", "main", "my-sub"], str(parent),
        ).stdout.split()[2]

        branch = detect_submodule_feature_branch(
            str(sub_in_parent), target_sha, "openspec/test-feature",
        )
        assert branch == "openspec/test-feature"

    def test_returns_none_for_missing_branch(self, repo_with_submodule: tuple[Path, Path, Path]) -> None:
        parent, sub_origin, sub_in_parent = repo_with_submodule

        target_sha = _git(
            ["ls-tree", "main", "my-sub"], str(parent),
        ).stdout.split()[2]

        branch = detect_submodule_feature_branch(
            str(sub_in_parent), target_sha, "nonexistent/branch",
        )
        assert branch is None


# ---------------------------------------------------------------------------
# Tests: no-submodule regression
# ---------------------------------------------------------------------------

class TestNoSubmoduleRegression:
    """Ensure the sync script is a no-op when no submodules changed."""

    def test_no_submodules_returns_zero(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "no-sub-repo")
        # Create a second commit so main@{1} exists
        (repo / "file.txt").write_text("x")
        _git(["add", "file.txt"], str(repo))
        _git(["commit", "--no-gpg-sign", "-m", "second"], str(repo))

        changes = detect_changed_submodules(str(repo))
        assert changes == []

"""Tests for prototype branch cleanup helpers.

Spec scenarios covered:
- skill-workflow.CleanupIncludesPrototypeBranches.prototype-cleanup-on-merge
  — local AND remote prototype/<change>/v* branches are deleted alongside
  the feature branch.
- skill-workflow.CleanupIncludesPrototypeBranches.stale-state-without-findings
  — branches are deleted even when no prototype-findings.md exists.

Design decisions: D4 (branch retention through feature lifecycle —
cleanup is the bookend that ends the retention period).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "cleanup-feature" / "scripts"),
)
from cleanup_prototype import (
    PROTOTYPE_BRANCH_PATTERN,
    delete_prototype_branches,
    enumerate_prototype_branches,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.fixture
def repo_with_prototype_branches(tmp_path: Path) -> Path:
    """A git repo with prototype/add-foo/v1, v2, v3 + an unrelated branch."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    for k, v in [
        ("user.email", "test@test.com"),
        ("user.name", "Test"),
        ("commit.gpgsign", "false"),
    ]:
        _git(tmp_path, "config", k, v)
    (tmp_path / "README.md").write_text("init")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "--no-gpg-sign", "-m", "init")
    _git(tmp_path, "branch", "-M", "main")

    # Prototype branches for add-foo
    for vid in ("v1", "v2", "v3"):
        _git(tmp_path, "branch", f"prototype/add-foo/{vid}", "main")

    # An unrelated branch — must NOT be deleted by the helper
    _git(tmp_path, "branch", "openspec/add-bar", "main")
    # A prototype branch for a different change — also must NOT be touched
    _git(tmp_path, "branch", "prototype/add-bar/v1", "main")

    return tmp_path


class TestEnumeratePrototypeBranches:
    def test_finds_all_variant_branches_for_change(
        self, repo_with_prototype_branches: Path
    ) -> None:
        branches = enumerate_prototype_branches(
            "add-foo", repo_dir=repo_with_prototype_branches
        )
        assert sorted(branches) == [
            "prototype/add-foo/v1",
            "prototype/add-foo/v2",
            "prototype/add-foo/v3",
        ]

    def test_does_not_match_other_changes(
        self, repo_with_prototype_branches: Path
    ) -> None:
        # prototype/add-bar/v1 exists but must not be returned for add-foo
        branches = enumerate_prototype_branches(
            "add-foo", repo_dir=repo_with_prototype_branches
        )
        assert "prototype/add-bar/v1" not in branches

    def test_does_not_match_openspec_branches(
        self, repo_with_prototype_branches: Path
    ) -> None:
        branches = enumerate_prototype_branches(
            "add-foo", repo_dir=repo_with_prototype_branches
        )
        assert not any(b.startswith("openspec/") for b in branches)

    def test_pattern_constant_matches_spec(self) -> None:
        # The pattern must include both the prototype/ namespace AND the
        # /v<n> suffix so unrelated branches like prototype/<change>/main
        # (if anyone created one) wouldn't be deleted.
        assert "prototype/" in PROTOTYPE_BRANCH_PATTERN
        assert "v" in PROTOTYPE_BRANCH_PATTERN

    def test_returns_empty_when_no_prototype_branches_exist(
        self, tmp_path: Path
    ) -> None:
        # Spec scenario stale-state-without-findings: caller may invoke
        # cleanup even when no prototype branches were ever created.
        # Helper must not fail — it must return an empty list.
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        for k, v in [
            ("user.email", "t@t"),
            ("user.name", "T"),
            ("commit.gpgsign", "false"),
        ]:
            _git(tmp_path, "config", k, v)
        (tmp_path / "x").write_text("")
        _git(tmp_path, "add", "x")
        _git(tmp_path, "commit", "--no-gpg-sign", "-m", "x")
        _git(tmp_path, "branch", "-M", "main")

        assert enumerate_prototype_branches("add-foo", repo_dir=tmp_path) == []


class TestDeletePrototypeBranches:
    def test_deletes_all_change_specific_branches(
        self, repo_with_prototype_branches: Path
    ) -> None:
        deleted = delete_prototype_branches(
            "add-foo", repo_dir=repo_with_prototype_branches
        )
        assert sorted(deleted) == [
            "prototype/add-foo/v1",
            "prototype/add-foo/v2",
            "prototype/add-foo/v3",
        ]

        remaining = _git(repo_with_prototype_branches, "branch", "--list", "prototype/*")
        assert "add-foo" not in remaining
        # Different-change prototype branch survives
        assert "prototype/add-bar/v1" in remaining

    def test_unrelated_branches_untouched(
        self, repo_with_prototype_branches: Path
    ) -> None:
        delete_prototype_branches(
            "add-foo", repo_dir=repo_with_prototype_branches
        )
        # openspec/add-bar must still exist
        bars = _git(repo_with_prototype_branches, "branch", "--list", "openspec/add-bar")
        assert "openspec/add-bar" in bars

    def test_idempotent_when_nothing_to_delete(self, tmp_path: Path) -> None:
        # Spec scenario stale-state-without-findings — re-running cleanup
        # after success must not error.
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        for k, v in [
            ("user.email", "t@t"),
            ("user.name", "T"),
            ("commit.gpgsign", "false"),
        ]:
            _git(tmp_path, "config", k, v)
        (tmp_path / "x").write_text("")
        _git(tmp_path, "add", "x")
        _git(tmp_path, "commit", "--no-gpg-sign", "-m", "x")
        _git(tmp_path, "branch", "-M", "main")

        result = delete_prototype_branches("add-foo", repo_dir=tmp_path)
        assert result == []  # nothing to delete; no error

    def test_force_delete_unmerged_branches(
        self, repo_with_prototype_branches: Path
    ) -> None:
        # Add a commit to one prototype branch so it's not fully merged into main.
        # Without force, ``git branch -d`` would refuse — D4 says cleanup
        # MUST delete prototype branches regardless of merge status (they
        # were exploratory; the chosen design landed on the feature branch).
        _git(repo_with_prototype_branches, "checkout", "prototype/add-foo/v1")
        (repo_with_prototype_branches / "extra.txt").write_text("variant-only change")
        _git(repo_with_prototype_branches, "add", "extra.txt")
        _git(repo_with_prototype_branches, "commit", "--no-gpg-sign", "-m", "v1 extra")
        _git(repo_with_prototype_branches, "checkout", "main")

        deleted = delete_prototype_branches(
            "add-foo", repo_dir=repo_with_prototype_branches
        )
        assert "prototype/add-foo/v1" in deleted
        # Confirm it's actually gone
        remaining = _git(
            repo_with_prototype_branches,
            "branch",
            "--list",
            "prototype/add-foo/v1",
        )
        assert remaining == ""

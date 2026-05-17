"""Tests for post-merge OpenSpec cleanup planning."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Add scripts dir to path so we can import post_merge_cleanup
sys.path.insert(0, str(Path(__file__).parent.parent))

from post_merge_cleanup import plan_cleanup, render_prompt


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _init_repo(repo: Path) -> None:
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("test\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "init")
    _git(repo, "branch", "-M", "main")


def test_plan_cleanup_filters_to_merged_local_openspec_changes(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    change_dir = repo / "openspec" / "changes" / "add-user-export"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text("# Proposal\n")
    (repo / ".git-worktrees").mkdir()
    (repo / ".git-worktrees" / ".registry.json").write_text(json.dumps({
        "version": 1,
        "entries": [{
            "change_id": "add-user-export",
            "agent_id": "wp-api",
            "branch": "openspec/add-user-export--wp-api",
            "worktree_path": str(repo / ".git-worktrees/add-user-export/wp-api"),
        }],
    }))
    _git(repo, "branch", "openspec/add-user-export")
    _git(repo, "branch", "openspec/add-user-export--wp-api")

    candidates = plan_cleanup([
        {
            "pr_number": 42,
            "origin": "openspec",
            "change_id": "add-user-export",
            "branch": "openspec/add-user-export",
            "success": True,
        },
        {
            "pr_number": 43,
            "origin": "dependabot",
            "change_id": None,
            "success": True,
        },
        {
            "pr_number": 44,
            "origin": "openspec",
            "change_id": "not-local",
            "success": True,
        },
        {
            "pr_number": 45,
            "origin": "openspec",
            "change_id": "unmerged",
            "success": False,
        },
    ], repo_dir=repo)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["pr_number"] == 42
    assert candidate["change_id"] == "add-user-export"
    assert candidate["command"] == (
        "/cleanup-feature add-user-export --post-merge --pr 42"
    )
    assert candidate["local_branches"] == [
        "openspec/add-user-export",
        "openspec/add-user-export--wp-api",
    ]
    assert len(candidate["registry_entries"]) == 1


def test_render_prompt_requires_explicit_approval() -> None:
    prompt = render_prompt([{
        "pr_number": 42,
        "change_id": "add-user-export",
        "head_branch": "openspec/add-user-export",
        "registry_entries": [],
        "local_branches": [],
        "command": "/cleanup-feature add-user-export --post-merge --pr 42",
    }])

    assert "Proceed with post-merge cleanup" in prompt
    assert "Only run the listed cleanup commands after explicit approval" in prompt
    assert "/cleanup-feature add-user-export --post-merge --pr 42" in prompt

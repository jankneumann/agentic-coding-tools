"""Post-merge hook tests for coordinator-task-status-renderer.

Covers tasks 4.7, 4.8, 4.8a.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _create_branch_with_tasks_md(repo: Path, change_id: str = "demo") -> None:
    """Create a feature branch with a tasks.md, then return to main."""
    subprocess.run(["git", "checkout", "-b", "feature"], cwd=repo, check=True, capture_output=True)
    target_dir = repo / "openspec" / "changes" / change_id
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "tasks.md").write_text("# Tasks\n\n- [ ] 1.1 First\n")
    subprocess.run(["git", "add", "openspec/"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "--no-verify", "-m", "add tasks"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "checkout", "main"], cwd=repo, check=True, capture_output=True)


def _create_branch_unrelated(repo: Path) -> None:
    subprocess.run(["git", "checkout", "-b", "unrelated"], cwd=repo, check=True, capture_output=True)
    (repo / "other.txt").write_text("hello\n")
    subprocess.run(["git", "add", "other.txt"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "--no-verify", "-m", "unrelated"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "checkout", "main"], cwd=repo, check=True, capture_output=True)


# ---------- 4.7 post-merge fires on merged tasks.md -----------------------


def test_post_merge_invokes_renderer_when_tasks_md_merged(
    hermetic_repo, renderer_stub
):
    stub, log = renderer_stub(exit_code=0)
    _create_branch_with_tasks_md(hermetic_repo, "demo")
    env = os.environ.copy()
    env["COORDINATOR_TASK_STATUS_RENDERER"] = str(stub)
    result = subprocess.run(
        ["git", "merge", "--no-edit", "--no-ff", "feature"],
        cwd=hermetic_repo,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"merge failed: {result.stderr}"
    assert log.exists(), "post-merge must invoke renderer when tasks.md was merged"
    assert "demo" in log.read_text()


# ---------- 4.8 post-merge skips when merge did not touch tasks.md ------


def test_post_merge_skips_when_no_tasks_md(hermetic_repo, renderer_stub):
    stub, log = renderer_stub(exit_code=0)
    _create_branch_unrelated(hermetic_repo)
    env = os.environ.copy()
    env["COORDINATOR_TASK_STATUS_RENDERER"] = str(stub)
    result = subprocess.run(
        ["git", "merge", "--no-edit", "--no-ff", "unrelated"],
        cwd=hermetic_repo,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert not log.exists(), "post-merge must NOT invoke renderer for unrelated merge"


# ---------- 4.8a post-merge honors env-var override ----------------------


def test_post_merge_uses_env_var_path_when_set(hermetic_repo, renderer_stub):
    stub, log = renderer_stub(exit_code=0)
    _create_branch_with_tasks_md(hermetic_repo, "demo")
    env = os.environ.copy()
    env["COORDINATOR_TASK_STATUS_RENDERER"] = str(stub)
    result = subprocess.run(
        ["git", "merge", "--no-edit", "--no-ff", "feature"],
        cwd=hermetic_repo,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert log.exists()

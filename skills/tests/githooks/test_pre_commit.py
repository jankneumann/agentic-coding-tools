"""Pre-commit hook tests for coordinator-task-status-renderer.

Covers tasks 4.1, 4.2, 4.3, 4.3a, 4.3b.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _stage_tasks_md(repo: Path, change_id: str = "demo", body: str | None = None) -> Path:
    target_dir = repo / "openspec" / "changes" / change_id
    target_dir.mkdir(parents=True, exist_ok=True)
    tasks_md = target_dir / "tasks.md"
    tasks_md.write_text(body or "# Tasks — demo\n\n- [ ] 1.1 First task\n")
    subprocess.run(
        ["git", "add", "openspec/"],
        cwd=repo,
        check=True,
    )
    return tasks_md


# ---------- 4.1 pre-commit invokes renderer when tasks.md staged ----------


def test_pre_commit_invokes_renderer_on_staged_tasks_md(
    hermetic_repo, renderer_stub, run_with_hook
):
    stub, log = renderer_stub(exit_code=0)
    _stage_tasks_md(hermetic_repo, "demo")
    result = run_with_hook(
        ["git", "commit", "-m", "add tasks"],
        hermetic_repo,
        env_extra={"COORDINATOR_TASK_STATUS_RENDERER": str(stub)},
    )
    assert result.returncode == 0, f"commit failed: {result.stderr}"
    assert log.exists(), "renderer stub was not invoked"
    text = log.read_text()
    assert "demo" in text, f"renderer not invoked with change-id 'demo': {text!r}"


# ---------- 4.2 pre-commit re-stages the rendered file --------------------


def test_pre_commit_re_stages_rendered_file(hermetic_repo, renderer_stub, run_with_hook):
    """The hook must invoke `git add` on the tasks.md after rendering.

    We simulate the renderer modifying the file: the stub rewrites tasks.md
    with new content before exiting, then we verify the staged blob matches
    the post-render content (not the pre-render content).
    """
    log_path = hermetic_repo / "_invocations.log"
    target_md = hermetic_repo / "openspec/changes/demo/tasks.md"
    target_md.parent.mkdir(parents=True, exist_ok=True)
    target_md.write_text("# Tasks — demo\n\n- [ ] 1.1 First\n")
    subprocess.run(["git", "add", "openspec/"], cwd=hermetic_repo, check=True)

    # Renderer stub that ALSO mutates tasks.md.
    stub = hermetic_repo / "renderer_modify.sh"
    stub.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{log_path}"\n'
        f'cat > "{target_md}" <<EOF\n'
        '# Tasks — demo\n'
        '\n'
        '- [ ] 1.1 First\n'
        '\n'
        '<!-- GENERATED: begin coordinator:tasks-status -->\n'
        'rendered content\n'
        '<!-- GENERATED: end coordinator:tasks-status -->\n'
        'EOF\n'
    )
    stub.chmod(0o755)

    result = subprocess.run(
        ["git", "commit", "-m", "add tasks with render"],
        cwd=hermetic_repo,
        capture_output=True,
        text=True,
        env={
            **__import__("os").environ,
            "COORDINATOR_TASK_STATUS_RENDERER": str(stub),
        },
    )
    assert result.returncode == 0, f"commit failed: {result.stderr}"
    # The latest commit should have the rendered content (re-stage worked).
    show = subprocess.run(
        ["git", "show", "HEAD:openspec/changes/demo/tasks.md"],
        cwd=hermetic_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "GENERATED: begin coordinator:tasks-status" in show.stdout, (
        "pre-commit must re-stage the rendered file"
    )


# ---------- 4.3 pre-commit skips renderer when no tasks.md staged ---------


def test_pre_commit_skips_when_no_tasks_md_staged(
    hermetic_repo, renderer_stub, run_with_hook
):
    stub, log = renderer_stub(exit_code=0)
    # Stage an unrelated file.
    (hermetic_repo / "other.txt").write_text("hello\n")
    subprocess.run(["git", "add", "other.txt"], cwd=hermetic_repo, check=True)
    result = run_with_hook(
        ["git", "commit", "-m", "unrelated change"],
        hermetic_repo,
        env_extra={"COORDINATOR_TASK_STATUS_RENDERER": str(stub)},
    )
    assert result.returncode == 0, f"commit failed: {result.stderr}"
    assert not log.exists(), "renderer stub should NOT have been invoked"


# ---------- 4.3a pre-commit allows commit when renderer exits non-zero ----


def test_pre_commit_continues_when_renderer_fails(
    hermetic_repo, renderer_stub, run_with_hook
):
    """Renderer non-zero exit must NOT block the commit, and `git add` for that
    file must NOT run."""
    log_path = hermetic_repo / "_invocations.log"
    target_md = hermetic_repo / "openspec/changes/demo/tasks.md"
    target_md.parent.mkdir(parents=True, exist_ok=True)
    target_md.write_text("# Tasks — demo\n\n- [ ] 1.1 First\n")
    subprocess.run(["git", "add", "openspec/"], cwd=hermetic_repo, check=True)
    initial_hash = subprocess.run(
        ["git", "ls-files", "-s", "openspec/changes/demo/tasks.md"],
        cwd=hermetic_repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()[1]

    # Stub mutates file AND exits non-zero. The hook must not re-stage.
    stub = hermetic_repo / "renderer_fail.sh"
    stub.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{log_path}"\n'
        f'echo "mutated" >> "{target_md}"\n'
        "exit 7\n"
    )
    stub.chmod(0o755)

    result = subprocess.run(
        ["git", "commit", "-m", "renderer fails but commit proceeds"],
        cwd=hermetic_repo,
        capture_output=True,
        text=True,
        env={
            **__import__("os").environ,
            "COORDINATOR_TASK_STATUS_RENDERER": str(stub),
        },
    )
    assert result.returncode == 0, (
        f"commit must proceed even when renderer fails: {result.stderr}"
    )
    # Renderer was invoked.
    assert log_path.exists()
    # Staged blob is unchanged (renderer's mutation NOT re-added).
    final_hash = subprocess.run(
        ["git", "show", "HEAD:openspec/changes/demo/tasks.md"],
        cwd=hermetic_repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "mutated" not in final_hash, (
        "pre-commit must NOT re-stage when renderer exited non-zero"
    )
    _ = initial_hash  # silence unused


# ---------- 4.3b pre-commit honors env-var override ----------------------


def test_pre_commit_uses_env_var_path_when_set(
    hermetic_repo, renderer_stub, run_with_hook
):
    stub, log = renderer_stub(exit_code=0)
    _stage_tasks_md(hermetic_repo)
    result = run_with_hook(
        ["git", "commit", "-m", "use env override"],
        hermetic_repo,
        env_extra={"COORDINATOR_TASK_STATUS_RENDERER": str(stub)},
    )
    assert result.returncode == 0
    assert log.exists(), "env-var override stub should have been invoked"


def test_pre_commit_falls_back_to_default_path_when_env_unset(hermetic_repo):
    """When COORDINATOR_TASK_STATUS_RENDERER is unset, the hook tries the
    default path; if that file doesn't exist in the hermetic repo, the hook
    SHALL log a warning and still allow the commit."""
    target_dir = hermetic_repo / "openspec" / "changes" / "demo"
    target_dir.mkdir(parents=True)
    (target_dir / "tasks.md").write_text("# Tasks\n")
    subprocess.run(["git", "add", "openspec/"], cwd=hermetic_repo, check=True)
    # No env var override; the default path doesn't exist in the hermetic repo.
    import os
    env = {k: v for k, v in os.environ.items() if k != "COORDINATOR_TASK_STATUS_RENDERER"}
    result = subprocess.run(
        ["git", "commit", "-m", "no env"],
        cwd=hermetic_repo,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, (
        f"commit must proceed even when default renderer path missing: {result.stderr}"
    )

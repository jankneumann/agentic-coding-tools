"""Hermetic git hook tests.

Per the Phase 4 hook test strategy:
- ``tmp_path`` git repo with ``core.hooksPath`` set to a copy of ``.githooks/``.
- The renderer is stubbed via ``COORDINATOR_TASK_STATUS_RENDERER`` env var
  pointing at a fake script that records argv to a temp file.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Iterator

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2].parent
_GITHOOKS_SRC = _REPO_ROOT / ".githooks"


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        cmd, cwd=str(cwd), env=full_env, capture_output=True, text=True
    )


@pytest.fixture()
def hermetic_repo(tmp_path: Path) -> Iterator[Path]:
    """A git repo with our hooks installed and a clean initial commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    # Init repo with main as default branch.
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(repo)],
        check=True,
        capture_output=True,
    )
    # Configure identity (required for commits).
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)
    # Copy hooks dir into the repo (so we modify it freely).
    repo_hooks = repo / ".githooks"
    shutil.copytree(_GITHOOKS_SRC, repo_hooks)
    # Make hooks executable.
    for f in repo_hooks.iterdir():
        if f.is_file():
            f.chmod(f.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    subprocess.run(
        ["git", "config", "core.hooksPath", ".githooks"], cwd=repo, check=True
    )
    # Initial commit so HEAD exists.
    (repo / "README.md").write_text("init\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "--no-verify", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    yield repo


@pytest.fixture()
def renderer_stub(tmp_path: Path):
    """Create a renderer-stub script that records its argv to a temp file.

    Returns a (stub_path, invocation_log) pair where ``invocation_log`` is a
    helper that reads the recorded argv on demand.
    """
    log_path = tmp_path / "renderer.invocations"

    def _make_stub(
        *, exit_code: int = 0, record_to: Path | None = None
    ) -> tuple[Path, Path]:
        rec = record_to or log_path
        stub = tmp_path / f"renderer_stub_exit{exit_code}.sh"
        stub.write_text(
            "#!/bin/sh\n"
            f'echo "$@" >> "{rec}"\n'
            f"exit {exit_code}\n"
        )
        stub.chmod(0o755)
        return stub, rec

    return _make_stub


def _run_with_hook(
    cmd: list[str], cwd: Path, *, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True)


@pytest.fixture()
def run_with_hook():
    """Run a subprocess with extra env vars and capture output."""
    return _run_with_hook

"""worktree.py setup must not start work on a stale base (#619).

Two defects:

- A *new* branch was created from the local ``main`` ref even though setup
  had just run ``git fetch origin main``. The shared checkout's ``main`` lags
  whenever other sessions merge, so worktrees silently came up behind
  ``origin/main``.
- An *existing* same-name branch (for example a leftover ``--cleanup`` branch
  from an aborted run) was reused as-is, however stale.

Every test gives the temp repo a real ``origin`` and then advances
``origin/main`` past local ``main``, which is the situation the bugs need.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

import worktree


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(repo: Path, name: str, content: str) -> str:
    (repo / name).write_text(content)
    _git(repo, "add", name)
    _git(repo, "commit", "--no-gpg-sign", "-m", f"add {name}")
    return _git(repo, "rev-parse", "HEAD")


@contextlib.contextmanager
def _chdir(path: Path) -> Iterator[None]:
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def _args(**kwargs: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "command": "setup",
        "change_id": None,
        "branch": None,
        "prefix": None,
        "no_bootstrap": True,
        "agent_id": None,
        "parent": False,
        "sibling": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


@pytest.fixture
def repo_behind_origin(
    git_repo: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, str, str]:
    """A repo whose local ``main`` is one commit behind ``origin/main``.

    Returns (repo, stale_local_main_sha, origin_main_sha).
    """
    monkeypatch.delenv("OPENSPEC_BRANCH_OVERRIDE", raising=False)
    _git(git_repo, "branch", "-M", "main")
    origin = tmp_path_factory.mktemp("origin") / "origin.git"
    _git(git_repo, "clone", "--bare", str(git_repo), str(origin))
    _git(git_repo, "remote", "add", "origin", str(origin))
    _git(git_repo, "fetch", "origin")
    stale = _git(git_repo, "rev-parse", "main")

    # Another session merges to origin; this checkout's main does not move.
    other = tmp_path_factory.mktemp("other")
    _git(other, "clone", str(origin), "clone")
    clone = other / "clone"
    for key, value in [("user.email", "o@test.com"), ("user.name", "O"), ("commit.gpgsign", "false")]:
        _git(clone, "config", key, value)
    merged = _commit(clone, "merged-elsewhere.txt", "landed on origin/main\n")
    _git(clone, "push", "origin", "HEAD:main")
    return git_repo, stale, merged


def _worktree_head(repo: Path, change_id: str, agent_id: str | None = None) -> str:
    path = repo / ".git-worktrees" / change_id
    if agent_id:
        path = path / agent_id
    return _git(path, "rev-parse", "HEAD")


def test_new_branch_starts_from_origin_main_not_stale_local_main(
    repo_behind_origin: tuple[Path, str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    repo, stale, merged = repo_behind_origin

    with _chdir(repo):
        assert worktree.cmd_setup(_args(change_id="feat")) == 0

    assert _worktree_head(repo, "feat") == merged != stale
    out = capsys.readouterr().out
    assert "BRANCH_START_POINT=origin/main" in out
    assert "BRANCH_START_SOURCE=main" in out


def test_leftover_branch_without_unique_work_is_fast_forwarded(
    repo_behind_origin: tuple[Path, str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    # The #619 incident: an aborted cleanup left `--cleanup` at an old commit.
    repo, stale, merged = repo_behind_origin
    _git(repo, "branch", "openspec/feat--cleanup", stale)

    with _chdir(repo):
        assert worktree.cmd_setup(_args(change_id="feat", agent_id="cleanup")) == 0

    assert _worktree_head(repo, "feat", "cleanup") == merged
    out = capsys.readouterr().out
    assert "BRANCH_FAST_FORWARDED=origin/main" in out


def test_rebase_merged_commits_do_not_count_as_unique_work(
    repo_behind_origin: tuple[Path, str, str],
) -> None:
    # A rebase-merge lands the branch's patches on main under new SHAs. The old
    # branch is then not an ancestor of main, but it holds no unmerged work.
    repo, stale, merged = repo_behind_origin
    _git(repo, "fetch", "-q", "origin")  # make the merged commit's object available locally
    _git(repo, "checkout", "-q", "-b", "openspec/feat--cleanup", stale)
    _git(repo, "cherry-pick", "--no-gpg-sign", merged)  # same patch, new SHA
    _git(repo, "checkout", "-q", "main")

    with _chdir(repo):
        assert worktree.cmd_setup(_args(change_id="feat", agent_id="cleanup")) == 0

    assert _worktree_head(repo, "feat", "cleanup") == merged


def test_branch_with_unique_commits_is_kept_and_reported(
    repo_behind_origin: tuple[Path, str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    # A feature branch behind main is normal; its own work must never be discarded.
    repo, stale, _merged = repo_behind_origin
    _git(repo, "checkout", "-q", "-b", "openspec/feat", stale)
    own = _commit(repo, "feature-only.txt", "work in progress\n")
    _git(repo, "checkout", "-q", "main")

    with _chdir(repo):
        assert worktree.cmd_setup(_args(change_id="feat")) == 0

    assert _worktree_head(repo, "feat") == own
    out = capsys.readouterr().out
    assert "BRANCH_BEHIND_BASE=1" in out
    assert "BRANCH_FAST_FORWARDED" not in out


def test_branch_checked_out_in_a_live_worktree_is_left_alone(
    repo_behind_origin: tuple[Path, str, str],
) -> None:
    # Moving a branch under an existing worktree could orphan uncommitted work.
    repo, stale, _merged = repo_behind_origin
    _git(repo, "branch", "openspec/feat", stale)
    live = repo / ".git-worktrees" / "feat"
    live.parent.mkdir(parents=True)
    _git(repo, "worktree", "add", str(live), "openspec/feat")

    with _chdir(repo):
        assert worktree.cmd_setup(_args(change_id="feat")) == 0

    assert _worktree_head(repo, "feat") == stale

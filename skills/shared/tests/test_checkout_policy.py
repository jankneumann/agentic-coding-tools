"""Tests for the shared checkout mutation policy guard."""

from __future__ import annotations

import sys
import subprocess
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from shared import checkout_policy as cp  # noqa: E402
from shared.environment_profile import EnvironmentProfile  # noqa: E402


def _profile(isolated: bool) -> EnvironmentProfile:
    return EnvironmentProfile(
        isolation_provided=isolated,
        source="env_var",
        details={"test": True},
    )


@pytest.fixture(autouse=True)
def _stable_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Avoid host container heuristics leaking into policy tests."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cp.environment_profile, "detect", lambda agent_id=None: _profile(False))


def test_local_shared_checkout_blocks_mutation(tmp_path: Path) -> None:
    shared = tmp_path / "repo"
    shared.mkdir()

    policy = cp.classify_checkout(cwd=shared, repo_root=shared)

    assert policy.allowed is False
    assert policy.reason == "shared_checkout_blocked"
    assert "managed worktree" in policy.message


def test_local_managed_worktree_allows_mutation(tmp_path: Path) -> None:
    shared = tmp_path / "repo"
    worktree = shared / ".git-worktrees" / "change-a"
    nested = worktree / "skills"
    nested.mkdir(parents=True)

    policy = cp.classify_checkout(cwd=nested, repo_root=shared)

    assert policy.allowed is True
    assert policy.reason == "managed_worktree"
    assert policy.worktree_root == worktree


def test_managed_worktree_detected_without_explicit_repo_root(tmp_path: Path) -> None:
    shared = tmp_path / "repo"
    worktree = shared / ".git-worktrees" / "change-a"
    nested = worktree / "skills"
    nested.mkdir(parents=True)

    policy = cp.classify_checkout(cwd=nested)

    assert policy.allowed is True
    assert policy.reason == "managed_worktree"
    assert policy.repo_root == shared


def test_isolated_harness_allows_current_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = tmp_path / "repo"
    checkout.mkdir()
    monkeypatch.setattr(cp.environment_profile, "detect", lambda agent_id=None: _profile(True))

    policy = cp.classify_checkout(cwd=checkout, repo_root=checkout)

    assert policy.allowed is True
    assert policy.reason == "isolated_harness"
    assert policy.isolation_provided is True


def test_sync_point_explicitly_allows_shared_checkout(tmp_path: Path) -> None:
    shared = tmp_path / "repo"
    shared.mkdir()

    policy = cp.classify_checkout(cwd=shared, repo_root=shared, sync_point=True)

    assert policy.allowed is True
    assert policy.reason == "approved_sync_point"
    assert "clean-tree" in policy.message
    assert "active-agent" in policy.message


def test_require_mutation_allowed_raises_for_shared_checkout(tmp_path: Path) -> None:
    shared = tmp_path / "repo"
    shared.mkdir()

    with pytest.raises(cp.CheckoutPolicyError) as exc:
        cp.require_mutation_allowed(cwd=shared, repo_root=shared)

    assert "shared checkout" in str(exc.value)


def test_cli_json_success_for_managed_worktree(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    shared = tmp_path / "repo"
    worktree = shared / ".git-worktrees" / "change-a"
    worktree.mkdir(parents=True)

    rc = cp.main(
        [
            "require-mutation",
            "--cwd",
            str(worktree),
            "--repo-root",
            str(shared),
            "--json",
        ]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert '"allowed": true' in out
    assert '"reason": "managed_worktree"' in out


def test_cli_rejects_local_shared_checkout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    shared = tmp_path / "repo"
    shared.mkdir()

    rc = cp.main(
        [
            "require-mutation",
            "--cwd",
            str(shared),
            "--repo-root",
            str(shared),
        ]
    )

    assert rc == 1
    captured = capsys.readouterr()
    assert "shared checkout" in captured.err


def test_script_path_cli_rejects_local_shared_checkout(tmp_path: Path) -> None:
    shared = tmp_path / "repo"
    shared.mkdir()
    script = Path(__file__).resolve().parents[1] / "checkout_policy.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "require-mutation",
            "--cwd",
            str(shared),
            "--repo-root",
            str(shared),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={"AGENT_EXECUTION_ENV": "local"},
    )

    assert result.returncode == 1
    assert "shared checkout" in result.stderr


def test_execution_root_requires_registered_git_identity(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    root = repo / ".git-worktrees" / "change-a"
    root.mkdir(parents=True)
    (repo / ".git").mkdir()
    (root / ".git").write_text("gitdir: elsewhere\n")

    assert cp.is_managed_execution_root(
        root,
        repo,
        git_toplevel=root,
        git_common_dir=repo / ".git",
        read_only=False,
    )
    assert not cp.is_managed_execution_root(
        root,
        repo,
        git_toplevel=repo,
        git_common_dir=repo / ".git",
        read_only=False,
    )


def test_review_snapshot_is_read_only_only(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    snapshot = repo / ".git-worktrees" / ".review-snapshots" / "attempt-1"
    snapshot.mkdir(parents=True)
    (repo / ".git").mkdir()
    (snapshot / ".git").write_text("gitdir: elsewhere\n")

    common = repo / ".git"
    assert cp.is_managed_execution_root(
        snapshot,
        repo,
        git_toplevel=snapshot,
        git_common_dir=common,
        read_only=True,
    )
    assert not cp.is_managed_execution_root(
        snapshot,
        repo,
        git_toplevel=snapshot,
        git_common_dir=common,
        read_only=False,
    )


def test_execution_root_rejects_shared_home_and_symlink(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = repo / ".git-worktrees" / "change-a"
    target.mkdir(parents=True)
    (repo / ".git").mkdir()
    (target / ".git").write_text("gitdir: elsewhere\n")
    link = repo / ".git-worktrees" / "change-link"
    link.symlink_to(target, target_is_directory=True)

    common = repo / ".git"
    assert not cp.is_managed_execution_root(
        repo,
        repo,
        git_toplevel=repo,
        git_common_dir=common,
        read_only=False,
    )
    assert not cp.is_managed_execution_root(
        link,
        repo,
        git_toplevel=target,
        git_common_dir=common,
        read_only=False,
    )

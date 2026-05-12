"""Tests for environment-aware short-circuits in worktree.py.

Covers spec scenarios:
- worktree-isolation.2 (cloud harness short-circuits setup)
- worktree-isolation.3 (teardown/pin/unpin/heartbeat/gc no-op under cloud)
- worktree-isolation.7 (branch override without cloud signal creates worktree)
- worktree-isolation.8 (cloud signal without branch override short-circuits)
- worktree-isolation.9 (existing local single-agent run unchanged)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import worktree  # noqa: E402


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with a single commit on main."""
    subprocess.run(["git", "init", "-b", "main", str(tmp_path)], check=True, capture_output=True)
    for key, value in [
        ("user.email", "test@test.com"),
        ("user.name", "Test"),
        ("commit.gpgsign", "false"),
    ]:
        subprocess.run(
            ["git", "config", key, value],
            cwd=str(tmp_path),
            check=True,
            capture_output=True,
        )
    readme = tmp_path / "README.md"
    readme.write_text("test repo\n")
    subprocess.run(["git", "add", "README.md"], cwd=str(tmp_path), check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    return tmp_path


class TestSetupShortCircuit:
    """setup under isolation_provided=true emits current checkout and skips worktree creation."""

    def test_cloud_setup_emits_toplevel_and_current_branch(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "cloud")

        ns = worktree.argparse.Namespace(
            change_id="feature-x", agent_id=None, branch=None, prefix=None
        )
        rc = worktree.cmd_setup(ns)
        assert rc == 0

        out = capsys.readouterr()
        assert f"WORKTREE_PATH={git_repo}" in out.out
        assert "WORKTREE_BRANCH=main" in out.out
        assert "ISOLATION_PROVIDED=true" in out.err
        assert "isolation_provided=true" in out.err
        assert "source=env_var" in out.err

        # Crucially: no .git-worktrees/ was created
        assert not (git_repo / ".git-worktrees").exists()

    def test_cloud_setup_survives_branch_already_checked_out(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The exact bug this feature fixes: the cloud harness has already
        checked out a branch at the repo root. Pre-fix, `git worktree add`
        failed with `fatal: already used by worktree`. Post-fix, setup
        short-circuits cleanly.
        """
        monkeypatch.chdir(git_repo)
        # Simulate the harness having checked out a mandated branch
        subprocess.run(
            ["git", "checkout", "-b", "claude/some-fix-branch"],
            cwd=str(git_repo),
            check=True,
            capture_output=True,
        )
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "cloud")
        monkeypatch.setenv("OPENSPEC_BRANCH_OVERRIDE", "claude/some-fix-branch")

        ns = worktree.argparse.Namespace(
            change_id="some-fix", agent_id=None, branch=None, prefix=None
        )
        rc = worktree.cmd_setup(ns)
        assert rc == 0

        out = capsys.readouterr()
        assert "WORKTREE_BRANCH=claude/some-fix-branch" in out.out
        assert not (git_repo / ".git-worktrees").exists()


class TestWriteOpsShortCircuit:
    """teardown, heartbeat, pin, unpin, gc are no-ops under cloud mode."""

    def test_teardown_short_circuits(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "cloud")

        ns = worktree.argparse.Namespace(
            change_id="feature-x", agent_id=None, prefix=None
        )
        rc = worktree.cmd_teardown(ns)
        assert rc == 0

        out = capsys.readouterr()
        assert "REMOVED=skipped" in out.out
        assert "skipped teardown" in out.err

    def test_heartbeat_short_circuits(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "cloud")

        ns = worktree.argparse.Namespace(change_id="feature-x", agent_id=None)
        rc = worktree.cmd_heartbeat(ns)
        assert rc == 0
        assert "skipped heartbeat" in capsys.readouterr().err

    def test_pin_short_circuits(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "cloud")

        ns = worktree.argparse.Namespace(change_id="feature-x", agent_id=None)
        rc = worktree.cmd_pin(ns)
        assert rc == 0
        assert "skipped pin" in capsys.readouterr().err

    def test_unpin_short_circuits(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "cloud")

        ns = worktree.argparse.Namespace(change_id="feature-x", agent_id=None)
        rc = worktree.cmd_unpin(ns)
        assert rc == 0
        assert "skipped unpin" in capsys.readouterr().err

    def test_gc_short_circuits(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "cloud")

        ns = worktree.argparse.Namespace(force=False, stale_after="24h")
        rc = worktree.cmd_gc(ns)
        assert rc == 0
        assert "skipped gc" in capsys.readouterr().err


class TestLocalBackwardCompat:
    """With AGENT_EXECUTION_ENV=local, behavior is unchanged from pre-change."""

    def test_local_setup_creates_worktree(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit local mode still creates .git-worktrees/ as before."""
        monkeypatch.chdir(git_repo)
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "local")
        # Heuristic and coordinator must stay silent for this regression
        # test even if the host is a dev container.
        monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
        monkeypatch.delenv("CODESPACES", raising=False)

        ns = worktree.argparse.Namespace(
            change_id="feature-y",
            agent_id=None,
            branch=None,
            prefix=None,
            no_bootstrap=True,
        )
        rc = worktree.cmd_setup(ns)
        assert rc == 0
        # The worktree directory exists
        assert (git_repo / ".git-worktrees" / "feature-y").is_dir()


class TestOrthogonalBranchOverride:
    """OPENSPEC_BRANCH_OVERRIDE does NOT imply cloud mode (D2/spec req 3)."""

    def test_branch_override_alone_creates_worktree(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        # Branch override is set, but no cloud signal of any kind
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "local")
        monkeypatch.setenv(
            "OPENSPEC_BRANCH_OVERRIDE", "claude/review-branch"
        )
        monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
        monkeypatch.delenv("CODESPACES", raising=False)

        ns = worktree.argparse.Namespace(
            change_id="review",
            agent_id=None,
            branch=None,
            prefix=None,
            no_bootstrap=True,
        )
        rc = worktree.cmd_setup(ns)
        assert rc == 0
        # Worktree WAS created — branch override alone does not short-circuit
        assert (git_repo / ".git-worktrees" / "review").is_dir()

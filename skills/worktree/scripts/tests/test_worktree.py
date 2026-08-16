"""Tests for scripts/worktree.py."""

import argparse
import contextlib
import os
import subprocess
import threading

# Import the module under test
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import worktree
from worktree import (
    cmd_gc,
    cmd_heartbeat,
    cmd_list,
    cmd_pin,
    cmd_unpin,
    default_branch,
    find_entry,
    load_registry,
    parse_duration_hours,
    remove_entry,
    resolve_branch,
    save_registry,
    worktree_path,
)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo for testing."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    # Repo-local config only; never touch the user's global git config.
    # Disable commit signing so tests work in sandboxes that enforce GPG globally.
    for key, value in [
        ("user.email", "test@test.com"),
        ("user.name", "Test"),
        ("commit.gpgsign", "false"),
        ("tag.gpgsign", "false"),
    ]:
        subprocess.run(
            ["git", "config", key, value],
            cwd=str(tmp_path),
            check=True,
            capture_output=True,
        )
    # Create initial commit so we have a main branch
    (tmp_path / "README.md").write_text("test")
    subprocess.run(["git", "add", "README.md"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "--no-gpg-sign", "-m", "init"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    # Ensure we're on main
    subprocess.run(
        ["git", "branch", "-M", "main"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    return tmp_path


class TestResolveMainRepo:
    def test_from_main_repo(self, git_repo: Path) -> None:
        result = worktree.resolve_main_repo(str(git_repo))
        assert result == git_repo

    def test_from_worktree(self, git_repo: Path) -> None:
        wt_path = git_repo / ".git-worktrees" / "test-wt"
        wt_path.parent.mkdir(parents=True)
        subprocess.run(
            ["git", "branch", "test-branch", "main"],
            cwd=str(git_repo),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "worktree", "add", str(wt_path), "test-branch"],
            cwd=str(git_repo),
            check=True,
            capture_output=True,
        )
        result = worktree.resolve_main_repo(str(wt_path))
        assert result == git_repo


class TestWorktreePath:
    def test_without_prefix(self, tmp_path: Path) -> None:
        result = worktree.worktree_path(tmp_path, "my-feature")
        assert result == tmp_path / ".git-worktrees" / "my-feature"

    def test_with_prefix(self, tmp_path: Path) -> None:
        result = worktree.worktree_path(tmp_path, "2026-02-24", prefix="fix-scrub")
        assert result == tmp_path / ".git-worktrees" / "fix-scrub" / "2026-02-24"


class TestWorktreePathWithAgentId:
    def test_with_agent_id(self, tmp_path: Path) -> None:
        result = worktree_path(tmp_path, "change", agent_id="w1")
        assert result == tmp_path / ".git-worktrees" / "change" / "w1"

    def test_with_agent_id_and_prefix(self, tmp_path: Path) -> None:
        result = worktree_path(tmp_path, "change", agent_id="w1", prefix="fix")
        assert result == tmp_path / ".git-worktrees" / "fix" / "change" / "w1"

    def test_without_agent_id_backward_compat(self, tmp_path: Path) -> None:
        result = worktree_path(tmp_path, "change")
        assert result == tmp_path / ".git-worktrees" / "change"


class TestWorktreePathSibling:
    """sibling=True places the agent worktree as a peer of <change-id>
    instead of nested inside it. Used by cleanup-feature to avoid leaving
    `cleanup/` as an untracked directory in the implementation worktree.
    """

    def test_sibling_places_agent_next_to_change_dir(self, tmp_path: Path) -> None:
        result = worktree_path(
            tmp_path,
            "feat",
            agent_id="cleanup",
            sibling=True,
        )
        assert result == tmp_path / ".git-worktrees" / "feat--cleanup"

    def test_sibling_with_prefix(self, tmp_path: Path) -> None:
        result = worktree_path(
            tmp_path,
            "feat",
            agent_id="cleanup",
            prefix="fix",
            sibling=True,
        )
        assert result == tmp_path / ".git-worktrees" / "fix" / "feat--cleanup"

    def test_sibling_without_agent_is_noop(self, tmp_path: Path) -> None:
        # Nothing to "place beside" — fall back to default change-id path
        result = worktree_path(tmp_path, "feat", sibling=True)
        assert result == tmp_path / ".git-worktrees" / "feat"

    def test_sibling_path_is_not_inside_change_dir(self, tmp_path: Path) -> None:
        """Regression: the whole point of --sibling is that the cleanup
        worktree must not be a path-descendant of the impl worktree. A nested
        layout polluted the impl's `git status` with an untracked
        cleanup/ subdirectory and forced --force on teardown."""
        impl = worktree_path(tmp_path, "feat")
        cleanup = worktree_path(
            tmp_path,
            "feat",
            agent_id="cleanup",
            sibling=True,
        )
        # The cleanup path must NOT be inside the impl path
        assert impl not in cleanup.parents
        # Both must share the .git-worktrees parent
        assert impl.parent == cleanup.parent


class TestDefaultBranch:
    def test_basic(self) -> None:
        assert default_branch("change") == "openspec/change"

    def test_with_agent_id(self) -> None:
        assert default_branch("change", agent_id="w1") == "openspec/change--w1"

    def test_with_prefix(self) -> None:
        assert default_branch("change", prefix="fix") == "fix/change"

    def test_with_agent_id_and_prefix(self) -> None:
        assert default_branch("change", agent_id="w1", prefix="fix") == "fix/change--w1"


class TestResolveBranch:
    """Branch resolution precedence: explicit > env override > default,
    with agent-id suffix composition for parallel disambiguation."""

    def test_no_override_returns_default(self) -> None:
        assert resolve_branch("change", env={}) == "openspec/change"

    def test_explicit_wins_over_env_and_is_verbatim(self) -> None:
        """Explicit --branch is used verbatim; agent-id suffix is NOT applied.

        Lets callers that pre-compose fully-qualified task branches pass them
        through via --branch without further transformation.
        """
        env = {"OPENSPEC_BRANCH_OVERRIDE": "operator/branch"}
        assert resolve_branch("change", explicit="explicit/branch", env=env) == "explicit/branch"
        # Even with agent_id, explicit stays verbatim
        assert (
            resolve_branch("change", agent_id="w1", explicit="explicit/branch", env=env)
            == "explicit/branch"
        )

    def test_env_override_used_when_no_explicit(self) -> None:
        env = {"OPENSPEC_BRANCH_OVERRIDE": "claude/fix-branch-mismatch-9P9o1"}
        assert resolve_branch("change", env=env) == "claude/fix-branch-mismatch-9P9o1"

    def test_empty_env_override_falls_through_to_default(self) -> None:
        env = {"OPENSPEC_BRANCH_OVERRIDE": ""}
        assert resolve_branch("change", env=env) == "openspec/change"

    def test_whitespace_env_override_falls_through_to_default(self) -> None:
        env = {"OPENSPEC_BRANCH_OVERRIDE": "   "}
        assert resolve_branch("change", env=env) == "openspec/change"

    def test_empty_explicit_falls_through_to_env(self) -> None:
        env = {"OPENSPEC_BRANCH_OVERRIDE": "operator/branch"}
        assert resolve_branch("change", explicit="", env=env) == "operator/branch"

    def test_env_override_composes_with_agent_id(self) -> None:
        """Regression: parallel work-package agents MUST get disambiguated branches.

        Without this composition, wp-backend, wp-frontend, wp-integration would
        all land on the same branch and clobber each other's commits during
        parallel execution. The agent suffix is what keeps them isolated until
        merge_worktrees.py integrates them.
        """
        env = {"OPENSPEC_BRANCH_OVERRIDE": "claude/fix-branch-mismatch-9P9o1"}
        assert resolve_branch("change", env=env) == "claude/fix-branch-mismatch-9P9o1"
        assert (
            resolve_branch("change", agent_id="wp-backend", env=env)
            == "claude/fix-branch-mismatch-9P9o1--wp-backend"
        )
        assert (
            resolve_branch("change", agent_id="wp-frontend", env=env)
            == "claude/fix-branch-mismatch-9P9o1--wp-frontend"
        )
        assert (
            resolve_branch("change", agent_id="cleanup", env=env)
            == "claude/fix-branch-mismatch-9P9o1--cleanup"
        )

    def test_env_override_with_prefix_ignores_prefix(self) -> None:
        """When env override is set, it replaces prefix — they don't compose."""
        env = {"OPENSPEC_BRANCH_OVERRIDE": "claude/fixit"}
        assert resolve_branch("change", prefix="fix", env=env) == "claude/fixit"
        assert resolve_branch("change", agent_id="w1", prefix="fix", env=env) == "claude/fixit--w1"

    def test_default_path_still_composes_with_agent_id(self) -> None:
        """Baseline: without env override, resolve_branch matches default_branch exactly."""
        assert resolve_branch("change", env={}) == default_branch("change")
        assert resolve_branch("change", agent_id="w1", env={}) == default_branch(
            "change", agent_id="w1"
        )
        assert resolve_branch("change", prefix="fix", env={}) == default_branch(
            "change", prefix="fix"
        )
        assert resolve_branch("change", agent_id="w1", prefix="fix", env={}) == default_branch(
            "change", agent_id="w1", prefix="fix"
        )


class TestResolveParentBranch:
    """resolve_parent_branch strips any agent suffix to return the integration target."""

    def test_default_parent(self) -> None:
        from worktree import resolve_parent_branch

        assert resolve_parent_branch("change", env={}) == "openspec/change"

    def test_env_override_parent(self) -> None:
        from worktree import resolve_parent_branch

        env = {"OPENSPEC_BRANCH_OVERRIDE": "claude/fix-branch-mismatch-9P9o1"}
        assert resolve_parent_branch("change", env=env) == "claude/fix-branch-mismatch-9P9o1"

    def test_parent_ignores_any_caller_agent_id_context(self) -> None:
        """resolve_parent_branch never takes agent_id — it's the integration target."""
        from worktree import resolve_parent_branch

        env = {"OPENSPEC_BRANCH_OVERRIDE": "claude/op"}
        # Caller didn't even get to pass agent_id — the function intentionally
        # doesn't accept one, making it impossible to accidentally get a
        # sub-branch back from this call.
        assert resolve_parent_branch("change", env=env) == "claude/op"


class TestRegistry:
    def test_load_missing_file_returns_empty(self, tmp_path: Path) -> None:
        reg = load_registry(tmp_path)
        assert reg == {
            "schema_version": 2,
            "entries": [],
            "setup_reservations": [],
            "recovery_audit": [],
        }

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        reg = {
            "version": 1,
            "entries": [
                {
                    "change_id": "c1",
                    "agent_id": None,
                    "branch": "openspec/c1",
                    "worktree_path": "/tmp/wt",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "last_heartbeat": "2026-01-01T00:00:00+00:00",
                    "pinned": False,
                },
            ],
        }
        save_registry(tmp_path, reg)
        loaded = load_registry(tmp_path)
        assert loaded["schema_version"] == 2
        assert loaded["entries"][0]["entry_generation"].startswith("legacy-v1-entry:")
        assert loaded["entries"][0]["activity_lease"]["phase"] == "LEGACY"

    def test_find_entry_by_change_id_and_agent_id(self) -> None:
        reg = {
            "version": 1,
            "entries": [
                {"change_id": "c1", "agent_id": None},
                {"change_id": "c1", "agent_id": "w1"},
                {"change_id": "c2", "agent_id": None},
            ],
        }
        assert find_entry(reg, "c1", "w1") == {"change_id": "c1", "agent_id": "w1"}
        assert find_entry(reg, "c1") == {"change_id": "c1", "agent_id": None}
        assert find_entry(reg, "c3") is None

    def test_remove_entry_returns_true(self) -> None:
        reg = {
            "version": 1,
            "entries": [
                {"change_id": "c1", "agent_id": None},
                {"change_id": "c2", "agent_id": None},
            ],
        }
        assert remove_entry(reg, "c1") is True
        assert len(reg["entries"]) == 1
        assert reg["entries"][0]["change_id"] == "c2"

    def test_remove_entry_missing_returns_false(self) -> None:
        reg = {
            "version": 1,
            "entries": [
                {"change_id": "c1", "agent_id": None},
            ],
        }
        assert remove_entry(reg, "nonexistent") is False
        assert len(reg["entries"]) == 1


class TestCmdSetup:
    def test_creates_worktree(self, git_repo: Path) -> None:
        args = _make_args("setup", change_id="test-feature")
        with _chdir(git_repo):
            result = worktree.cmd_setup(args)
        assert result == 0
        wt_path = git_repo / ".git-worktrees" / "test-feature"
        assert wt_path.is_dir()
        # Check branch was created
        branches = subprocess.run(
            ["git", "branch", "--list", "openspec/test-feature"],
            cwd=str(git_repo),
            capture_output=True,
            text=True,
        )
        assert "openspec/test-feature" in branches.stdout

    def test_creates_worktree_with_prefix(self, git_repo: Path) -> None:
        args = _make_args(
            "setup", change_id="2026-02-24", prefix="fix-scrub", branch="fix-scrub/2026-02-24"
        )
        with _chdir(git_repo):
            result = worktree.cmd_setup(args)
        assert result == 0
        wt_path = git_repo / ".git-worktrees" / "fix-scrub" / "2026-02-24"
        assert wt_path.is_dir()

    def test_idempotent_rerun(self, git_repo: Path) -> None:
        args = _make_args("setup", change_id="test-feature")
        with _chdir(git_repo):
            worktree.cmd_setup(args)
            # Second run should not fail
            result = worktree.cmd_setup(args)
        assert result == 0

    def test_custom_branch(self, git_repo: Path) -> None:
        args = _make_args("setup", change_id="test-feature", branch="custom/branch")
        with _chdir(git_repo):
            result = worktree.cmd_setup(args)
        assert result == 0
        branches = subprocess.run(
            ["git", "branch", "--list", "custom/branch"],
            cwd=str(git_repo),
            capture_output=True,
            text=True,
        )
        assert "custom/branch" in branches.stdout

    def test_env_override_creates_operator_branch(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: operator-mandated branch via OPENSPEC_BRANCH_OVERRIDE.

        Simulates the Claude cloud harness injecting a branch name the skill
        must honor instead of its default openspec/<change-id>.
        """
        monkeypatch.setenv("OPENSPEC_BRANCH_OVERRIDE", "claude/fix-branch-mismatch-9P9o1")
        args = _make_args("setup", change_id="test-feature")
        with _chdir(git_repo):
            result = worktree.cmd_setup(args)
        assert result == 0

        # The operator branch should exist
        branches = subprocess.run(
            ["git", "branch", "--list", "claude/fix-branch-mismatch-9P9o1"],
            cwd=str(git_repo),
            capture_output=True,
            text=True,
        )
        assert "claude/fix-branch-mismatch-9P9o1" in branches.stdout

        # The openspec/ default branch should NOT have been created
        default_branches = subprocess.run(
            ["git", "branch", "--list", "openspec/test-feature"],
            cwd=str(git_repo),
            capture_output=True,
            text=True,
        )
        assert default_branches.stdout.strip() == ""

        # Registry should record the override branch
        reg = load_registry(git_repo)
        entry = find_entry(reg, "test-feature")
        assert entry is not None
        assert entry["branch"] == "claude/fix-branch-mismatch-9P9o1"

    def test_env_override_composes_with_agent_id(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: parallel work-package agents must get disambiguated branches.

        When OPENSPEC_BRANCH_OVERRIDE + --agent-id are both set, the resolved
        branch is <override>--<agent-id>, not <override> verbatim. This keeps
        parallel packages from clobbering each other.
        """
        monkeypatch.setenv("OPENSPEC_BRANCH_OVERRIDE", "claude/op-session-9P9o1")

        for agent_id in ["wp-backend", "wp-frontend", "wp-integration"]:
            args = _make_args("setup", change_id="feat", agent_id=agent_id)
            with _chdir(git_repo):
                result = worktree.cmd_setup(args)
            assert result == 0

            expected_branch = f"claude/op-session-9P9o1--{agent_id}"
            branches = subprocess.run(
                ["git", "branch", "--list", expected_branch],
                cwd=str(git_repo),
                capture_output=True,
                text=True,
            )
            assert expected_branch in branches.stdout, f"missing branch for {agent_id}"

            reg = load_registry(git_repo)
            entry = find_entry(reg, "feat", agent_id)
            assert entry is not None
            assert entry["branch"] == expected_branch

        # And the parent (no agent_id) branch should be separate and creatable
        args = _make_args("setup", change_id="feat")
        with _chdir(git_repo):
            worktree.cmd_setup(args)
        reg = load_registry(git_repo)
        parent_entry = find_entry(reg, "feat")
        assert parent_entry is not None
        assert parent_entry["branch"] == "claude/op-session-9P9o1"

    def test_agent_branch_starts_from_existing_parent_branch(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: agent branches must start from the feature branch.

        If the agent branch is created from main instead, merging it back into
        the feature branch can pull unrelated main-only commits into the PR.
        """
        _commit_file(git_repo, "feature-only.txt", "feature\n", branch="claude/feature")
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=str(git_repo),
            check=True,
            capture_output=True,
        )
        _commit_file(git_repo, "main-only.txt", "main\n")

        monkeypatch.setenv("OPENSPEC_BRANCH_OVERRIDE", "claude/feature")
        args = _make_args("setup", change_id="feat", agent_id="wp-backend")
        with _chdir(git_repo):
            result = worktree.cmd_setup(args)
        assert result == 0

        wt_path = git_repo / ".git-worktrees" / "feat--wp-backend"
        assert (wt_path / "feature-only.txt").is_file()
        assert not (wt_path / "main-only.txt").exists()

    def test_agent_branch_starts_from_current_feature_branch_when_parent_ref_absent(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: when the named parent feature branch does not exist as a
        ref, the agent branch must start from the feature branch the operator is
        on (the invoking checkout's HEAD), NOT from main.

        Coordinated workflow: setup runs from the feature-branch worktree. With
        no OPENSPEC_BRANCH_OVERRIDE, resolve_parent_branch computes
        'openspec/<change-id>', which may not exist as a ref (the operator's
        branch has a different name). The helper previously fabricated that
        parent from main, giving every agent branch a stale base so merging it
        back dragged main-only commits into the feature PR. It must instead base
        the parent on the current feature-branch HEAD.
        """
        # Operator's feature branch (name differs from openspec/<id>); stay on it.
        _commit_file(git_repo, "feature-only.txt", "feature\n", branch="feature-work")
        # main diverges with a commit that must NOT leak into the agent branch.
        subprocess.run(
            ["git", "checkout", "main"], cwd=str(git_repo), check=True, capture_output=True
        )
        _commit_file(git_repo, "main-only.txt", "main\n")
        # Return to the feature branch — this is the invoking checkout state.
        subprocess.run(
            ["git", "checkout", "feature-work"], cwd=str(git_repo), check=True, capture_output=True
        )

        # No override: parent 'openspec/feat' will not resolve as a ref.
        monkeypatch.delenv("OPENSPEC_BRANCH_OVERRIDE", raising=False)
        args = _make_args("setup", change_id="feat", agent_id="wp-backend")
        with _chdir(git_repo):
            result = worktree.cmd_setup(args)
        assert result == 0

        wt_path = git_repo / ".git-worktrees" / "feat--wp-backend"
        assert (wt_path / "feature-only.txt").is_file(), (
            "agent branch must start from the current feature branch HEAD"
        )
        assert not (wt_path / "main-only.txt").exists(), (
            "agent branch must NOT be fabricated from main (stale base)"
        )

    def test_explicit_branch_wins_over_env_override(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--branch flag must take precedence over OPENSPEC_BRANCH_OVERRIDE."""
        monkeypatch.setenv("OPENSPEC_BRANCH_OVERRIDE", "from-env")
        args = _make_args("setup", change_id="test-feature", branch="from-flag")
        with _chdir(git_repo):
            result = worktree.cmd_setup(args)
        assert result == 0

        branches = subprocess.run(
            ["git", "branch", "--list", "from-flag"],
            cwd=str(git_repo),
            capture_output=True,
            text=True,
        )
        assert "from-flag" in branches.stdout

    def test_setup_emits_branch_in_stdout(
        self, git_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Callers shell-eval the stdout; they need WORKTREE_BRANCH to pass it on."""
        args = _make_args("setup", change_id="test-feature")
        with _chdir(git_repo):
            worktree.cmd_setup(args)
        captured = capsys.readouterr()
        assert "WORKTREE_BRANCH=openspec/test-feature" in captured.out

    def test_output_contains_worktree_path(
        self, git_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        args = _make_args("setup", change_id="test-feature")
        with _chdir(git_repo):
            worktree.cmd_setup(args)
        captured = capsys.readouterr()
        expected = str(git_repo / ".git-worktrees" / "test-feature")
        assert f"WORKTREE_PATH={expected}" in captured.out


class TestCmdResolveBranch:
    """resolve-branch subcommand — used by iterate/validate to discover the branch."""

    def test_prefers_registry_over_env(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """When a registry entry exists, it wins over env override.

        This matters when plan-feature was run with one override and implement
        is later run with a different (or missing) env var — the registry is the
        source of truth for what was actually used.
        """
        # Setup with an explicit operator branch
        monkeypatch.setenv("OPENSPEC_BRANCH_OVERRIDE", "operator/original")
        setup_args = _make_args("setup", change_id="regtest")
        with _chdir(git_repo):
            worktree.cmd_setup(setup_args)

        # Clear the env var and change it to something else — registry should still win
        monkeypatch.setenv("OPENSPEC_BRANCH_OVERRIDE", "something/different")
        capsys.readouterr()  # clear

        resolve_args = _make_args("resolve-branch", change_id="regtest")
        with _chdir(git_repo):
            result = worktree.cmd_resolve_branch(resolve_args)
        assert result == 0
        captured = capsys.readouterr()
        assert "BRANCH=operator/original" in captured.out
        assert "BRANCH_SOURCE=registry" in captured.out

    def test_falls_back_to_env_when_no_registry(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("OPENSPEC_BRANCH_OVERRIDE", "operator/fallback")
        resolve_args = _make_args("resolve-branch", change_id="no-reg")
        with _chdir(git_repo):
            result = worktree.cmd_resolve_branch(resolve_args)
        assert result == 0
        captured = capsys.readouterr()
        assert "BRANCH=operator/fallback" in captured.out
        assert "BRANCH_SOURCE=env" in captured.out

    def test_falls_back_to_default_when_no_registry_no_env(
        self, git_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        resolve_args = _make_args("resolve-branch", change_id="no-reg-no-env")
        with _chdir(git_repo):
            result = worktree.cmd_resolve_branch(resolve_args)
        assert result == 0
        captured = capsys.readouterr()
        assert "BRANCH=openspec/no-reg-no-env" in captured.out
        assert "BRANCH_SOURCE=default" in captured.out

    def test_explicit_branch_flag_wins(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("OPENSPEC_BRANCH_OVERRIDE", "from-env")
        resolve_args = _make_args("resolve-branch", change_id="x", branch="from-flag")
        with _chdir(git_repo):
            result = worktree.cmd_resolve_branch(resolve_args)
        assert result == 0
        captured = capsys.readouterr()
        assert "BRANCH=from-flag" in captured.out
        assert "BRANCH_SOURCE=explicit" in captured.out

    def test_parent_strips_agent_id_from_registry(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--parent returns the feature branch, not the agent sub-branch.

        Used by cleanup-feature: its own worktree is on <feature>--cleanup, but
        gh pr merge / git branch -d need to target <feature>.
        """
        monkeypatch.setenv("OPENSPEC_BRANCH_OVERRIDE", "claude/op-9P9o1")
        # Setup both the parent and the cleanup agent worktrees
        with _chdir(git_repo):
            worktree.cmd_setup(_make_args("setup", change_id="feat"))
            worktree.cmd_setup(_make_args("setup", change_id="feat", agent_id="cleanup"))

        capsys.readouterr()  # clear

        # Without --parent, asking for the cleanup agent returns its sub-branch
        resolve_args = _make_args("resolve-branch", change_id="feat", agent_id="cleanup")
        with _chdir(git_repo):
            worktree.cmd_resolve_branch(resolve_args)
        captured = capsys.readouterr()
        assert "BRANCH=claude/op-9P9o1--cleanup" in captured.out

        # With --parent, asking for the same thing returns the feature branch
        resolve_args = _make_args(
            "resolve-branch", change_id="feat", agent_id="cleanup", parent=True
        )
        with _chdir(git_repo):
            worktree.cmd_resolve_branch(resolve_args)
        captured = capsys.readouterr()
        assert "BRANCH=claude/op-9P9o1" in captured.out
        assert "BRANCH=claude/op-9P9o1--cleanup" not in captured.out


class TestCmdTeardown:
    def test_removes_worktree(self, git_repo: Path) -> None:
        # Setup first
        setup_args = _make_args("setup", change_id="test-feature")
        with _chdir(git_repo):
            worktree.cmd_setup(setup_args)
        wt_path = git_repo / ".git-worktrees" / "test-feature"
        assert wt_path.is_dir()

        # Teardown
        teardown_args = _make_args("teardown", change_id="test-feature")
        with _chdir(git_repo):
            result = worktree.cmd_teardown(teardown_args)
        assert result == 0
        assert not wt_path.is_dir()

    def test_not_found_returns_error(self, git_repo: Path) -> None:
        teardown_args = _make_args("teardown", change_id="nonexistent")
        with _chdir(git_repo):
            result = worktree.cmd_teardown(teardown_args)
        assert result == 1

    def test_sibling_setup_and_teardown_roundtrip(self, git_repo: Path) -> None:
        """The cleanup-feature flow: --sibling setup and --sibling teardown
        place and remove the worktree at <change>--<agent>/, never inside
        the parent <change>/ dir."""
        impl = git_repo / ".git-worktrees" / "feat"
        sibling_path = git_repo / ".git-worktrees" / "feat--cleanup"

        with _chdir(git_repo):
            # Both worktrees exist independently
            worktree.cmd_setup(_make_args("setup", change_id="feat"))
            worktree.cmd_setup(
                _make_args(
                    "setup",
                    change_id="feat",
                    agent_id="cleanup",
                    sibling=True,
                )
            )

        assert impl.is_dir()
        assert sibling_path.is_dir()
        # Critical: sibling cleanup is NOT inside the impl worktree
        assert sibling_path.parent == impl.parent

        # Tear down only the cleanup; impl untouched
        with _chdir(git_repo):
            result = worktree.cmd_teardown(
                _make_args(
                    "teardown",
                    change_id="feat",
                    agent_id="cleanup",
                    sibling=True,
                )
            )
        assert result == 0
        assert not sibling_path.is_dir()
        assert impl.is_dir()  # impl survives

    def test_agent_setup_never_nests_inside_feature_checkout(self, git_repo: Path) -> None:
        """Managed agent worktrees cannot pollute the parent feature checkout."""
        nested_path = git_repo / ".git-worktrees" / "feat" / "cleanup"
        sibling_path = git_repo / ".git-worktrees" / "feat--cleanup"

        with _chdir(git_repo):
            worktree.cmd_setup(
                _make_args(
                    "setup",
                    change_id="feat",
                    agent_id="cleanup",
                )
            )
        assert sibling_path.is_dir()
        assert not nested_path.exists()

        with _chdir(git_repo):
            result = worktree.cmd_teardown(
                _make_args(
                    "teardown",
                    change_id="feat",
                    agent_id="cleanup",
                    sibling=True,
                )
            )
        assert result == 0
        assert not sibling_path.is_dir()


class TestCmdStatus:
    def test_specific_worktree_exists(
        self, git_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        setup_args = _make_args("setup", change_id="test-feature")
        with _chdir(git_repo):
            worktree.cmd_setup(setup_args)

        status_args = _make_args("status", change_id="test-feature")
        with _chdir(git_repo):
            result = worktree.cmd_status(status_args)
        assert result == 0
        captured = capsys.readouterr()
        assert "EXISTS=true" in captured.out

    def test_specific_worktree_not_found(
        self, git_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        status_args = _make_args("status", change_id="nonexistent")
        with _chdir(git_repo):
            result = worktree.cmd_status(status_args)
        assert result == 1
        captured = capsys.readouterr()
        assert "EXISTS=false" in captured.out

    def test_list_all(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        status_args = _make_args("status", change_id=None)
        with _chdir(git_repo):
            result = worktree.cmd_status(status_args)
        assert result == 0
        captured = capsys.readouterr()
        assert str(git_repo) in captured.out


class TestCmdDetect:
    def test_from_main_repo(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        detect_args = _make_args("detect")
        with _chdir(git_repo):
            result = worktree.cmd_detect(detect_args)
        assert result == 0
        captured = capsys.readouterr()
        assert "IN_WORKTREE=false" in captured.out
        assert f"MAIN_REPO={git_repo}" in captured.out
        assert "OPENSPEC_PATH=openspec" in captured.out

    def test_from_worktree(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        setup_args = _make_args("setup", change_id="test-feature")
        with _chdir(git_repo):
            worktree.cmd_setup(setup_args)

        wt_path = git_repo / ".git-worktrees" / "test-feature"
        detect_args = _make_args("detect")
        with _chdir(wt_path):
            capsys.readouterr()  # Clear previous output
            result = worktree.cmd_detect(detect_args)
        assert result == 0
        captured = capsys.readouterr()
        assert "IN_WORKTREE=true" in captured.out
        assert f"MAIN_REPO={git_repo}" in captured.out
        assert f"OPENSPEC_PATH={git_repo}/openspec" in captured.out


class TestCmdHeartbeat:
    def test_heartbeat_updates_timestamp(self, git_repo: Path) -> None:
        # Setup a worktree first to populate registry
        setup_args = _make_args("setup", change_id="hb-test")
        with _chdir(git_repo):
            worktree.cmd_setup(setup_args)

        # Read initial heartbeat
        reg_before = load_registry(git_repo)
        entry_before = find_entry(reg_before, "hb-test")
        assert entry_before is not None
        ts_before = entry_before["last_heartbeat"]

        # Call heartbeat
        hb_args = _make_args("heartbeat", change_id="hb-test")
        with _chdir(git_repo):
            result = cmd_heartbeat(hb_args)
        assert result == 0

        # Verify timestamp updated
        reg_after = load_registry(git_repo)
        entry_after = find_entry(reg_after, "hb-test")
        assert entry_after is not None
        assert entry_after["last_heartbeat"] >= ts_before

    def test_heartbeat_unknown_returns_1(self, git_repo: Path) -> None:
        hb_args = _make_args("heartbeat", change_id="nonexistent")
        with _chdir(git_repo):
            result = cmd_heartbeat(hb_args)
        assert result == 1


class TestCmdPinUnpin:
    def test_pin_sets_pinned_true(self, git_repo: Path) -> None:
        setup_args = _make_args("setup", change_id="pin-test")
        with _chdir(git_repo):
            worktree.cmd_setup(setup_args)

        pin_args = _make_args("pin", change_id="pin-test")
        with _chdir(git_repo):
            result = cmd_pin(pin_args)
        assert result == 0

        reg = load_registry(git_repo)
        entry = find_entry(reg, "pin-test")
        assert entry is not None
        assert entry["retained"] is True

    def test_unpin_sets_pinned_false(self, git_repo: Path) -> None:
        setup_args = _make_args("setup", change_id="unpin-test")
        with _chdir(git_repo):
            worktree.cmd_setup(setup_args)

        # Pin first
        pin_args = _make_args("pin", change_id="unpin-test")
        with _chdir(git_repo):
            cmd_pin(pin_args)

        # Unpin
        unpin_args = _make_args("unpin", change_id="unpin-test")
        with _chdir(git_repo):
            result = cmd_unpin(unpin_args)
        assert result == 0

        reg = load_registry(git_repo)
        entry = find_entry(reg, "unpin-test")
        assert entry is not None
        assert entry["retained"] is False

    def test_pin_unknown_returns_1(self, git_repo: Path) -> None:
        pin_args = _make_args("pin", change_id="nonexistent")
        with _chdir(git_repo):
            result = cmd_pin(pin_args)
        assert result == 1


class TestCmdList:
    def test_list_with_entries(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        setup_args = _make_args("setup", change_id="list-test")
        with _chdir(git_repo):
            worktree.cmd_setup(setup_args)

        capsys.readouterr()  # Clear
        list_args = _make_args("list")
        with _chdir(git_repo):
            result = cmd_list(list_args)
        assert result == 0
        captured = capsys.readouterr()
        assert "CHANGE_ID" in captured.out  # Header
        assert "list-test" in captured.out

    def test_list_no_entries(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        list_args = _make_args("list")
        with _chdir(git_repo):
            result = cmd_list(list_args)
        assert result == 0
        captured = capsys.readouterr()
        assert "No active worktrees" in captured.out


class TestCmdGc:
    def test_gc_removes_stale(self, git_repo: Path) -> None:
        # Setup a worktree
        setup_args = _make_args("setup", change_id="gc-stale")
        with _chdir(git_repo):
            worktree.cmd_setup(setup_args)

        # Manually set heartbeat to 25 hours ago
        reg = load_registry(git_repo)
        entry = find_entry(reg, "gc-stale")
        assert entry is not None
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        entry["last_heartbeat"] = old_ts
        save_registry(git_repo, reg)

        # Run GC with default 24h threshold
        gc_args = _make_args("gc", stale_after="24h", force=False)
        with _chdir(git_repo):
            result = cmd_gc(gc_args)
        assert result == 0

        # Verify removed
        reg_after = load_registry(git_repo)
        assert find_entry(reg_after, "gc-stale") is None

    def test_gc_preserves_active(self, git_repo: Path) -> None:
        # Setup a worktree (fresh heartbeat = active)
        setup_args = _make_args("setup", change_id="gc-active")
        with _chdir(git_repo):
            worktree.cmd_setup(setup_args)

        gc_args = _make_args("gc", stale_after="24h", force=False)
        with _chdir(git_repo):
            result = cmd_gc(gc_args)
        assert result == 0

        # Verify preserved
        reg = load_registry(git_repo)
        assert find_entry(reg, "gc-active") is not None

    def test_gc_preserves_pinned(self, git_repo: Path) -> None:
        # Setup and pin
        setup_args = _make_args("setup", change_id="gc-pinned")
        with _chdir(git_repo):
            worktree.cmd_setup(setup_args)

        pin_args = _make_args("pin", change_id="gc-pinned")
        with _chdir(git_repo):
            cmd_pin(pin_args)

        # Make it stale
        reg = load_registry(git_repo)
        entry = find_entry(reg, "gc-pinned")
        assert entry is not None
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        entry["last_heartbeat"] = old_ts
        save_registry(git_repo, reg)

        # GC without force should preserve pinned
        gc_args = _make_args("gc", stale_after="24h", force=False)
        with _chdir(git_repo):
            cmd_gc(gc_args)

        reg_after = load_registry(git_repo)
        assert find_entry(reg_after, "gc-pinned") is not None

    def test_gc_force_removes_pinned(self, git_repo: Path) -> None:
        # Setup and pin
        setup_args = _make_args("setup", change_id="gc-force")
        with _chdir(git_repo):
            worktree.cmd_setup(setup_args)

        pin_args = _make_args("pin", change_id="gc-force")
        with _chdir(git_repo):
            cmd_pin(pin_args)

        # Make it stale
        reg = load_registry(git_repo)
        entry = find_entry(reg, "gc-force")
        assert entry is not None
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        entry["last_heartbeat"] = old_ts
        save_registry(git_repo, reg)

        # GC with force should remove pinned
        gc_args = _make_args("gc", stale_after="24h", force=True)
        with _chdir(git_repo):
            cmd_gc(gc_args)

        reg_after = load_registry(git_repo)
        assert find_entry(reg_after, "gc-force") is None

    def test_gc_never_removes_automatic_or_recovery_entries(self, git_repo: Path) -> None:
        for change_id in ("automatic", "recovery"):
            with _chdir(git_repo):
                worktree.cmd_setup(_make_args("setup", change_id=change_id))
            registry = load_registry(git_repo)
            entry = find_entry(registry, change_id)
            assert entry is not None
            entry["last_heartbeat"] = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            if change_id == "automatic":
                entry["setup_id"] = "completed-setup"
            else:
                entry["recovery_required"] = True
                entry["recovery_reason"] = "preserved"
                entry["recovery_context"] = {
                    "source": "setup-failure",
                    "prior_owner": None,
                    "prior_lease_id": None,
                    "prior_controller_instance_id": None,
                    "process_evidence_key": None,
                    "quarantined_at": datetime.now(timezone.utc).isoformat(),
                }
            save_registry(git_repo, registry)

        with _chdir(git_repo):
            assert cmd_gc(_make_args("gc", stale_after="1h", force=True)) == 0

        registry = load_registry(git_repo)
        assert find_entry(registry, "automatic") is not None
        assert find_entry(registry, "recovery") is not None


class TestRecoveryCommands:
    def _reservation(self, git_repo: Path) -> dict[str, object]:
        target = {
            "remote_name": "origin",
            "remote_url_hash_algorithm": "git-remote-url-v1",
            "canonical_remote_url_sha256": "a" * 64,
            "ref_name": "refs/remotes/origin/openspec/recovery",
        }
        intent = {
            "owner": "owner",
            "lease_id": "lease",
            "controller_instance_id": "controller",
            "session_id": None,
            "phase": "IMPLEMENT",
            "reason": "test",
            "lifecycle_mode": "standalone",
            "ttl_seconds": 1800,
        }
        return worktree.lifecycle.reserve_setup(
            git_repo,
            setup_id="setup",
            change_id="recovery",
            agent_id=None,
            branch="openspec/recovery",
            worktree_path=str(git_repo / "missing"),
            entry_generation="generation",
            durability_target=target,
            lease_intent=intent,
            now=datetime.now(timezone.utc) - timedelta(hours=2),
            ttl_seconds=1800,
        )

    def test_expired_side_effect_free_setup_reconciliation_is_audited(
        self,
        git_repo: Path,
    ) -> None:
        self._reservation(git_repo)
        args = argparse.Namespace(
            setup_id="setup",
            entry_generation="generation",
            actor="operator",
            reason="controller terminated",
            confirm_terminated=True,
            json_output=True,
            agent_id=None,
        )
        with _chdir(git_repo):
            assert worktree.cmd_setup_reconcile(args) == 0
        registry = load_registry(git_repo)
        assert registry["setup_reservations"] == []
        assert registry["entries"] == []
        assert registry["recovery_audit"][0]["event"] == "setup-reconciled"
        assert registry["recovery_audit"][0]["outcome"] == "removed-empty-side-effects"

    def test_force_teardown_of_missing_quarantine_preserves_audit(
        self,
        git_repo: Path,
    ) -> None:
        entry = {
            "change_id": "recovery",
            "agent_id": None,
            "branch": "openspec/recovery",
            "worktree_path": str(git_repo / "missing"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "entry_generation": "generation",
            "setup_id": None,
            "durability_target": None,
            "retained": False,
            "retention_reason": None,
            "recovery_required": True,
            "recovery_reason": "legacy work",
            "recovery_context": {
                "source": "legacy-adoption",
                "prior_owner": None,
                "prior_lease_id": None,
                "prior_controller_instance_id": None,
                "process_evidence_key": None,
                "quarantined_at": datetime.now(timezone.utc).isoformat(),
            },
            "activity_lease": None,
        }
        save_registry(git_repo, worktree.lifecycle.empty_registry(entries=[entry]))
        args = argparse.Namespace(
            change_id="recovery",
            agent_id=None,
            entry_generation="generation",
            actor="operator",
            reason="discard legacy orphan",
            confirm_terminated=True,
            confirm_discard=True,
            force=True,
            owner=None,
            lease_id=None,
            controller_instance_id=None,
            json_output=True,
        )
        with _chdir(git_repo):
            assert worktree.cmd_recovery_teardown(args) == 0
        registry = load_registry(git_repo)
        assert registry["entries"] == []
        assert registry["recovery_audit"][0]["event"] == "recovery-torn-down"
        assert registry["recovery_audit"][0]["discard_confirmed"] is True

    @pytest.mark.parametrize("failure_boundary", ["token", "evidence"])
    def test_force_adopt_evidence_failure_preserves_quarantine_for_exact_retry(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        failure_boundary: str,
    ) -> None:
        entry = {
            "change_id": "recovery",
            "agent_id": None,
            "branch": "openspec/recovery",
            "worktree_path": str(git_repo / "missing"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "entry_generation": "generation",
            "setup_id": None,
            "durability_target": None,
            "retained": False,
            "retention_reason": None,
            "recovery_required": True,
            "recovery_reason": "legacy work",
            "recovery_context": {
                "source": "legacy-adoption",
                "prior_owner": None,
                "prior_lease_id": None,
                "prior_controller_instance_id": None,
                "process_evidence_key": None,
                "quarantined_at": datetime.now(timezone.utc).isoformat(),
            },
            "activity_lease": None,
        }
        save_registry(git_repo, worktree.lifecycle.empty_registry(entries=[entry]))
        args = argparse.Namespace(
            change_id="recovery",
            agent_id=None,
            owner="new-owner",
            lease_id="new-lease",
            controller_instance_id="new-controller",
            session_id="new-session",
            reason="operator adoption",
            actor="operator",
            ttl_seconds=1800,
            durability_remote=None,
            durability_ref=None,
            confirm_terminated=True,
            force=True,
            json_output=True,
        )
        if failure_boundary == "token":
            failure_owner = worktree.lifecycle
            failure_name = "_process_start_token"
        else:
            failure_owner = worktree.lifecycle.tempfile
            failure_name = "mkstemp"
        with monkeypatch.context() as patcher:
            patcher.setattr(
                failure_owner,
                failure_name,
                lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    worktree.lifecycle.LifecycleError("token unavailable")
                    if failure_boundary == "token"
                    else PermissionError("evidence prohibited")
                ),
            )
            with _chdir(git_repo), pytest.raises(worktree.lifecycle.LifecycleError):
                worktree.cmd_recovery_adopt(args)

        after_failure = load_registry(git_repo)
        preserved = find_entry(after_failure, "recovery")
        assert preserved is not None
        assert preserved["recovery_required"] is True
        assert preserved["activity_lease"] is None
        assert after_failure["recovery_audit"] == []

        monkeypatch.setattr(worktree.lifecycle, "_process_start_token", lambda _pid: "token")
        with _chdir(git_repo):
            assert worktree.cmd_recovery_adopt(args) == 0
        adopted = find_entry(load_registry(git_repo), "recovery")
        assert adopted is not None
        assert adopted["recovery_required"] is False
        assert adopted["activity_lease"]["lease_id"] == "new-lease"

    def test_force_adopt_discovers_process_token_before_exclusive_publication_lock(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        entry = {
            "change_id": "recovery",
            "agent_id": None,
            "branch": "openspec/recovery",
            "worktree_path": str(git_repo / "missing"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "entry_generation": "generation",
            "setup_id": None,
            "durability_target": None,
            "retained": False,
            "retention_reason": None,
            "recovery_required": True,
            "recovery_reason": "legacy work",
            "recovery_context": {
                "source": "legacy-adoption",
                "prior_owner": None,
                "prior_lease_id": None,
                "prior_controller_instance_id": None,
                "process_evidence_key": None,
                "quarantined_at": datetime.now(timezone.utc).isoformat(),
            },
            "activity_lease": None,
        }
        save_registry(git_repo, worktree.lifecycle.empty_registry(entries=[entry]))
        args = argparse.Namespace(
            change_id="recovery",
            agent_id=None,
            owner="new-owner",
            lease_id="new-lease",
            controller_instance_id="new-controller",
            session_id="new-session",
            reason="operator adoption",
            actor="operator",
            ttl_seconds=1800,
            durability_remote=None,
            durability_ref=None,
            confirm_terminated=True,
            force=True,
            json_output=True,
        )
        real_lock = worktree.lifecycle.registry_lock
        exclusive = False
        events: list[str] = []

        @contextlib.contextmanager
        def tracked_lock(*lock_args: object, **lock_kwargs: object):
            nonlocal exclusive
            with real_lock(*lock_args, **lock_kwargs):
                prior = exclusive
                exclusive = bool(lock_kwargs.get("exclusive"))
                if exclusive:
                    events.append("exclusive-enter")
                try:
                    yield
                finally:
                    exclusive = prior

        monkeypatch.setattr(worktree.lifecycle, "registry_lock", tracked_lock)

        def process_token(_pid: int) -> str:
            assert not exclusive
            events.append("process-token")
            return "precomputed-token"

        monkeypatch.setattr(worktree.lifecycle, "_process_start_token", process_token)
        real_subprocess_run = worktree.subprocess.run

        def guarded_subprocess(*run_args: object, **run_kwargs: object):
            assert not exclusive
            return real_subprocess_run(*run_args, **run_kwargs)

        monkeypatch.setattr(worktree.subprocess, "run", guarded_subprocess)
        with _chdir(git_repo):
            assert worktree.cmd_recovery_adopt(args) == 0
        assert events.count("process-token") == 1
        assert events.index("process-token") < events.index("exclusive-enter")
        evidence = worktree.lifecycle.read_process_evidence(
            git_repo,
            change_id="recovery",
            agent_id=None,
            entry_generation="generation",
            lease_id="new-lease",
            owner="new-owner",
            controller_instance_id="new-controller",
        )
        assert evidence["process_start_token"] == "precomputed-token"

    @pytest.mark.parametrize("same_lease", [True, False], ids=["same-lease", "distinct-lease"])
    def test_concurrent_force_adopt_winner_exclusively_owns_its_evidence(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        same_lease: bool,
    ) -> None:
        entry = {
            "change_id": "recovery",
            "agent_id": None,
            "branch": "openspec/recovery",
            "worktree_path": str(git_repo / "missing"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "entry_generation": "generation",
            "setup_id": None,
            "durability_target": None,
            "retained": False,
            "retention_reason": None,
            "recovery_required": True,
            "recovery_reason": "legacy work",
            "recovery_context": {
                "source": "legacy-adoption",
                "prior_owner": None,
                "prior_lease_id": None,
                "prior_controller_instance_id": None,
                "process_evidence_key": None,
                "quarantined_at": datetime.now(timezone.utc).isoformat(),
            },
            "activity_lease": None,
        }
        save_registry(git_repo, worktree.lifecycle.empty_registry(entries=[entry]))

        def adopt_args(owner: str, lease_id: str, controller: str) -> argparse.Namespace:
            return argparse.Namespace(
                change_id="recovery",
                agent_id=None,
                owner=owner,
                lease_id=lease_id,
                controller_instance_id=controller,
                session_id=f"session-{owner}",
                reason="operator adoption",
                actor="operator",
                ttl_seconds=1800,
                durability_remote=None,
                durability_ref=None,
                confirm_terminated=True,
                force=True,
                json_output=True,
            )

        args_a = adopt_args("owner-a", "shared-lease", "controller-a")
        args_b = adopt_args("owner-b", "shared-lease" if same_lease else "lease-b", "controller-b")
        monkeypatch.setattr(worktree.lifecycle, "_process_start_token", lambda _pid: "token")
        real_lock = worktree.lifecycle.registry_lock
        lock_state = threading.local()

        @contextlib.contextmanager
        def tracked_lock(*args: object, **kwargs: object):
            with real_lock(*args, **kwargs):
                prior = getattr(lock_state, "exclusive", False)
                lock_state.exclusive = bool(kwargs.get("exclusive"))
                try:
                    yield
                finally:
                    lock_state.exclusive = prior

        monkeypatch.setattr(worktree.lifecycle, "registry_lock", tracked_lock)
        real_write = worktree.lifecycle.write_process_evidence
        a_written = threading.Event()
        b_written = threading.Event()
        a_published = threading.Event()

        def ordered_write(*args: object, **kwargs: object):
            owner = str(kwargs["owner"])
            kwargs.setdefault("process_start_token", f"token-{owner}")
            result = real_write(*args, **kwargs)
            if owner == "owner-a":
                a_written.set()
                if not getattr(lock_state, "exclusive", False):
                    assert b_written.wait(5)
            elif not getattr(lock_state, "exclusive", False):
                b_written.set()
                assert a_published.wait(5)
            return result

        monkeypatch.setattr(worktree.lifecycle, "write_process_evidence", ordered_write)
        results: dict[str, object] = {}

        def run_adoption(name: str, args: argparse.Namespace) -> None:
            try:
                results[name] = worktree.cmd_recovery_adopt(args)
            except worktree.lifecycle.LifecycleError as exc:
                results[name] = exc
            finally:
                if name == "a":
                    a_published.set()

        thread_a = threading.Thread(target=run_adoption, args=("a", args_a))
        thread_b = threading.Thread(target=run_adoption, args=("b", args_b))
        with _chdir(git_repo):
            thread_a.start()
            assert a_written.wait(5)
            thread_b.start()
            thread_a.join(5)
            thread_b.join(5)
        assert not thread_a.is_alive()
        assert not thread_b.is_alive()
        assert results["a"] == 0
        assert isinstance(results["b"], worktree.lifecycle.LifecycleError)
        assert not b_written.is_set()

        registry = load_registry(git_repo)
        adopted = find_entry(registry, "recovery")
        assert adopted is not None
        assert adopted["activity_lease"]["owner"] == "owner-a"
        assert adopted["activity_lease"]["controller_instance_id"] == "controller-a"
        evidence = worktree.lifecycle.read_process_evidence(
            git_repo,
            change_id="recovery",
            agent_id=None,
            entry_generation="generation",
            lease_id="shared-lease",
            owner="owner-a",
            controller_instance_id="controller-a",
        )
        assert evidence["owner"] == "owner-a"
        assert evidence["controller_instance_id"] == "controller-a"
        if not same_lease:
            loser_evidence = worktree.lifecycle.evidence_path(
                git_repo, "recovery", None, "generation", "lease-b"
            )
            assert not loser_evidence.exists()


class TestParseDurationHours:
    def test_hours(self) -> None:
        assert parse_duration_hours("24h") == 24.0

    def test_days(self) -> None:
        assert parse_duration_hours("7d") == 168.0

    def test_minutes(self) -> None:
        assert parse_duration_hours("30m") == 0.5

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_duration_hours("abc")


# --- Helpers ---


class _chdir:
    """Context manager to temporarily change directory."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.prev: str | None = None

    def __enter__(self) -> None:
        self.prev = os.getcwd()
        os.chdir(self.path)

    def __exit__(self, *args: object) -> None:
        if self.prev:
            os.chdir(self.prev)


def _make_args(command: str, **kwargs: object) -> argparse.Namespace:
    """Create a mock argparse.Namespace for testing."""
    defaults = {
        "command": command,
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


def _commit_file(
    repo: Path,
    relative_path: str,
    content: str,
    branch: str | None = None,
) -> None:
    if branch is not None:
        subprocess.run(
            ["git", "checkout", "-B", branch],
            cwd=str(repo),
            check=True,
            capture_output=True,
        )
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    subprocess.run(["git", "add", relative_path], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "--no-gpg-sign", "-m", f"add {relative_path}"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

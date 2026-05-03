"""Integration tests for ``worktree.py setup --branch-prefix prototype``.

Spec scenarios covered:
- skill-workflow.PrototypeWorktreeSupport.branch-creation — actual git
  branch is created at ``prototype/<change-id>/v<n>``.
- skill-workflow.PrototypeWorktreeSupport.branch-override-composition —
  setup with both env override AND ``--branch-prefix prototype`` puts
  the variant on a prototype branch while leaving the parent feature
  branch governed by the env var.
- skill-workflow.PrototypeWorktreeSupport.worktree-pin — auto-pin
  registry entry; the GC cycle does NOT remove a pinned prototype
  worktree even when its heartbeat is older than the threshold.

Design decisions: D4 (branch retention through feature lifecycle).
"""

from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pytest

import worktree
from worktree import cmd_gc, cmd_setup, find_entry, load_registry, save_registry


def _make_setup_args(**kwargs: object) -> argparse.Namespace:
    """Build a setup-command Namespace with the new branch_prefix field.

    Mirrors ``_make_args`` from the in-tree test suite but includes
    ``branch_prefix=None`` in the defaults so tests don't need to remember it.
    """
    defaults: dict[str, object] = {
        "command": "setup",
        "change_id": None,
        "branch": None,
        "prefix": None,
        "branch_prefix": None,
        "no_bootstrap": True,
        "agent_id": None,
        "parent": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


@contextlib.contextmanager
def _chdir(path: Path) -> Iterator[None]:
    prev = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


class TestSetupCreatesPrototypeBranch:
    """``--branch-prefix prototype --agent-id v1`` lands on prototype/<change>/v1."""

    def test_branch_uses_slash_separator(self, git_repo: Path) -> None:
        args = _make_setup_args(
            change_id="add-foo", agent_id="v1", branch_prefix="prototype"
        )
        with _chdir(git_repo):
            assert cmd_setup(args) == 0

        branches = subprocess.run(
            ["git", "branch", "--list", "prototype/add-foo/v1"],
            cwd=str(git_repo),
            capture_output=True,
            text=True,
        )
        assert "prototype/add-foo/v1" in branches.stdout

    def test_does_not_create_dash_dash_branch(self, git_repo: Path) -> None:
        # Regression: if branch_prefix wasn't honored end-to-end, we'd see
        # the openspec/<change>--<agent> name fall through.
        args = _make_setup_args(
            change_id="add-foo", agent_id="v1", branch_prefix="prototype"
        )
        with _chdir(git_repo):
            cmd_setup(args)

        branches = subprocess.run(
            ["git", "branch"],
            cwd=str(git_repo),
            capture_output=True,
            text=True,
        )
        assert "openspec/add-foo--v1" not in branches.stdout
        assert "openspec/add-foo" not in branches.stdout

    def test_worktree_path_uses_standard_layout(self, git_repo: Path) -> None:
        # Spec scenario: worktree at .git-worktrees/<change-id>/v1/
        # (No 'prototype/' segment in the path — only in the branch name.
        # This makes the worktree directory layout uniform whether we're
        # running prototype variants or normal parallel work-packages.)
        args = _make_setup_args(
            change_id="add-foo", agent_id="v1", branch_prefix="prototype"
        )
        with _chdir(git_repo):
            cmd_setup(args)

        wt_path = git_repo / ".git-worktrees" / "add-foo" / "v1"
        assert wt_path.is_dir()

    def test_three_variants_all_land_on_prototype_branches(
        self, git_repo: Path
    ) -> None:
        # End-to-end of the default 3-variant dispatch path: each variant
        # gets its own ``prototype/<change>/v<n>`` branch and its own
        # worktree directory.
        for vid in ("v1", "v2", "v3"):
            args = _make_setup_args(
                change_id="add-foo", agent_id=vid, branch_prefix="prototype"
            )
            with _chdir(git_repo):
                assert cmd_setup(args) == 0

        branches = subprocess.run(
            ["git", "branch", "--list", "prototype/add-foo/*"],
            cwd=str(git_repo),
            capture_output=True,
            text=True,
        )
        for vid in ("v1", "v2", "v3"):
            assert f"prototype/add-foo/{vid}" in branches.stdout


class TestSetupAutoPinsPrototypeWorktrees:
    """Spec scenario: PrototypeWorktreeSupport.worktree-pin."""

    def test_registry_entry_is_pinned(self, git_repo: Path) -> None:
        args = _make_setup_args(
            change_id="add-foo", agent_id="v1", branch_prefix="prototype"
        )
        with _chdir(git_repo):
            cmd_setup(args)

        registry = load_registry(git_repo)
        entry = find_entry(registry, "add-foo", "v1")
        assert entry is not None
        assert entry["pinned"] is True, (
            "prototype worktrees must auto-pin to survive 24h GC per D4"
        )

    def test_standard_setup_does_not_auto_pin(self, git_repo: Path) -> None:
        # Confirm the auto-pin is gated on branch_prefix='prototype' and
        # doesn't leak into the normal openspec/ flow.
        args = _make_setup_args(change_id="add-foo")
        with _chdir(git_repo):
            cmd_setup(args)

        registry = load_registry(git_repo)
        entry = find_entry(registry, "add-foo")
        assert entry is not None
        assert entry["pinned"] is False

    def test_pinned_prototype_survives_gc_after_threshold(
        self, git_repo: Path
    ) -> None:
        # Spec scenario: worktree-pin says "they SHALL be pinned to survive
        # the default 24-hour GC timer". Simulate that by backdating the
        # heartbeat past the threshold and running GC.
        args = _make_setup_args(
            change_id="add-foo", agent_id="v1", branch_prefix="prototype"
        )
        with _chdir(git_repo):
            cmd_setup(args)

        registry = load_registry(git_repo)
        entry = find_entry(registry, "add-foo", "v1")
        assert entry is not None
        old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        entry["last_heartbeat"] = old
        save_registry(git_repo, registry)

        gc_args = argparse.Namespace(
            command="gc", stale_after="24h", force=False
        )
        with _chdir(git_repo):
            assert cmd_gc(gc_args) == 0

        wt_path = git_repo / ".git-worktrees" / "add-foo" / "v1"
        assert wt_path.is_dir(), (
            "GC should NOT remove a pinned prototype worktree"
        )
        registry_after = load_registry(git_repo)
        assert find_entry(registry_after, "add-foo", "v1") is not None


class TestEnvOverrideComposition:
    """Spec scenario: PrototypeWorktreeSupport.branch-override-composition."""

    def test_prototype_prefix_wins_over_env_var(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Operator has set OPENSPEC_BRANCH_OVERRIDE for the session, but
        # the prototype variant must still go on prototype/<change>/v1
        # so cleanup-feature can find and delete the branches by pattern.
        monkeypatch.setenv("OPENSPEC_BRANCH_OVERRIDE", "claude/op-9P9o1")

        args = _make_setup_args(
            change_id="add-foo", agent_id="v1", branch_prefix="prototype"
        )
        with _chdir(git_repo):
            assert cmd_setup(args) == 0

        branches = subprocess.run(
            ["git", "branch", "--list", "prototype/add-foo/v1"],
            cwd=str(git_repo),
            capture_output=True,
            text=True,
        )
        assert "prototype/add-foo/v1" in branches.stdout

        # And the override branch should NOT have been created as a side effect.
        override_branches = subprocess.run(
            ["git", "branch", "--list", "claude/op-9P9o1*"],
            cwd=str(git_repo),
            capture_output=True,
            text=True,
        )
        assert override_branches.stdout.strip() == ""

    def test_parent_feature_branch_still_uses_env_var(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Companion guarantee: a setup call WITHOUT branch_prefix in the
        # same session still produces the env-override branch. This is the
        # "parent feature branch" — the integration target the variant
        # branches eventually merge into.
        monkeypatch.setenv("OPENSPEC_BRANCH_OVERRIDE", "claude/op-9P9o1")

        args = _make_setup_args(change_id="add-foo")
        with _chdir(git_repo):
            assert cmd_setup(args) == 0

        branches = subprocess.run(
            ["git", "branch", "--list", "claude/op-9P9o1"],
            cwd=str(git_repo),
            capture_output=True,
            text=True,
        )
        assert "claude/op-9P9o1" in branches.stdout

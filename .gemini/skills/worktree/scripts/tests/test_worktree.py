"""Tests for scripts/worktree.py."""

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

# Import the module under test
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import worktree
from worktree import (
    worktree_path,
    default_branch,
    load_registry,
    save_registry,
    find_entry,
    remove_entry,
    parse_duration_hours,
    cmd_heartbeat,
    cmd_list,
    cmd_pin,
    cmd_unpin,
    cmd_gc,
)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo for testing."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    # Create initial commit so we have a main branch
    (tmp_path / "README.md").write_text("test")
    subprocess.run(
        ["git", "add", "README.md"], cwd=str(tmp_path), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
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


class TestDefaultBranch:
    def test_basic(self) -> None:
        assert default_branch("change") == "openspec/change"

    def test_with_agent_id(self) -> None:
        assert default_branch("change", agent_id="w1") == "openspec/change--w1"

    def test_with_prefix(self) -> None:
        assert default_branch("change", prefix="fix") == "fix/change"

    def test_with_agent_id_and_prefix(self) -> None:
        assert default_branch("change", agent_id="w1", prefix="fix") == "fix/change--w1"


class TestRegistry:
    def test_load_missing_file_returns_empty(self, tmp_path: Path) -> None:
        reg = load_registry(tmp_path)
        assert reg == {"version": 1, "entries": []}

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        reg = {"version": 1, "entries": [
            {"change_id": "c1", "agent_id": None, "branch": "openspec/c1",
             "worktree_path": "/tmp/wt", "created_at": "2026-01-01T00:00:00+00:00",
             "last_heartbeat": "2026-01-01T00:00:00+00:00", "pinned": False},
        ]}
        save_registry(tmp_path, reg)
        loaded = load_registry(tmp_path)
        assert loaded == reg

    def test_find_entry_by_change_id_and_agent_id(self) -> None:
        reg = {"version": 1, "entries": [
            {"change_id": "c1", "agent_id": None},
            {"change_id": "c1", "agent_id": "w1"},
            {"change_id": "c2", "agent_id": None},
        ]}
        assert find_entry(reg, "c1", "w1") == {"change_id": "c1", "agent_id": "w1"}
        assert find_entry(reg, "c1") == {"change_id": "c1", "agent_id": None}
        assert find_entry(reg, "c3") is None

    def test_remove_entry_returns_true(self) -> None:
        reg = {"version": 1, "entries": [
            {"change_id": "c1", "agent_id": None},
            {"change_id": "c2", "agent_id": None},
        ]}
        assert remove_entry(reg, "c1") is True
        assert len(reg["entries"]) == 1
        assert reg["entries"][0]["change_id"] == "c2"

    def test_remove_entry_missing_returns_false(self) -> None:
        reg = {"version": 1, "entries": [
            {"change_id": "c1", "agent_id": None},
        ]}
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

    def test_output_contains_worktree_path(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        args = _make_args("setup", change_id="test-feature")
        with _chdir(git_repo):
            worktree.cmd_setup(args)
        captured = capsys.readouterr()
        expected = str(git_repo / ".git-worktrees" / "test-feature")
        assert f"WORKTREE_PATH={expected}" in captured.out


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


class TestCmdStatus:
    def test_specific_worktree_exists(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        setup_args = _make_args("setup", change_id="test-feature")
        with _chdir(git_repo):
            worktree.cmd_setup(setup_args)

        status_args = _make_args("status", change_id="test-feature")
        with _chdir(git_repo):
            result = worktree.cmd_status(status_args)
        assert result == 0
        captured = capsys.readouterr()
        assert "EXISTS=true" in captured.out

    def test_specific_worktree_not_found(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
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
        assert entry["pinned"] is True

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
        assert entry["pinned"] is False

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
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)

"""Tests for skills.shared.active_agents."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from shared import active_agents as aa


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".git-worktrees").mkdir()
    return tmp_path


def write_registry(repo: Path, entries: list[dict]) -> None:
    (repo / ".git-worktrees" / ".registry.json").write_text(
        json.dumps({"version": 1, "entries": entries})
    )


NOW = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)


def _entry(change_id: str, *, heartbeat: datetime, pinned: bool = False,
           agent_id: str | None = None) -> dict:
    return {
        "change_id": change_id,
        "agent_id": agent_id,
        "branch": f"openspec/{change_id}" + (f"--{agent_id}" if agent_id else ""),
        "worktree_path": f"/x/{change_id}",
        "created_at": heartbeat.isoformat(),
        "last_heartbeat": heartbeat.isoformat(),
        "pinned": pinned,
    }


# ---------------------------------------------------------------------------
# Library API
# ---------------------------------------------------------------------------


class TestCheckNoActiveAgents:
    def test_no_registry_means_clear(self, tmp_path: Path) -> None:
        clear, active = aa.check_no_active_agents(repo_root=tmp_path)
        assert clear is True
        assert active == []

    def test_empty_registry_means_clear(self, repo: Path) -> None:
        write_registry(repo, [])
        clear, active = aa.check_no_active_agents(repo_root=repo)
        assert clear is True
        assert active == []

    def test_recent_heartbeat_blocks(self, repo: Path) -> None:
        write_registry(repo, [_entry("abc", heartbeat=NOW - timedelta(minutes=5))])
        clear, active = aa.check_no_active_agents(repo_root=repo, now=NOW)
        assert clear is False
        assert len(active) == 1
        assert active[0].change_id == "abc"
        assert active[0].pinned is False

    def test_heartbeat_at_threshold_blocks(self, repo: Path) -> None:
        write_registry(repo, [_entry("edge", heartbeat=NOW - timedelta(hours=1))])
        clear, _ = aa.check_no_active_agents(repo_root=repo, now=NOW)
        assert clear is False

    def test_stale_unpinned_is_ignored(self, repo: Path) -> None:
        write_registry(repo, [_entry("stale", heartbeat=NOW - timedelta(hours=2))])
        clear, active = aa.check_no_active_agents(repo_root=repo, now=NOW)
        assert clear is True
        assert active == []

    def test_pinned_blocks_even_when_stale(self, repo: Path) -> None:
        write_registry(repo, [_entry("pin", heartbeat=NOW - timedelta(days=2), pinned=True)])
        clear, active = aa.check_no_active_agents(repo_root=repo, now=NOW)
        assert clear is False
        assert active[0].pinned is True

    def test_only_active_entries_returned(self, repo: Path) -> None:
        write_registry(repo, [
            _entry("fresh", heartbeat=NOW - timedelta(minutes=2), agent_id="wp-1"),
            _entry("stale", heartbeat=NOW - timedelta(hours=3)),
            _entry("pinned", heartbeat=NOW - timedelta(days=1), pinned=True),
        ])
        clear, active = aa.check_no_active_agents(repo_root=repo, now=NOW)
        assert clear is False
        assert sorted(a.change_id for a in active) == ["fresh", "pinned"]

    def test_unparseable_heartbeat_is_ignored(self, repo: Path) -> None:
        write_registry(repo, [{
            "change_id": "bad",
            "agent_id": None,
            "branch": "openspec/bad",
            "worktree_path": "/x/bad",
            "last_heartbeat": "not-a-timestamp",
            "pinned": False,
        }])
        clear, _ = aa.check_no_active_agents(repo_root=repo, now=NOW)
        assert clear is True

    def test_corrupt_registry_returns_clear(self, repo: Path) -> None:
        # Fail-open: corrupt registry must not wedge sync-point skills.
        (repo / ".git-worktrees" / ".registry.json").write_text("{not json")
        clear, active = aa.check_no_active_agents(repo_root=repo)
        assert clear is True
        assert active == []

    def test_non_dict_entry_is_skipped(self, repo: Path) -> None:
        (repo / ".git-worktrees" / ".registry.json").write_text(
            json.dumps({"version": 1, "entries": ["bogus", 42, None]})
        )
        clear, _ = aa.check_no_active_agents(repo_root=repo, now=NOW)
        assert clear is True

    def test_custom_stale_threshold(self, repo: Path) -> None:
        write_registry(repo, [_entry("recent-but-old", heartbeat=NOW - timedelta(minutes=30))])
        clear_default, _ = aa.check_no_active_agents(repo_root=repo, now=NOW)
        assert clear_default is False
        clear_short, _ = aa.check_no_active_agents(
            repo_root=repo, now=NOW, stale_threshold=timedelta(minutes=10)
        )
        assert clear_short is True


class TestActiveAgentLabel:
    def test_label_with_agent_id(self) -> None:
        a = aa.ActiveAgent(
            change_id="abc", agent_id="wp-1", branch="openspec/abc--wp-1",
            worktree_path="/x", last_heartbeat="...", pinned=False,
        )
        assert a.label == "abc/wp-1 on openspec/abc--wp-1"

    def test_label_without_agent_id(self) -> None:
        a = aa.ActiveAgent(
            change_id="abc", agent_id=None, branch="openspec/abc",
            worktree_path="/x", last_heartbeat="...", pinned=False,
        )
        assert a.label == "abc on openspec/abc"

    def test_label_pinned_suffix(self) -> None:
        a = aa.ActiveAgent(
            change_id="abc", agent_id=None, branch="openspec/abc",
            worktree_path="/x", last_heartbeat="...", pinned=True,
        )
        assert a.label == "abc on openspec/abc (pinned)"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCli:
    def test_exit_zero_when_clear(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write_registry(repo, [])
        rc = aa.main(["--repo-root", str(repo)])
        assert rc == 0
        assert "clear" in capsys.readouterr().out

    def test_exit_one_when_blocked(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write_registry(repo, [_entry("abc", heartbeat=datetime.now(timezone.utc))])
        rc = aa.main(["--repo-root", str(repo)])
        assert rc == 1
        out = capsys.readouterr().out
        assert "BLOCKED" in out
        assert "abc" in out

    def test_force_exits_zero_even_when_blocked(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write_registry(repo, [_entry("abc", heartbeat=datetime.now(timezone.utc))])
        rc = aa.main(["--repo-root", str(repo), "--force"])
        assert rc == 0
        assert "bypassing" in capsys.readouterr().err

    def test_json_output_shape(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write_registry(repo, [_entry("abc", heartbeat=datetime.now(timezone.utc))])
        aa.main(["--repo-root", str(repo), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["clear"] is False
        assert payload["force"] is False
        assert len(payload["active"]) == 1
        assert payload["active"][0]["change_id"] == "abc"

    def test_stale_hours_argument(self, repo: Path) -> None:
        write_registry(repo, [_entry(
            "recent-but-old",
            heartbeat=datetime.now(timezone.utc) - timedelta(minutes=30),
        )])
        # Default 1h threshold -> blocked
        assert aa.main(["--repo-root", str(repo)]) == 1
        # Tighten to 10m -> clear
        assert aa.main(["--repo-root", str(repo), "--stale-hours", "0.166"]) == 0

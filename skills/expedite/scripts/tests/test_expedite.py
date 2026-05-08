"""Tests for skills/expedite/scripts/expedite.py."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

THIS = Path(__file__).resolve()
SCRIPTS_DIR = THIS.parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))
import expedite as ex  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".git-worktrees").mkdir()
    return tmp_path


def write_validation_report(path: Path, *,
                            smoke: str = "pass",
                            security: str = "pass",
                            e2e: str = "pass") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""# Validation Report

## Smoke Tests
**Status**: {smoke}

## Security
**Status**: {security}

## E2E Tests
**Status**: {e2e}
"""
    )


def write_rework_report(path: Path, *,
                        action: str = "none",
                        failures: list[dict] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    failures = failures or []
    path.write_text(json.dumps({
        "failures": failures,
        "summary": {
            "total_failures": len(failures),
            "public_failures": sum(1 for f in failures if f.get("visibility") == "public"),
            "holdout_failures": sum(1 for f in failures if f.get("visibility") == "holdout"),
            "has_blocking_holdout": action == "block-cleanup",
            "recommended_action": action,
        },
    }))


def write_active_agent_registry(repo: Path, *, active: bool) -> None:
    if not active:
        (repo / ".git-worktrees" / ".registry.json").write_text(
            json.dumps({"version": 1, "entries": []})
        )
        return
    now = datetime.now(timezone.utc).isoformat()
    (repo / ".git-worktrees" / ".registry.json").write_text(json.dumps({
        "version": 1,
        "entries": [{
            "change_id": "other",
            "agent_id": "wp-1",
            "branch": "openspec/other--wp-1",
            "worktree_path": "/x/other",
            "created_at": now,
            "last_heartbeat": now,
            "pinned": False,
        }],
    }))


# ---------------------------------------------------------------------------
# Path probing
# ---------------------------------------------------------------------------


class TestPathProbing:
    def test_validation_report_found_in_change_root(self, repo: Path) -> None:
        report = repo / "openspec" / "changes" / "abc" / "validation-report.md"
        write_validation_report(report)
        found = ex.find_validation_report("abc", repo)
        assert found == report

    def test_validation_report_found_in_reports_subdir(self, repo: Path) -> None:
        report = repo / "openspec" / "changes" / "abc" / "reports" / "validation-report.md"
        write_validation_report(report)
        found = ex.find_validation_report("abc", repo)
        assert found == report

    def test_validation_report_found_in_worktree(self, repo: Path) -> None:
        report = repo / ".git-worktrees" / "abc" / "validation-report.md"
        write_validation_report(report)
        found = ex.find_validation_report("abc", repo)
        assert found == report

    def test_validation_report_none_when_missing(self, repo: Path) -> None:
        assert ex.find_validation_report("missing", repo) is None

    def test_rework_report_paths(self, repo: Path) -> None:
        report = repo / "openspec" / "changes" / "abc" / "rework-report.json"
        write_rework_report(report)
        assert ex.find_rework_report("abc", repo) == report


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


class TestActiveAgentsCheck:
    def test_pass_when_no_agents(self, repo: Path) -> None:
        write_active_agent_registry(repo, active=False)
        c = ex.check_active_agents(repo)
        assert c.status == "pass"

    def test_fail_when_agents_active(self, repo: Path) -> None:
        write_active_agent_registry(repo, active=True)
        c = ex.check_active_agents(repo)
        assert c.status == "fail"
        assert "active agent" in c.detail
        assert "force" in c.action.lower()


class TestValidationReportCheck:
    def test_skip_when_path_none(self) -> None:
        c = ex.check_validation_report(None)
        assert c.status == "skip"
        assert "validate-feature" in c.action

    def test_pass_when_all_hard_gates_pass(self, tmp_path: Path) -> None:
        report = tmp_path / "validation-report.md"
        write_validation_report(report)
        c = ex.check_validation_report(report)
        assert c.status == "pass"

    def test_fail_when_smoke_fails(self, tmp_path: Path) -> None:
        report = tmp_path / "validation-report.md"
        write_validation_report(report, smoke="fail")
        c = ex.check_validation_report(report)
        assert c.status == "fail"

    def test_fail_when_security_fails(self, tmp_path: Path) -> None:
        report = tmp_path / "validation-report.md"
        write_validation_report(report, security="fail")
        c = ex.check_validation_report(report)
        assert c.status == "fail"

    def test_fail_when_e2e_fails(self, tmp_path: Path) -> None:
        report = tmp_path / "validation-report.md"
        write_validation_report(report, e2e="fail")
        c = ex.check_validation_report(report)
        assert c.status == "fail"


class TestReworkReportCheck:
    def test_skip_when_path_none(self) -> None:
        c = ex.check_rework_report(None)
        assert c.status == "skip"

    def test_pass_when_action_none(self, tmp_path: Path) -> None:
        path = tmp_path / "rework-report.json"
        write_rework_report(path, action="none")
        c = ex.check_rework_report(path)
        assert c.status == "pass"

    def test_pass_when_action_defer(self, tmp_path: Path) -> None:
        path = tmp_path / "rework-report.json"
        # ACTION_DEFER is summary_action when failures exist but none iterate/block
        write_rework_report(path, action="defer", failures=[
            {"scenario_id": "s1", "visibility": "public", "recommended_action": "defer"},
        ])
        c = ex.check_rework_report(path)
        assert c.status == "pass"
        assert "deferred" in c.detail

    def test_fail_when_action_block_cleanup(self, tmp_path: Path) -> None:
        path = tmp_path / "rework-report.json"
        write_rework_report(path, action="block-cleanup", failures=[
            {"scenario_id": "s1", "visibility": "holdout",
             "recommended_action": "block-cleanup"},
        ])
        c = ex.check_rework_report(path)
        assert c.status == "fail"
        assert "block-cleanup" in c.detail
        assert "merge is blocked" in c.action

    def test_fail_when_action_iterate(self, tmp_path: Path) -> None:
        path = tmp_path / "rework-report.json"
        write_rework_report(path, action="iterate", failures=[
            {"scenario_id": "s1", "visibility": "public",
             "recommended_action": "iterate"},
        ])
        c = ex.check_rework_report(path)
        assert c.status == "fail"
        assert "iterate" in c.action

    def test_fail_when_action_revise_spec(self, tmp_path: Path) -> None:
        path = tmp_path / "rework-report.json"
        write_rework_report(path, action="revise-spec", failures=[
            {"scenario_id": "s1", "visibility": "public",
             "recommended_action": "revise-spec"},
        ])
        c = ex.check_rework_report(path)
        assert c.status == "fail"
        assert "spec revision" in c.detail or "spec revision" in c.action

    def test_fail_when_load_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "rework-report.json"
        path.write_text("{not json")
        c = ex.check_rework_report(path)
        assert c.status == "fail"
        assert "failed to load" in c.detail


# ---------------------------------------------------------------------------
# expedite() composition
# ---------------------------------------------------------------------------


class TestExpedite:
    def test_ready_when_all_pass(self, repo: Path) -> None:
        write_active_agent_registry(repo, active=False)
        write_validation_report(repo / "openspec" / "changes" / "abc" / "validation-report.md")
        write_rework_report(repo / "openspec" / "changes" / "abc" / "rework-report.json",
                            action="none")
        v = ex.expedite("abc", repo)
        assert v.ready is True
        assert all(c.status in ("pass", "skip") for c in v.checks)

    def test_ready_when_skips_only(self, repo: Path) -> None:
        write_active_agent_registry(repo, active=False)
        # No reports → both skip → still ready
        v = ex.expedite("abc", repo)
        assert v.ready is True
        statuses = [c.status for c in v.checks]
        assert "skip" in statuses

    def test_blocked_when_active_agents(self, repo: Path) -> None:
        write_active_agent_registry(repo, active=True)
        v = ex.expedite("abc", repo)
        assert v.ready is False

    def test_blocked_when_validation_fails(self, repo: Path) -> None:
        write_active_agent_registry(repo, active=False)
        write_validation_report(
            repo / "openspec" / "changes" / "abc" / "validation-report.md",
            smoke="fail",
        )
        v = ex.expedite("abc", repo)
        assert v.ready is False

    def test_blocked_when_rework_blocks(self, repo: Path) -> None:
        write_active_agent_registry(repo, active=False)
        write_validation_report(repo / "openspec" / "changes" / "abc" / "validation-report.md")
        write_rework_report(
            repo / "openspec" / "changes" / "abc" / "rework-report.json",
            action="block-cleanup",
            failures=[{"scenario_id": "s1", "visibility": "holdout",
                       "recommended_action": "block-cleanup"}],
        )
        v = ex.expedite("abc", repo)
        assert v.ready is False

    def test_explicit_paths_override_probing(self, repo: Path, tmp_path: Path) -> None:
        write_active_agent_registry(repo, active=False)
        # Put a passing report somewhere the probe wouldn't find:
        elsewhere = tmp_path / "elsewhere" / "validation-report.md"
        write_validation_report(elsewhere)
        v = ex.expedite("abc", repo, validation_report=elsewhere)
        validation_check = next(c for c in v.checks if c.name == "validation_report")
        assert validation_check.status == "pass"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCli:
    def test_exit_zero_when_ready(self, repo: Path,
                                   capsys: pytest.CaptureFixture[str]) -> None:
        write_active_agent_registry(repo, active=False)
        rc = ex.main(["abc", "--repo-root", str(repo)])
        assert rc == 0
        assert "READY" in capsys.readouterr().out

    def test_exit_one_when_blocked(self, repo: Path,
                                    capsys: pytest.CaptureFixture[str]) -> None:
        write_active_agent_registry(repo, active=True)
        rc = ex.main(["abc", "--repo-root", str(repo)])
        assert rc == 1
        out = capsys.readouterr().out
        assert "BLOCKED" in out
        assert "active_agents" in out

    def test_json_output_shape(self, repo: Path,
                                capsys: pytest.CaptureFixture[str]) -> None:
        write_active_agent_registry(repo, active=False)
        ex.main(["abc", "--repo-root", str(repo), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["change_id"] == "abc"
        assert payload["ready"] is True
        assert isinstance(payload["checks"], list)
        assert {c["name"] for c in payload["checks"]} == {
            "active_agents", "validation_report", "rework_report"
        }

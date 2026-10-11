"""results query / trend / latest (tasks 3.3-3.5)."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from agent_scenarios.results_cli import main
from agent_scenarios.results_store import (
    JsonlResultsStore,
    ResultRecord,
    RunRecord,
    compute_trend,
)

D = datetime(2026, 10, 12, 3, 0, tzinfo=UTC)


def rec(
    *, vendor: str = "claude", skill: str = "validate-feature", family: str = "validate",
    scenario: str = "validate-feature-clean-pass", status: str = "pass",
    at: datetime = D, run: str = "r1",
) -> ResultRecord:
    return ResultRecord(
        run_id=run, recorded_at=at.isoformat(), scenario_id=scenario, skill_under_test=skill,
        skill_family=family,  # type: ignore[arg-type]
        vendor=vendor, deterministic_status=status,  # type: ignore[arg-type]
        failed_gates=["g"] if status == "fail" else [], trajectory_status=None,
        duration_seconds=None, repo_sha=None, skills_sha=None,
        error="boom" if status == "error" else None,
    )


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    path = tmp_path / "results.jsonl"
    store = JsonlResultsStore(path)
    store.append([
        rec(vendor="claude", at=D - timedelta(days=3), run="old"),
        rec(vendor="codex", at=D, status="fail"),
        rec(vendor="claude", at=D),
        rec(vendor="codex", skill="plan-feature", family="plan", scenario="plan-feature-basic",
            at=D + timedelta(hours=1)),
        rec(vendor="codex", at=D + timedelta(days=1), run="r2"),
        RunRecord(run_id="r1", started_at=D.isoformat(), finished_at=D.isoformat(),
                  status="completed", planned_pairs=4, executed_pairs=4, vendors=["claude"],
                  config_digest=None, repo_sha=None, skills_sha=None, reason=None),
    ])
    return path


def run_cli(capsys: pytest.CaptureFixture[str], store: Path, *argv: str) -> Any:
    assert main([argv[0], argv[1], "--store", str(store), *argv[2:]]) == 0
    return json.loads(capsys.readouterr().out)


def test_query_by_vendor_skill_and_window(store_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rows = run_cli(capsys, store_path, "results", "query", "--vendor", "codex",
                   "--skill", "validate-feature", "--since", "2026-10-12")
    assert {(r["vendor"], r["skill_under_test"]) for r in rows} == {("codex", "validate-feature")}
    assert len(rows) == 2  # fail on 10-12 and pass on 10-13


def test_query_by_family_and_scenario_until(store_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fam = run_cli(capsys, store_path, "results", "query", "--family", "plan")
    assert [r["scenario_id"] for r in fam] == ["plan-feature-basic"]
    rows = run_cli(capsys, store_path, "results", "query", "--scenario",
                   "validate-feature-clean-pass", "--until", "2026-10-12")
    assert all(r["recorded_at"] <= "2026-10-12T23:59:59.999999+00:00" for r in rows)
    assert len(rows) == 3  # old claude, codex fail, claude pass (bare --until date is inclusive)


def test_query_marks_run_state(store_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rows = run_cli(capsys, store_path, "results", "query")
    states = {r["run_id"]: r["run_state"] for r in rows}
    assert states == {"old": "interrupted", "r1": "complete", "r2": "interrupted"}


def test_query_status_filter_and_table_format(store_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["results", "query", "--store", str(store_path), "--status", "fail",
                 "--format", "table"]) == 0
    out = capsys.readouterr().out
    assert "scenario_id" in out and "fail" in out and out.count("\n") == 2


def test_latest_one_per_scenario_vendor(store_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rows = run_cli(capsys, store_path, "results", "latest", "--skill", "validate-feature")
    pairs = [(r["scenario_id"], r["vendor"]) for r in rows]
    assert sorted(pairs) == [("validate-feature-clean-pass", "claude"),
                             ("validate-feature-clean-pass", "codex")]
    codex = next(r for r in rows if r["vendor"] == "codex")
    assert codex["run_id"] == "r2" and codex["deterministic_status"] == "pass"


def test_trend_buckets_and_denominator(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "r.jsonl"
    JsonlResultsStore(path).append([
        rec(status="pass"), rec(status="pass"), rec(status="fail"),
        rec(status="error"), rec(status="skipped_budget"),
        rec(vendor="codex", status="pass", at=D + timedelta(days=1)),
    ])
    rows = run_cli(capsys, path, "results", "trend", "--group-by", "vendor,skill",
                   "--bucket", "day")
    first = next(r for r in rows if r["vendor"] == "claude")
    assert first["bucket"] == "2026-10-12" and first["skill"] == "validate-feature"
    assert (first["pass"], first["fail"], first["error"], first["skipped_budget"]) == (2, 1, 1, 1)
    assert first["pass_rate"] == pytest.approx(2 / 3, abs=1e-3)  # error/skipped excluded
    codex = next(r for r in rows if r["vendor"] == "codex")
    assert codex["bucket"] == "2026-10-13" and codex["pass_rate"] == 1.0


def test_trend_week_bucket_and_all_error_group_has_null_rate() -> None:
    rows = compute_trend([rec(status="error"), rec(at=D + timedelta(days=2))],
                         ("vendor", "family"), "week")
    assert len({r["bucket"] for r in rows}) == 1
    assert rows[0]["bucket"] == "2026-10-12"  # Monday
    only_error = compute_trend([rec(status="error")], ("scenario", "vendor"), "day")
    assert only_error[0]["pass_rate"] is None


def test_trend_over_15k_records_is_fast(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "big.jsonl"
    store = JsonlResultsStore(path)
    batch = [rec(vendor=f"v{i % 3}", at=D + timedelta(minutes=i), run=f"r{i // 22}")
             for i in range(15_000)]
    store.append(batch)
    start = time.monotonic()
    rows = run_cli(capsys, path, "results", "trend", "--group-by", "vendor,skill")
    assert time.monotonic() - start < 2.0
    assert sum(r["pass"] for r in rows) == 15_000

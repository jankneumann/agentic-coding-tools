"""Nightly run loop with an injected fake clock (task 5.2)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from agent_scenarios import AgentScenario, FakeExecutor, Outcome, RunResult
from agent_scenarios.gap_emitter import SpoolMemorySink
from agent_scenarios.nightly import NightlyConfig, run_nightly
from agent_scenarios.results_store import JsonlResultsStore, ResultRecord, RunRecord
from tests.test_nightly_config import Factory, make_suite, run_records, write_config

PASS = Outcome(write_files={"out.txt": "x"})
FAIL = Outcome()
ERROR = Outcome(error="vendor CLI unavailable: nope", exit_code=127)


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class TickingExecutor:
    """Wraps FakeExecutor; each run advances the fake clock and logs the call order."""

    def __init__(self, script: dict[Any, Outcome], clock: Clock, step: float = 10.0,
                 log: list[str] | None = None) -> None:
        self.inner = FakeExecutor(script)
        self.clock, self.step, self.log = clock, step, log if log is not None else []
        self.runs: list[tuple[str, str]] = []

    def run(self, scenario: AgentScenario, vendor: str, workdir: Path) -> RunResult:
        self.runs.append((scenario.id, vendor))
        self.log.append(f"run:{scenario.id}:{vendor}")
        self.clock.t += self.step
        return self.inner.run(scenario, vendor, workdir)


class Sink:
    def __init__(self, log: list[str] | None = None, ack: bool = True) -> None:
        self.entries: list[dict[str, Any]] = []
        self.log, self.ack = log if log is not None else [], ack

    def send(self, entry: dict[str, Any]) -> bool:
        self.log.append("sink")
        self.entries.append(entry)
        return self.ack


FIXED_NOW = datetime(2026, 10, 12, 2, 30, tzinfo=UTC)


def go(root: Path, executor: Any, clock: Clock | None = None, sink: Sink | None = None,
       **over: Any) -> int:
    return run_nightly(
        write_config(root, **over), executor_factory=Factory(executor), clock=clock or Clock(),
        coordinator_sink=sink or Sink(), now=lambda: FIXED_NOW,
    )


def results(root: Path) -> list[ResultRecord]:
    return list(JsonlResultsStore(root / "state" / "results.jsonl").iter_results())


@pytest.fixture
def suite(tmp_path: Path) -> Path:
    make_suite(tmp_path)
    return tmp_path


def test_all_pass_exits_0_with_full_matrix_recorded(suite: Path) -> None:
    clock = Clock()
    ex = TickingExecutor({"a-one": PASS, "b-two": PASS}, clock, step=7.5)
    assert go(suite, ex, clock) == 0
    recs = results(suite)
    assert len(recs) == 4
    assert {(r.scenario_id, r.vendor) for r in recs} == {
        ("a-one", "claude"), ("a-one", "codex"), ("b-two", "claude"), ("b-two", "codex")}
    assert all(r.deterministic_status == "pass" and r.duration_seconds == 7.5 for r in recs)
    assert all(r.skill_family == "plan" for r in recs)
    (run,) = run_records(suite)
    assert run.status == "completed" and run.executed_pairs == run.planned_pairs == 4
    assert {r.run_id for r in recs} == {run.run_id}
    assert ex.runs == [("a-one", "claude"), ("a-one", "codex"), ("b-two", "claude"),
                       ("b-two", "codex")]


def test_failure_exits_1_and_writes_results_findings_and_gaps(suite: Path) -> None:
    clock = Clock()
    ex = TickingExecutor({("a-one", "claude"): FAIL, ("a-one", "codex"): PASS, "b-two": PASS}, clock)
    sink = Sink()
    assert go(suite, ex, clock, sink) == 1
    (run,) = run_records(suite)
    findings = json.loads((suite / "state" / "findings" / f"{run.run_id}.json").read_text())
    assert findings["findings"], "a failing pair must produce findings"
    assert len(sink.entries) == 1
    gap = sink.entries[0]
    assert "source:scenario-parity" in gap["tags"] and "vendor:claude" in gap["tags"]
    assert "capability_gap:scenario-parity/a-one/wrote-out" in gap["tags"]
    assert gap["session_id"] == run.run_id


def test_undeliverable_gaps_are_spooled(suite: Path) -> None:
    clock = Clock()
    ex = TickingExecutor({"a-one": FAIL, "b-two": PASS}, clock)
    assert go(suite, ex, clock, Sink(ack=False)) == 1
    pending = SpoolMemorySink(suite / "state" / "gap-spool.jsonl").pending()
    assert len(pending) == 2  # a-one on both vendors


def test_errors_only_exit_3_and_emit_no_gaps(suite: Path) -> None:
    clock = Clock()
    ex = TickingExecutor({("a-one", "claude"): ERROR, ("a-one", "codex"): PASS, "b-two": PASS}, clock)
    sink = Sink()
    assert go(suite, ex, clock, sink) == 3
    assert sink.entries == []
    errs = [r for r in results(suite) if r.deterministic_status == "error"]
    assert len(errs) == 1 and "unavailable" in (errs[0].error or "")


def test_wall_clock_budget_skips_remaining_pairs(suite: Path) -> None:
    clock = Clock()
    ex = TickingExecutor({"a-one": PASS, "b-two": PASS}, clock, step=100.0)
    # 1 minute budget: the first pair (100s) exhausts it; the other three are skipped.
    code = go(suite, ex, clock, caps={"max_wall_clock_minutes": 1})
    assert code == 3  # incomplete matrix is never green, even with all executed pairs passing
    recs = results(suite)
    assert [r.deterministic_status for r in recs] == ["pass", "skipped_budget",
                                                      "skipped_budget", "skipped_budget"]
    assert ex.runs == [("a-one", "claude")]
    skipped = recs[1]
    assert skipped.duration_seconds is None and skipped.failed_gates == []
    (run,) = run_records(suite)
    assert run.status == "budget_exhausted" and run.executed_pairs == 1 and run.planned_pairs == 4


def test_fail_with_budget_exhausted_exits_1(suite: Path) -> None:
    clock = Clock()
    ex = TickingExecutor({"a-one": FAIL, "b-two": PASS}, clock, step=100.0)
    assert go(suite, ex, clock, caps={"max_wall_clock_minutes": 1}) == 1
    assert run_records(suite)[0].status == "budget_exhausted"


def test_results_are_appended_incrementally_and_survive_a_kill(suite: Path) -> None:
    clock = Clock()

    class Killed(TickingExecutor):
        def run(self, scenario: AgentScenario, vendor: str, workdir: Path) -> RunResult:
            if len(self.runs) == 2:
                raise KeyboardInterrupt  # SIGKILL stand-in: not an Exception
            return super().run(scenario, vendor, workdir)

    ex = Killed({"a-one": PASS, "b-two": PASS}, clock)
    with pytest.raises(KeyboardInterrupt):
        go(suite, ex, clock)
    assert len(results(suite)) == 2
    assert run_records(suite) == []


def test_spool_is_flushed_before_any_pair_runs(suite: Path) -> None:
    log: list[str] = []
    SpoolMemorySink(suite / "state" / "gap-spool.jsonl").send(
        {"summary": "old", "tags": ["capability_gap"]})
    clock = Clock()
    ex = TickingExecutor({"a-one": PASS, "b-two": PASS}, clock, log=log)
    sink = Sink(log)
    assert go(suite, ex, clock, sink) == 0
    assert log[0] == "sink" and log[1].startswith("run:")
    assert sink.entries[0]["summary"] == "old"
    assert SpoolMemorySink(suite / "state" / "gap-spool.jsonl").pending() == []


def test_pass_workspaces_deleted_and_fail_error_kept(suite: Path) -> None:
    clock = Clock()
    ex = TickingExecutor({("a-one", "claude"): FAIL, ("a-one", "codex"): ERROR, "b-two": PASS},
                         clock)
    go(suite, ex, clock)
    (run,) = run_records(suite)
    run_dir = suite / "state" / "workspaces" / run.run_id
    assert sorted(p.name for p in run_dir.iterdir() if p.is_dir()) == [
        "a-one--claude", "a-one--codex"]


def test_old_run_dirs_pruned_beyond_retention(suite: Path) -> None:
    ws = suite / "state" / "workspaces"
    for i in range(9):
        (ws / f"nightly-2026010{i + 1}T000000Z-old{i}").mkdir(parents=True)
    clock = Clock()
    ex = TickingExecutor({"a-one": PASS, "b-two": PASS}, clock)
    go(suite, ex, clock, retain_failed_runs=3)
    names = sorted(p.name for p in ws.iterdir())
    old = [n for n in names if n.endswith(tuple(f"old{i}" for i in range(9)))]
    assert old == [f"nightly-2026010{i + 1}T000000Z-old{i}" for i in (6, 7, 8)]


def test_run_record_carries_digest_and_vendors(suite: Path) -> None:
    clock = Clock()
    ex = TickingExecutor({"a-one": PASS, "b-two": PASS}, clock)
    go(suite, ex, clock)
    (run,) = run_records(suite)
    assert run.vendors == ["claude", "codex"] and run.config_digest and len(run.config_digest) == 16
    assert isinstance(run, RunRecord)


def test_default_executor_factory_wires_hermetic_settings(tmp_path: Path) -> None:
    from agent_scenarios import CLIVendorExecutor
    from agent_scenarios.nightly import default_executor_factory, load_config

    make_suite(tmp_path)
    path = write_config(tmp_path, env_scrub=["EXTRA"], env_set={"FOO": "bar"},
                        caps={"per_pair_timeout_seconds": 77})
    cfg: NightlyConfig = load_config(path)
    ex = default_executor_factory(cfg)
    assert isinstance(ex, CLIVendorExecutor)
    assert ex._timeout == 77 and ex._env_scrub == ("EXTRA",) and ex._env_set == {"FOO": "bar"}
    assert set(ex._always_scrub) == {"COORDINATION_API_KEY", "COORDINATION_API_URL"}
    assert ex._skills_root == tmp_path / "repo" / "skills"


def test_findings_emission_failure_is_not_a_green_night(
    suite: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Results, findings and gaps are the run's contract: a lost findings file is an
    infrastructure failure recorded on the run record, never exit 0."""
    import agent_scenarios.nightly as nightly_mod

    def boom(**_: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(nightly_mod, "emit_findings", boom)
    clock = Clock()
    assert go(suite, TickingExecutor({"a-one": PASS, "b-two": PASS}, clock), clock) == 3
    (run,) = run_records(suite)
    assert run.status == "completed"
    assert run.reason is not None and "findings emission failed: disk full" in run.reason

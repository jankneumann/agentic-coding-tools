"""ResultsStore append/read (tasks 3.1/3.2)."""

from __future__ import annotations

import fcntl
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from agent_scenarios.models import (
    GateVerdict,
    ParityMatrix,
    TrajectoryVerdict,
    VendorRunVerdict,
)
from agent_scenarios.results_store import (
    JsonlResultsStore,
    RecordFilter,
    ResultRecord,
    RunRecord,
    lock_path_for,
    records_from_matrices,
    run_states,
    skipped_budget_record,
)
from agent_scenarios.suite import skill_family
from tests.test_schemas import load_schema

SCHEMA = load_schema("results-record.schema.json")
T0 = datetime(2026, 10, 12, 2, 30, tzinfo=UTC)


def result(**kw: Any) -> ResultRecord:
    base: dict[str, Any] = {
        "run_id": "r1", "recorded_at": T0.isoformat(), "scenario_id": "s1",
        "skill_under_test": "plan-feature", "skill_family": "plan", "vendor": "claude",
        "deterministic_status": "pass", "failed_gates": [], "trajectory_status": "skip",
        "duration_seconds": 1.5, "repo_sha": "abc", "skills_sha": None, "error": None,
    }
    base.update(kw)
    return ResultRecord(**base)


def run_rec(run_id: str = "r1", **kw: Any) -> RunRecord:
    base: dict[str, Any] = {
        "run_id": run_id, "started_at": T0.isoformat(), "finished_at": T0.isoformat(),
        "status": "completed", "planned_pairs": 1, "executed_pairs": 1,
        "vendors": ["claude"], "config_digest": None, "repo_sha": None, "skills_sha": None,
        "reason": None,
    }
    base.update(kw)
    return RunRecord(**base)


def _verdict(vendor: str, status: str, gates: list[tuple[str, str]], error: str | None = None
             ) -> VendorRunVerdict:
    return VendorRunVerdict(
        scenario_id="s1", vendor=vendor,
        gate_verdicts=[GateVerdict(gate_id=g, check="file", mode="verify", status=s)  # type: ignore[arg-type]
                       for g, s in gates],
        trajectory=TrajectoryVerdict(status="skip"),
        deterministic_status=status,  # type: ignore[arg-type]
        error=error,
    )


def test_records_validate_against_schema() -> None:
    for rec in (result(), result(deterministic_status="fail", failed_gates=["g"]), run_rec(),
                skipped_budget_record("r1", "s", "plan-feature", "claude", family_of=skill_family)):
        jsonschema.validate(rec.model_dump(mode="json"), SCHEMA)


def test_nullable_fields_are_explicit_nulls() -> None:
    dumped = result().model_dump(mode="json")
    assert dumped["skills_sha"] is None and "skills_sha" in dumped
    assert dumped["schema_version"] == 1 and dumped["record_type"] == "result"


@pytest.mark.parametrize(
    "kw",
    [
        {"deterministic_status": "fail", "failed_gates": []},
        {"deterministic_status": "pass", "failed_gates": ["g"]},
        {"deterministic_status": "skipped_budget", "failed_gates": ["g"]},
        {"deterministic_status": "error", "error": None},
    ],
)
def test_contradictory_states_rejected_by_model_and_schema(kw: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        result(**kw)
    raw = result().model_dump(mode="json") | kw
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(raw, SCHEMA)


def test_records_from_matrices_field_mapping() -> None:
    matrix = ParityMatrix(scenario_id="s1", scenario_name="n", results=[
        _verdict("claude", "pass", [("a", "pass")]),
        _verdict("codex", "fail", [("a", "pass"), ("b", "fail"), ("c", "error")]),
        _verdict("grok", "error", [], error="vendor CLI timed out after 5s"),
    ])
    recs = records_from_matrices(
        "r1", [matrix], skill_of={"s1": "plan-feature"}, family_of=skill_family,
        durations={("s1", "claude"): 3.25}, repo_sha="deadbeef", skills_sha="deadbeef+dirty",
        recorded_at=T0,
    )
    by_vendor = {r.vendor: r for r in recs}
    assert by_vendor["claude"].duration_seconds == 3.25
    assert by_vendor["claude"].skill_family == "plan"
    assert by_vendor["codex"].failed_gates == ["b", "c"]
    assert by_vendor["codex"].duration_seconds is None
    assert by_vendor["grok"].error == "vendor CLI timed out after 5s"
    assert by_vendor["codex"].error is None
    assert all(r.skills_sha == "deadbeef+dirty" and r.trajectory_status == "skip" for r in recs)
    for r in recs:
        jsonschema.validate(r.model_dump(mode="json"), SCHEMA)


def test_append_and_read_roundtrip(tmp_path: Path) -> None:
    store = JsonlResultsStore(tmp_path / "sub" / "results.jsonl")
    store.append([result(), run_rec()])
    store.append([result(vendor="codex")])
    recs = list(store.iter_records())
    assert [type(r).__name__ for r in recs] == ["ResultRecord", "RunRecord", "ResultRecord"]
    assert len(list(store.iter_records(RecordFilter(vendor="codex")))) == 2  # run rec passes through


def test_torn_final_line_and_unknown_version_skipped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "r.jsonl"
    store = JsonlResultsStore(path)
    store.append([result()])
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('{"schema_version": 2, "record_type": "result"}\n')
        fh.write('{"schema_version": 1, "record_type": "res')  # torn, no newline
    with caplog.at_level(logging.WARNING):
        recs = list(store.iter_records())
    assert len(recs) == 1
    assert any("unknown schema_version" in m for m in caplog.messages)
    assert any("torn final" in m for m in caplog.messages)
    # An append after a torn tail must not be glued to the garbage.
    store.append([result(vendor="codex")])
    assert [r.vendor for r in store.iter_records() if isinstance(r, ResultRecord)] == [
        "claude", "codex"]


def test_concurrent_appends_keep_whole_lines(tmp_path: Path) -> None:
    store = JsonlResultsStore(tmp_path / "r.jsonl")

    def worker(n: int) -> None:
        for i in range(25):
            store.append([result(run_id=f"w{n}", scenario_id=f"s{i}")])

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(list(store.iter_records())) == 150


def test_interrupted_run_detected(tmp_path: Path) -> None:
    store = JsonlResultsStore(tmp_path / "r.jsonl")
    store.append([result(run_id="done"), run_rec("done")])
    store.append([result(run_id="killed", scenario_id=f"s{i}") for i in range(5)])
    states = run_states(store)
    assert states == {"done": "complete", "killed": "interrupted"}


def test_run_in_progress_while_lock_held(tmp_path: Path) -> None:
    store = JsonlResultsStore(tmp_path / "r.jsonl")
    store.append([result(run_id="live")])
    lock = lock_path_for(store.path)
    with open(lock, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert run_states(store) == {"live": "in_progress"}
    assert run_states(store) == {"live": "interrupted"}

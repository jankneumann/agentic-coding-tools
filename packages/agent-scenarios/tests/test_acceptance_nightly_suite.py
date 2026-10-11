"""Acceptance: a 2-vendor nightly over the full seed suite with golden outcomes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_scenarios import FakeExecutor, load_scenarios
from agent_scenarios.__main__ import main as cli_main
from agent_scenarios.nightly import NightlyConfig, run_nightly
from agent_scenarios.results_store import JsonlResultsStore, RunRecord
from tests.test_nightly_config import write_config
from tests.test_seed_outcomes import outcome_module

from .conftest import SCENARIOS_DIR


class Sink:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def send(self, entry: dict[str, Any]) -> bool:
        self.entries.append(entry)
        return True


def _golden_factory(cfg: NightlyConfig) -> FakeExecutor:
    scripts = {s.id: outcome_module(s.id).golden for s in load_scenarios(SCENARIOS_DIR)}
    return FakeExecutor(scripts)  # type: ignore[arg-type]


def test_two_vendor_nightly_over_full_suite_is_all_green(
    tmp_path: Path, capsys: Any
) -> None:
    path = write_config(tmp_path, scenarios_dir=str(SCENARIOS_DIR))
    sink = Sink()
    assert run_nightly(path, executor_factory=_golden_factory, coordinator_sink=sink) == 0
    capsys.readouterr()

    store = JsonlResultsStore(tmp_path / "state" / "results.jsonl")
    records = list(store.iter_records())
    results = [r for r in records if not isinstance(r, RunRecord)]
    runs = [r for r in records if isinstance(r, RunRecord)]
    n = len(load_scenarios(SCENARIOS_DIR))
    assert n >= 10
    assert len(results) == 2 * n and len(runs) == 1  # 22 results + 1 run for 11 scenarios
    assert {r.run_id for r in records} == {runs[0].run_id}
    assert {r.vendor for r in results} == {"claude", "codex"}
    assert {r.skill_family for r in results} == {"plan", "implement", "validate", "merge"}
    assert all(r.deterministic_status == "pass" for r in results)
    assert runs[0].status == "completed" and runs[0].executed_pairs == 2 * n
    assert sink.entries == []

    assert cli_main(["results", "trend", "--store", str(store.path),
                     "--group-by", "vendor,skill"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert {r["vendor"] for r in rows} == {"claude", "codex"}
    assert {r["skill"] for r in rows} >= {"plan-feature", "implement-feature",
                                          "validate-feature", "merge-pull-requests"}
    assert all(r["pass_rate"] == 1.0 for r in rows)

    # Passing pairs leave no workspaces behind.
    run_dir = tmp_path / "state" / "workspaces" / runs[0].run_id
    assert not any(p.is_dir() for p in run_dir.iterdir())

"""Golden/broken self-test: every seed gate set is satisfiable and discriminating (task 2.3)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from agent_scenarios import AgentScenario, FakeExecutor, load_scenarios, run_scenario

from .conftest import SCENARIOS_DIR

SCENARIOS = {s.id: s for s in load_scenarios(SCENARIOS_DIR)}


OUTCOMES_DIR = Path(__file__).resolve().parent / "scenario_outcomes"


def outcome_module(scenario_id: str) -> ModuleType:
    """Load ``scenario_outcomes/<scenario_id>.py`` (hyphenated names are not importable)."""
    path = OUTCOMES_DIR / f"{scenario_id}.py"
    name = f"tests.scenario_outcomes.{scenario_id.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("scenario_id", sorted(SCENARIOS))
def test_golden_outcome_passes_every_gate(scenario_id: str, tmp_path: Path) -> None:
    scenario: AgentScenario = SCENARIOS[scenario_id]
    mod = outcome_module(scenario_id)
    matrix = run_scenario(
        scenario, FakeExecutor({scenario_id: mod.golden}), workspaces_root=tmp_path
    )
    assert len(matrix.results) == len(scenario.vendors)
    for result in matrix.results:
        assert result.deterministic_status == "pass", (
            result.vendor,
            result.error,
            [(g.gate_id, g.status, g.detail) for g in result.gate_verdicts if g.status != "pass"],
        )


@pytest.mark.parametrize("scenario_id", sorted(SCENARIOS))
def test_broken_outcome_fails_a_named_gate(scenario_id: str, tmp_path: Path) -> None:
    scenario: AgentScenario = SCENARIOS[scenario_id]
    mod = outcome_module(scenario_id)
    matrix = run_scenario(
        scenario, FakeExecutor({scenario_id: mod.broken}), workspaces_root=tmp_path
    )
    for result in matrix.results:
        assert result.deterministic_status == "fail", (result.vendor, result.error)
        assert mod.BROKEN_GATE in [g.gate_id for g in result.failed_gates]

"""Scenario YAML loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_scenarios import ExpectBlock, load_scenario, load_scenarios
from agent_scenarios.loader import ScenarioLoadError
from agent_scenarios.models import AgentScenario, GoalGate


def test_seed_scenarios_load_and_validate(scenarios_dir: Path) -> None:
    scenarios = load_scenarios(scenarios_dir)
    ids = {s.id for s in scenarios}
    assert {"plan-feature-basic", "implement-feature-basic"} <= ids
    for s in scenarios:
        assert s.vendors, f"{s.id} has no vendors"
        assert s.goal_gates.all_gates(), f"{s.id} has no gates"
        assert s.source_path and s.source_path.endswith(".scenario.yaml")


def test_reuses_gen_eval_expectblock() -> None:
    """The command goal gate carries a genuine gen-eval ExpectBlock."""
    gate = GoalGate(id="g", check="command", command=["true"], expect=ExpectBlock(exit_code=0))
    assert isinstance(gate.expect, ExpectBlock)


def test_scenario_requires_vendor() -> None:
    with pytest.raises(ValueError, match="at least one vendor"):
        AgentScenario(
            id="x",
            name="x",
            task_prompt="do",
            skill_under_test="s",
            vendors=[],
            goal_gates={"verify": [{"id": "g", "check": "file", "path": "a"}]},
        )


def test_scenario_requires_gate() -> None:
    with pytest.raises(ValueError, match="at least one goal gate"):
        AgentScenario(
            id="x",
            name="x",
            task_prompt="do",
            skill_under_test="s",
            vendors=["claude"],
        )


def test_command_gate_requires_command() -> None:
    with pytest.raises(ValueError, match="requires 'command'"):
        GoalGate(id="g", check="command")


def test_branch_gate_requires_branch() -> None:
    with pytest.raises(ValueError, match="requires 'branch'"):
        GoalGate(id="g", check="branch")


def test_load_scenario_rejects_non_mapping(tmp_path: Path) -> None:
    bad = tmp_path / "bad.scenario.yaml"
    bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ScenarioLoadError, match="must be a YAML mapping"):
        load_scenario(bad)


def test_prohibit_list_forces_mode(scenarios_dir: Path) -> None:
    plan = load_scenario(scenarios_dir / "plan-feature-basic.scenario.yaml")
    prohibits = [g for g in plan.goal_gates.all_gates() if g.mode == "prohibit"]
    assert prohibits and all(g.mode == "prohibit" for g in prohibits)

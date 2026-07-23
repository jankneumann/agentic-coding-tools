"""Runner loops all vendors via the fake executor and produces per-vendor results."""

from __future__ import annotations

from pathlib import Path

from agent_scenarios import (
    AgentScenario,
    FakeExecutor,
    Outcome,
    PRRef,
    load_scenario,
    run_scenario,
    run_scenarios,
)


def _implement_scenario() -> AgentScenario:
    return AgentScenario(
        id="fix-add",
        name="fix add",
        task_prompt="fix add()",
        skill_under_test="implement-feature",
        vendors=["claude", "codex", "grok"],
        fixture={
            "files": {"src/calc.py": "def add(a, b):\n    return a - b\n"},
            "git_init": True,
        },
        goal_gates={
            "verify": [
                {"id": "fixed", "check": "file", "path": "src/calc.py", "contains": "a \\+ b"},
                {"id": "branch", "check": "branch", "branch": "feature/fix-add"},
                {"id": "pr", "check": "pr", "pr_head": "feature/fix-add"},
            ],
            "prohibit": [
                {"id": "no-env", "check": "file", "path": ".env"},
            ],
        },
    )


def test_runner_loops_every_vendor() -> None:
    scenario = _implement_scenario()
    # claude + codex succeed; grok leaves the bug and opens no PR (fails).
    good = Outcome(
        write_files={"src/calc.py": "def add(a, b):\n    return a + b\n"},
        new_branch="feature/fix-add",
        commit_message="fix: correct add",
        pr=PRRef(number=1, head="feature/fix-add", url="http://pr/1"),
    )
    bad = Outcome(
        write_files={"src/calc.py": "def add(a, b):\n    return a - b\n"},
        commit_message="noop",
    )
    executor = FakeExecutor(
        {
            ("fix-add", "claude"): good,
            ("fix-add", "codex"): good,
            ("fix-add", "grok"): bad,
        }
    )

    matrix = run_scenario(scenario, executor)

    # One result per declared vendor — the parity matrix is structural.
    assert [r.vendor for r in matrix.results] == ["claude", "codex", "grok"]
    by_vendor = {r.vendor: r for r in matrix.results}
    assert by_vendor["claude"].deterministic_status == "pass"
    assert by_vendor["codex"].deterministic_status == "pass"
    assert by_vendor["grok"].deterministic_status == "fail"
    assert not matrix.all_vendors_pass
    # grok failed the 'fixed', 'branch', and 'pr' gates.
    failed_ids = {g.gate_id for g in by_vendor["grok"].failed_gates}
    assert {"fixed", "branch", "pr"} <= failed_ids


def test_runner_no_scripted_outcome_fails_all_vendors() -> None:
    scenario = _implement_scenario()
    executor = FakeExecutor({})  # nothing scripted -> fixture left untouched
    matrix = run_scenario(scenario, executor)
    # No vendor can pass when the agent did nothing; gates are scored against the
    # unchanged fixture and fail deterministically.
    assert not matrix.all_vendors_pass
    assert all(r.deterministic_status in ("fail", "error") for r in matrix.results)


def test_run_scenarios_over_seed_suite(scenarios_dir: Path) -> None:
    plan = load_scenario(scenarios_dir / "plan-feature-basic.scenario.yaml")
    # Script a passing plan outcome for each vendor.
    plan_ok = Outcome(
        write_files={
            "openspec/changes/add-health-check-endpoint/proposal.md": "# health check\n",
            "openspec/changes/add-health-check-endpoint/tasks.md": "- [ ] do\n",
        },
        new_branch="openspec/add-health-check-endpoint",
        commit_message="docs: scaffold change",
    )
    executor = FakeExecutor({plan.id: plan_ok})
    matrices = run_scenarios([plan], executor)
    assert len(matrices) == 1
    assert matrices[0].all_vendors_pass
    assert len(matrices[0].results) == len(plan.vendors)


def test_executor_failure_is_error_even_when_gates_pass() -> None:
    # A CLI that exits non-zero after partially editing the workspace must be scored
    # as an error, NOT a pass, even if the deterministic gates happen to pass.
    scenario = AgentScenario(
        id="partial-fail",
        name="partial fail",
        task_prompt="fix add()",
        skill_under_test="implement-feature",
        vendors=["claude"],
        fixture={
            "files": {"src/calc.py": "def add(a, b):\n    return a - b\n"},
            "git_init": True,
        },
        goal_gates={
            "verify": [
                {"id": "fixed", "check": "file", "path": "src/calc.py", "contains": "a \\+ b"},
            ],
        },
    )
    partial = Outcome(
        write_files={"src/calc.py": "def add(a, b):\n    return a + b\n"},  # gate would pass
        commit_message="fix add",
        exit_code=1,
        error="cli crashed after editing",
    )
    matrix = run_scenario(scenario, FakeExecutor({("partial-fail", "claude"): partial}))
    result = matrix.results[0]
    assert result.deterministic_status == "error"
    assert result.error is not None


def test_fixture_path_traversal_is_rejected() -> None:
    # A fixture file path that escapes the throwaway workspace must fail materialization
    # (surfaced as an error RunResult), never write outside the workspace.
    scenario = AgentScenario(
        id="evil-fixture",
        name="evil fixture",
        task_prompt="x",
        skill_under_test="implement-feature",
        vendors=["claude"],
        fixture={"files": {"../escape.txt": "pwned"}, "git_init": True},
        goal_gates={
            "verify": [{"id": "any", "check": "file", "path": "x.txt"}],
        },
    )
    matrix = run_scenario(scenario, FakeExecutor({}))
    result = matrix.results[0]
    assert result.deterministic_status == "error"
    assert "workspace" in (result.error or "").lower()

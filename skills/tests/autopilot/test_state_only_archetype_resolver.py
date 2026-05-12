"""Tests for `autopilot._resolve_phase_archetype_for_state_only`.

Spec: openspec/changes/wire-autopilot-phase-subagents/specs/skill-workflow/spec.md
      Scenario: "INIT phase records archetype despite being state-only"
Design decisions: D7.
"""

from __future__ import annotations

from typing import Any

import autopilot
import coordination_bridge
import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOPILOT_PHASE_MODEL_OVERRIDE", raising=False)


def _stub_bridge(monkeypatch: pytest.MonkeyPatch, response: dict[str, Any] | None) -> None:
    monkeypatch.setattr(
        coordination_bridge,
        "try_resolve_archetype_for_phase",
        lambda phase, signals=None, **kwargs: response,
    )


def test_resolve_state_only_init_records_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    runner_resolved: dict[str, Any] = {
        "model": "haiku",
        "system_prompt": "Execute and report.",
        "archetype": "runner",
        "reasons": ["phase=INIT maps to archetype=runner"],
    }
    _stub_bridge(monkeypatch, runner_resolved)

    state = autopilot.LoopState(change_id="demo")
    autopilot._resolve_phase_archetype_for_state_only(state, "INIT")

    assert state.phase_archetype == "runner"


def test_resolve_state_only_submit_pr_records_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    runner_resolved: dict[str, Any] = {
        "model": "haiku",
        "system_prompt": "Execute and report.",
        "archetype": "runner",
        "reasons": ["phase=SUBMIT_PR maps to archetype=runner"],
    }
    _stub_bridge(monkeypatch, runner_resolved)

    state = autopilot.LoopState(change_id="demo")
    autopilot._resolve_phase_archetype_for_state_only(state, "SUBMIT_PR")

    assert state.phase_archetype == "runner"


def test_resolve_state_only_bridge_failure_leaves_archetype_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bridge None → state.phase_archetype stays None (fallback path)."""
    _stub_bridge(monkeypatch, None)

    state = autopilot.LoopState(change_id="demo")
    autopilot._resolve_phase_archetype_for_state_only(state, "INIT")

    assert state.phase_archetype is None


def test_resolve_state_only_does_not_dispatch_subagent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolver SHALL NOT call into Agent / phase_agent.run_phase_subagent."""
    runner_resolved: dict[str, Any] = {
        "model": "haiku",
        "system_prompt": "Execute and report.",
        "archetype": "runner",
        "reasons": [],
    }
    _stub_bridge(monkeypatch, runner_resolved)

    # If a sub-agent dispatch ever happened, run_phase_subagent would be called.
    # Wire it to fail loudly so the test catches accidental dispatches.
    import phase_agent
    monkeypatch.setattr(
        phase_agent, "run_phase_subagent",
        lambda **kwargs: pytest.fail("INIT must not dispatch a sub-agent (D7)"),
    )

    state = autopilot.LoopState(change_id="demo")
    autopilot._resolve_phase_archetype_for_state_only(state, "INIT")

    assert state.phase_archetype == "runner"


def test_run_loop_calls_state_only_resolver_at_init(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """run_loop SHALL call _resolve_phase_archetype_for_state_only at INIT entry."""
    init_calls: list[str] = []

    real_resolver = autopilot._resolve_phase_archetype_for_state_only

    def spy(state: autopilot.LoopState, phase: str) -> None:
        init_calls.append(phase)
        real_resolver(state, phase)

    monkeypatch.setattr(autopilot, "_resolve_phase_archetype_for_state_only", spy)

    runner_resolved: dict[str, Any] = {
        "model": "haiku",
        "system_prompt": "Execute and report.",
        "archetype": "runner",
        "reasons": [],
    }
    _stub_bridge(monkeypatch, runner_resolved)

    change_dir = tmp_path / "change"
    change_dir.mkdir()

    # plan_fn returns 'created' to keep INIT -> PLAN moving; then iterate
    # 'failed' escalates so the loop halts quickly.
    autopilot.run_loop(
        change_id="demo",
        change_dir=change_dir,
        worktree_path=change_dir,
        state_path=change_dir / "loop-state.json",
        plan_fn=lambda state: "created",
        iterate_plan_fn=lambda state: "failed",
        cli_review_enabled=True,
        max_global_iterations=5,
    )

    # The resolver must have fired for INIT (the very first iteration).
    assert "INIT" in init_calls

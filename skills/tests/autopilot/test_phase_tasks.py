"""Tests for _PHASE_TASKS coverage of all 13 non-terminal phases.

Spec: openspec/changes/add-per-phase-archetype-resolution/specs/skill-workflow/spec.md
      Requirement: Per-Phase Archetype Resolution in Autopilot, scenario
      "All 13 non-terminal phases dispatch with resolved archetype".
Design decisions: D6 (extend _PHASE_TASKS), D13 (INIT/SUBMIT_PR state-only).
"""

from __future__ import annotations

import phase_agent
import pytest

_ACTIVE_PHASES = (
    "PLAN",
    "PLAN_ITERATE",
    "PLAN_REVIEW",
    "PLAN_FIX",
    "IMPLEMENT",
    "IMPL_ITERATE",
    "IMPL_REVIEW",
    "IMPL_FIX",
    "VALIDATE",
    "VAL_REVIEW",
    "VAL_FIX",
)
_STATE_ONLY_PHASES = ("INIT", "SUBMIT_PR")
_ALL_PHASES = _ACTIVE_PHASES + _STATE_ONLY_PHASES


def test_phase_tasks_covers_all_13_phases() -> None:
    for phase in _ALL_PHASES:
        assert phase in phase_agent._PHASE_TASKS, f"_PHASE_TASKS missing entry for {phase}"


@pytest.mark.parametrize("phase", _ACTIVE_PHASES)
def test_active_phases_have_string_task(phase: str) -> None:
    entry = phase_agent._PHASE_TASKS[phase]
    assert isinstance(entry, str), f"{phase}: expected str task, got {type(entry).__name__}"
    assert entry.strip(), f"{phase}: task string is empty"


@pytest.mark.parametrize("phase", _STATE_ONLY_PHASES)
def test_state_only_phases_have_none_sentinel(phase: str) -> None:
    """D13: INIT and SUBMIT_PR are state-only — _PHASE_TASKS entry is None."""
    assert phase_agent._PHASE_TASKS[phase] is None


def test_phase_task_instructions_returns_string_for_active_phase() -> None:
    """_phase_task_instructions resolves the string task for active phases."""
    text = phase_agent._phase_task_instructions("IMPLEMENT")
    assert isinstance(text, str)
    assert "implement" in text.lower() or "tasks.md" in text.lower()


def test_phase_task_instructions_unknown_phase_falls_back() -> None:
    """Backward-compat: unknown phase still returns a generic string."""
    text = phase_agent._phase_task_instructions("BOGUS_PHASE")
    assert isinstance(text, str)
    assert "BOGUS_PHASE" in text

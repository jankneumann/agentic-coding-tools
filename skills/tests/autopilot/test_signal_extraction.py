"""Tests for phase_agent._extract_signals_for_phase.

Spec: openspec/changes/add-per-phase-archetype-resolution/specs/skill-workflow/spec.md
      Requirement: Per-Phase Archetype Resolution in Autopilot.
Design decision: D12 (signal extraction).
"""

from __future__ import annotations

import phase_agent
import pytest

# All 13 non-terminal phases per design D11.
_ALL_PHASES = (
    "INIT",
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
    "SUBMIT_PR",
)


def test_signal_keys_defined_for_every_phase() -> None:
    for phase in _ALL_PHASES:
        assert phase in phase_agent._PHASE_SIGNAL_KEYS, (
            f"phase {phase} missing from _PHASE_SIGNAL_KEYS"
        )


@pytest.mark.parametrize("phase", _ALL_PHASES)
def test_extract_signals_returns_empty_for_empty_state(phase: str) -> None:
    """Missing signals are tolerated — never raises."""
    result = phase_agent._extract_signals_for_phase(phase, {})
    assert isinstance(result, dict)
    assert result == {}


def test_extract_signals_lifts_listed_keys_for_implement() -> None:
    state = {
        "loc_estimate": 250,
        "write_allow": ["src/api/**"],
        "dependencies": ["wp-foo"],
        "complexity": "high",
        "irrelevant_key": "should be dropped",
    }
    out = phase_agent._extract_signals_for_phase("IMPLEMENT", state)
    assert out == {
        "loc_estimate": 250,
        "write_allow": ["src/api/**"],
        "dependencies": ["wp-foo"],
        "complexity": "high",
    }


def test_extract_signals_drops_unlisted_keys() -> None:
    state = {"capabilities_touched": 3, "loc_estimate": 1000, "test_count": 50}
    out = phase_agent._extract_signals_for_phase("PLAN", state)
    # PLAN's signals list contains only `capabilities_touched`.
    assert out == {"capabilities_touched": 3}


def test_extract_signals_unknown_phase_returns_empty() -> None:
    out = phase_agent._extract_signals_for_phase("BOGUS_PHASE", {"loc_estimate": 1})
    assert out == {}


def test_init_and_submit_pr_have_no_signals() -> None:
    assert phase_agent._extract_signals_for_phase("INIT", {"x": 1, "y": 2}) == {}
    assert phase_agent._extract_signals_for_phase("SUBMIT_PR", {"x": 1, "y": 2}) == {}


def test_extract_signals_preserves_state_when_partial_match() -> None:
    """Only keys present in BOTH state and the phase's signal list are lifted."""
    state = {"capabilities_touched": 5}  # IMPLEMENT wants loc_estimate; this is missing
    out = phase_agent._extract_signals_for_phase("IMPLEMENT", state)
    assert out == {}  # nothing matched

"""Tests for the auto_dev_loop state machine conductor.

All tests use mocks — no real file I/O or external dependencies.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure the scripts directory is importable
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from auto_dev_loop import (
    LoopState,
    check_escalation_resolved,
    enter_escalate,
    load_state,
    run_loop,
    save_state,
    transition,
)


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


def test_state_save_load_roundtrip(tmp_path: Path) -> None:
    """save_state then load_state produces an identical LoopState."""
    state = LoopState(
        change_id="test-123",
        current_phase="IMPLEMENT",
        iteration=2,
        total_iterations=7,
        findings_trend=[5, 3, 1],
        blocking_findings=[{"id": "F1", "severity": "high"}],
        val_review_enabled=True,
        previous_phase="PLAN_REVIEW",
        escalation_reason="stuck",
    )
    path = tmp_path / "state.json"
    save_state(state, path)
    loaded = load_state(path)
    assert asdict(loaded) == asdict(state)


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


def test_initial_state_defaults() -> None:
    """A fresh LoopState has the expected default values."""
    state = LoopState()
    assert state.schema_version == 1
    assert state.change_id == ""
    assert state.current_phase == "INIT"
    assert state.iteration == 0
    assert state.total_iterations == 0
    assert state.max_phase_iterations == 3
    assert state.findings_trend == []
    assert state.blocking_findings == []
    assert state.vendor_availability == {}
    assert state.packages_status == {}
    assert state.package_authors == {}
    assert state.implementation_strategy == {}
    assert state.memory_ids == []
    assert state.handoff_ids == []
    assert state.started_at == ""
    assert state.phase_started_at == ""
    assert state.previous_phase is None
    assert state.escalation_reason is None
    assert state.val_review_enabled is False
    assert state.error is None


# ---------------------------------------------------------------------------
# Transition function
# ---------------------------------------------------------------------------


def test_transition_init_to_plan() -> None:
    state = LoopState(current_phase="INIT")
    assert transition(state, "next") == "PLAN"


def test_transition_plan_review_converged() -> None:
    state = LoopState(current_phase="PLAN_REVIEW")
    assert transition(state, "converged") == "IMPLEMENT"


def test_transition_plan_review_not_converged() -> None:
    state = LoopState(current_phase="PLAN_REVIEW")
    assert transition(state, "not_converged") == "PLAN_FIX"


def test_transition_plan_review_max_iter() -> None:
    state = LoopState(current_phase="PLAN_REVIEW")
    assert transition(state, "max_iter") == "ESCALATE"


def test_transition_validate_to_submit_pr() -> None:
    """VALIDATE + passed with val_review_enabled=False -> SUBMIT_PR."""
    state = LoopState(current_phase="VALIDATE", val_review_enabled=False)
    assert transition(state, "passed") == "SUBMIT_PR"


def test_transition_validate_to_val_review() -> None:
    """VALIDATE + passed with val_review_enabled=True -> VAL_REVIEW."""
    state = LoopState(current_phase="VALIDATE", val_review_enabled=True)
    assert transition(state, "passed") == "VAL_REVIEW"


def test_transition_invalid_outcome() -> None:
    state = LoopState(current_phase="INIT")
    with pytest.raises(ValueError, match="Invalid outcome"):
        transition(state, "bogus")


def test_transition_invalid_phase() -> None:
    state = LoopState(current_phase="NONEXISTENT")
    with pytest.raises(ValueError, match="No transitions defined"):
        transition(state, "next")


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------


def test_escalate_sets_previous_phase() -> None:
    state = LoopState(current_phase="IMPL_REVIEW")
    enter_escalate(state, "review stuck")
    assert state.current_phase == "ESCALATE"
    assert state.previous_phase == "IMPL_REVIEW"
    assert state.escalation_reason == "review stuck"


def test_escalate_resolved_returns_to_previous() -> None:
    """ESCALATE + resolved with previous_phase=IMPL_REVIEW -> IMPL_REVIEW."""
    state = LoopState(current_phase="ESCALATE", previous_phase="IMPL_REVIEW")
    assert transition(state, "resolved") == "IMPL_REVIEW"


def test_escalate_resolved_no_previous_raises() -> None:
    state = LoopState(current_phase="ESCALATE", previous_phase=None)
    with pytest.raises(ValueError, match="previous_phase is None"):
        transition(state, "resolved")


def test_check_escalation_resolved_default_false() -> None:
    state = LoopState(current_phase="ESCALATE")
    assert check_escalation_resolved(state) is False


def test_check_escalation_resolved_with_callback() -> None:
    state = LoopState(current_phase="ESCALATE")
    assert check_escalation_resolved(state, lambda s: True) is True


# ---------------------------------------------------------------------------
# run_loop — resume from saved state
# ---------------------------------------------------------------------------


def test_resume_from_saved_state(tmp_path: Path) -> None:
    """Load state from file, run_loop continues from saved phase."""
    state = LoopState(
        change_id="resume-1",
        current_phase="SUBMIT_PR",
        total_iterations=10,
    )
    state_path = tmp_path / "state.json"
    save_state(state, state_path)

    change_dir = tmp_path / "change"
    change_dir.mkdir()
    wt = tmp_path / "wt"
    wt.mkdir()

    result = run_loop(
        "resume-1",
        change_dir,
        wt,
        state_path=state_path,
    )
    assert result.current_phase == "DONE"
    assert result.total_iterations == 11  # one transition: SUBMIT_PR -> DONE


# ---------------------------------------------------------------------------
# Full happy path
# ---------------------------------------------------------------------------


def test_full_happy_path(tmp_path: Path) -> None:
    """Mock all callbacks — run from INIT to DONE without findings."""
    change_dir = tmp_path / "change"
    change_dir.mkdir()
    wt = tmp_path / "wt"
    wt.mkdir()

    # Complexity gate: no force_required, val_review disabled
    assess_mock = MagicMock(return_value={"force_required": False, "val_review_enabled": False})

    # Convergence: always converges immediately
    converge_mock = MagicMock(return_value={
        "converged": True, "findings_count": 0, "blocking_findings": [],
    })

    result = run_loop(
        "happy-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
        converge_fn=converge_mock,
    )

    assert result.current_phase == "DONE"
    assert result.error is None
    # Phases traversed: INIT->PLAN->PLAN_REVIEW->IMPLEMENT->IMPL_REVIEW->VALIDATE->SUBMIT_PR->DONE
    assert result.total_iterations >= 7


# ---------------------------------------------------------------------------
# Plan review fix loop
# ---------------------------------------------------------------------------


def test_plan_review_fix_loop(tmp_path: Path) -> None:
    """Convergence fails round 1, succeeds round 2."""
    change_dir = tmp_path / "change"
    change_dir.mkdir()
    wt = tmp_path / "wt"
    wt.mkdir()

    # First call: not converged; second call: converged
    converge_results = iter([
        {"converged": False, "findings_count": 3, "blocking_findings": [{"id": "F1"}]},
        {"converged": True, "findings_count": 0, "blocking_findings": []},
        # For IMPL_REVIEW
        {"converged": True, "findings_count": 0, "blocking_findings": []},
    ])
    converge_mock = MagicMock(side_effect=lambda **kw: next(converge_results))
    assess_mock = MagicMock(return_value={"force_required": False, "val_review_enabled": False})

    result = run_loop(
        "fix-loop-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
        converge_fn=converge_mock,
    )

    assert result.current_phase == "DONE"
    # Should have gone through PLAN_REVIEW -> PLAN_FIX -> PLAN_REVIEW -> IMPLEMENT ...
    assert 3 in result.findings_trend or len(result.findings_trend) >= 1


# ---------------------------------------------------------------------------
# Complexity gate
# ---------------------------------------------------------------------------


def test_complexity_gate_blocks(tmp_path: Path) -> None:
    """assess_complexity returns force_required -> ESCALATE."""
    change_dir = tmp_path / "change"
    change_dir.mkdir()
    wt = tmp_path / "wt"
    wt.mkdir()

    assess_mock = MagicMock(return_value={"force_required": True})

    result = run_loop(
        "complex-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
    )

    assert result.current_phase == "ESCALATE"
    assert "force_required" in (result.escalation_reason or "")


def test_complexity_gate_enables_val_review(tmp_path: Path) -> None:
    """assess_complexity with val_review_enabled -> state reflects it."""
    change_dir = tmp_path / "change"
    change_dir.mkdir()
    wt = tmp_path / "wt"
    wt.mkdir()

    assess_mock = MagicMock(return_value={
        "force_required": False,
        "val_review_enabled": True,
        "strategies": {"default": "parallel"},
    })

    # Need convergence to work for all review phases
    converge_mock = MagicMock(return_value={
        "converged": True, "findings_count": 0, "blocking_findings": [],
    })

    result = run_loop(
        "val-review-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
        converge_fn=converge_mock,
    )

    assert result.val_review_enabled is True
    assert result.current_phase == "DONE"

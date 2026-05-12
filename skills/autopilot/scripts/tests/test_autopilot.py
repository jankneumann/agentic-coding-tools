"""Tests for the autopilot state machine conductor.

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

from autopilot import (
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
    assert state.schema_version == 3  # bumped 2->3 by add-per-phase-archetype-resolution
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


def test_transition_plan_to_plan_iterate() -> None:
    """PLAN -> PLAN_ITERATE (always, regardless of cli_review_enabled)."""
    state = LoopState(current_phase="PLAN")
    assert transition(state, "exists") == "PLAN_ITERATE"
    assert transition(state, "created") == "PLAN_ITERATE"


def test_transition_plan_iterate_to_plan_review_cli() -> None:
    """PLAN_ITERATE -> PLAN_REVIEW when cli_review_enabled=True."""
    state = LoopState(current_phase="PLAN_ITERATE", cli_review_enabled=True)
    assert transition(state, "complete") == "PLAN_REVIEW"


def test_transition_plan_iterate_to_implement_no_cli() -> None:
    """PLAN_ITERATE -> IMPLEMENT when cli_review_enabled=False."""
    state = LoopState(current_phase="PLAN_ITERATE", cli_review_enabled=False)
    assert transition(state, "complete") == "IMPLEMENT"


def test_transition_plan_iterate_failed() -> None:
    state = LoopState(current_phase="PLAN_ITERATE")
    assert transition(state, "failed") == "ESCALATE"


def test_transition_plan_review_converged() -> None:
    state = LoopState(current_phase="PLAN_REVIEW")
    assert transition(state, "converged") == "IMPLEMENT"


def test_transition_plan_review_not_converged() -> None:
    state = LoopState(current_phase="PLAN_REVIEW")
    assert transition(state, "not_converged") == "PLAN_FIX"


def test_transition_plan_review_max_iter() -> None:
    state = LoopState(current_phase="PLAN_REVIEW")
    assert transition(state, "max_iter") == "ESCALATE"


def test_transition_implement_to_impl_iterate() -> None:
    """IMPLEMENT -> IMPL_ITERATE (always)."""
    state = LoopState(current_phase="IMPLEMENT")
    assert transition(state, "complete") == "IMPL_ITERATE"


def test_transition_impl_iterate_to_impl_review_cli() -> None:
    """IMPL_ITERATE -> IMPL_REVIEW when cli_review_enabled=True."""
    state = LoopState(current_phase="IMPL_ITERATE", cli_review_enabled=True)
    assert transition(state, "complete") == "IMPL_REVIEW"


def test_transition_impl_iterate_to_validate_no_cli() -> None:
    """IMPL_ITERATE -> VALIDATE when cli_review_enabled=False."""
    state = LoopState(current_phase="IMPL_ITERATE", cli_review_enabled=False)
    assert transition(state, "complete") == "VALIDATE"


def test_transition_impl_iterate_failed() -> None:
    state = LoopState(current_phase="IMPL_ITERATE")
    assert transition(state, "failed") == "ESCALATE"


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
    # Phases: INIT->PLAN->PLAN_ITERATE->PLAN_REVIEW->IMPLEMENT->IMPL_ITERATE->IMPL_REVIEW->VALIDATE->SUBMIT_PR->DONE
    assert result.total_iterations >= 9


def test_full_happy_path_no_cli_review(tmp_path: Path) -> None:
    """With cli_review_enabled=False, review phases are skipped."""
    change_dir = tmp_path / "change"
    change_dir.mkdir()
    wt = tmp_path / "wt"
    wt.mkdir()

    assess_mock = MagicMock(return_value={"force_required": False, "val_review_enabled": False})

    # Convergence should NOT be called when cli_review_enabled=False
    converge_mock = MagicMock(return_value={
        "converged": True, "findings_count": 0, "blocking_findings": [],
    })

    result = run_loop(
        "no-review-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
        converge_fn=converge_mock,
        cli_review_enabled=False,
    )

    assert result.current_phase == "DONE"
    assert result.error is None
    assert result.cli_review_enabled is False
    # Phases: INIT->PLAN->PLAN_ITERATE->IMPLEMENT->IMPL_ITERATE->VALIDATE->SUBMIT_PR->DONE
    assert result.total_iterations >= 7
    # Convergence should not have been called (no review phases)
    converge_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Plan review fix loop
# ---------------------------------------------------------------------------


def test_plan_review_fix_loop(tmp_path: Path) -> None:
    """Convergence fails round 1, succeeds round 2."""
    change_dir = tmp_path / "change"
    change_dir.mkdir()
    wt = tmp_path / "wt"
    wt.mkdir()

    # First call: not converged; second call: converged (PLAN_REVIEW)
    # Third call: converged (IMPL_REVIEW)
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
    # Should have gone through PLAN_ITERATE -> PLAN_REVIEW -> PLAN_FIX -> PLAN_REVIEW -> IMPLEMENT ...
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


def test_iterate_callbacks_called(tmp_path: Path) -> None:
    """iterate_plan_fn and iterate_impl_fn are called in the loop."""
    change_dir = tmp_path / "change"
    change_dir.mkdir()
    wt = tmp_path / "wt"
    wt.mkdir()

    assess_mock = MagicMock(return_value={"force_required": False, "val_review_enabled": False})
    converge_mock = MagicMock(return_value={
        "converged": True, "findings_count": 0, "blocking_findings": [],
    })
    iterate_plan_mock = MagicMock(return_value="complete")
    iterate_impl_mock = MagicMock(return_value="complete")

    result = run_loop(
        "iterate-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
        converge_fn=converge_mock,
        iterate_plan_fn=iterate_plan_mock,
        iterate_impl_fn=iterate_impl_mock,
    )

    assert result.current_phase == "DONE"
    iterate_plan_mock.assert_called_once()
    iterate_impl_mock.assert_called_once()


def test_iterate_plan_failure_escalates(tmp_path: Path) -> None:
    """iterate_plan_fn returning 'failed' leads to ESCALATE."""
    change_dir = tmp_path / "change"
    change_dir.mkdir()
    wt = tmp_path / "wt"
    wt.mkdir()

    assess_mock = MagicMock(return_value={"force_required": False, "val_review_enabled": False})
    iterate_plan_mock = MagicMock(return_value="failed")

    result = run_loop(
        "iterate-fail-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
        iterate_plan_fn=iterate_plan_mock,
    )

    assert result.current_phase == "ESCALATE"


def test_cli_review_enabled_persisted(tmp_path: Path) -> None:
    """cli_review_enabled is saved/loaded in state."""
    state = LoopState(
        change_id="cli-1",
        current_phase="PLAN_ITERATE",
        cli_review_enabled=False,
    )
    path = tmp_path / "state.json"
    save_state(state, path)
    loaded = load_state(path)
    assert loaded.cli_review_enabled is False


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

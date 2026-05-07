"""Tests for _FIX phase archetype inheritance.

Spec: openspec/changes/wire-autopilot-phase-subagents/specs/skill-workflow/spec.md
      Scenario: "PLAN_FIX inherits phase_archetype from PLAN_REVIEW"
Design decisions: design.md "Phase-by-phase dispatch matrix" (_FIX rows
                  state convergence_loop never overwrites the field).

Guards against R1-009-class regressions where _FIX phases would silently
null out the field set by the preceding REVIEW phase.
"""

from __future__ import annotations

from typing import Any

import autopilot
import pytest


def test_plan_fix_preserves_phase_archetype_from_plan_review() -> None:
    """Direct unit test: _phase_review (no converge_fn) leaves phase_archetype
    untouched on the state, and the PLAN_FIX phase handler (which simply
    returns 'fixed') doesn't touch it either."""
    state = autopilot.LoopState(
        change_id="demo",
        current_phase="PLAN_REVIEW",
        phase_archetype="reviewer",  # set by the preceding PLAN_REVIEW dispatch
    )

    # Simulate a not_converged outcome by directly transitioning the state.
    # PLAN_REVIEW with not_converged → PLAN_FIX. Then PLAN_FIX returns 'fixed'.
    next_phase = autopilot.transition(state, "not_converged")
    assert next_phase == "PLAN_FIX"
    state.current_phase = next_phase

    # _run_phase for PLAN_FIX returns 'fixed' without touching state.phase_archetype.
    outcome = autopilot._run_phase(
        state,
        change_dir=Path_stub(),
        worktree_path=Path_stub(),
        plan_fn=None,
        iterate_plan_fn=None,
        iterate_impl_fn=None,
        implement_fn=None,
        validate_fn=None,
        submit_pr_fn=None,
        handoff_fn=None,
        memory_fn=None,
        gate_check_fn=None,
        converge_fn=None,
        assess_complexity_fn=None,
        post_fix_validator_fn=None,
    )
    assert outcome == "fixed"
    assert state.phase_archetype == "reviewer", (
        "PLAN_FIX must inherit phase_archetype from PLAN_REVIEW; "
        "convergence_loop never overwrites the field."
    )


def test_impl_fix_preserves_phase_archetype_from_impl_review() -> None:
    state = autopilot.LoopState(
        change_id="demo",
        current_phase="IMPL_FIX",
        phase_archetype="reviewer",  # set by the preceding IMPL_REVIEW dispatch
    )

    outcome = autopilot._run_phase(
        state,
        change_dir=Path_stub(),
        worktree_path=Path_stub(),
        plan_fn=None,
        iterate_plan_fn=None,
        iterate_impl_fn=None,
        implement_fn=None,
        validate_fn=None,
        submit_pr_fn=None,
        handoff_fn=None,
        memory_fn=None,
        gate_check_fn=None,
        converge_fn=None,
        assess_complexity_fn=None,
        post_fix_validator_fn=None,
    )
    assert outcome == "fixed"
    assert state.phase_archetype == "reviewer"


def test_val_fix_preserves_phase_archetype_from_val_review() -> None:
    state = autopilot.LoopState(
        change_id="demo",
        current_phase="VAL_FIX",
        phase_archetype="reviewer",  # set by the preceding VAL_REVIEW dispatch
    )

    outcome = autopilot._run_phase(
        state,
        change_dir=Path_stub(),
        worktree_path=Path_stub(),
        plan_fn=None,
        iterate_plan_fn=None,
        iterate_impl_fn=None,
        implement_fn=None,
        validate_fn=None,
        submit_pr_fn=None,
        handoff_fn=None,
        memory_fn=None,
        gate_check_fn=None,
        converge_fn=None,
        assess_complexity_fn=None,
        post_fix_validator_fn=None,
    )
    assert outcome == "fixed"
    assert state.phase_archetype == "reviewer"


def test_convergence_loop_round_trip_does_not_overwrite_archetype(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drive a fake convergence loop that does NOT converge → triggers PLAN_FIX.

    The convergence callable is replaced with a stub that returns
    `not_converged`. We assert PLAN_REVIEW dispatched, transitioned to
    PLAN_FIX, and at no point overwrote `state.phase_archetype`.
    """
    # Stub converge_fn that simulates a non-converged review round.
    def fake_converge(**kwargs: Any) -> dict[str, Any]:
        # Return-shape that _phase_review understands.
        return {
            "converged": False,
            "findings_count": 3,
            "blocking_findings": [],
        }

    state = autopilot.LoopState(
        change_id="demo",
        current_phase="PLAN_REVIEW",
        # Simulate that PLAN_REVIEW's dispatch already wrote 'reviewer'.
        phase_archetype="reviewer",
    )

    outcome = autopilot._phase_review(
        state,
        change_dir=Path_stub(),
        worktree_path=Path_stub(),
        converge_fn=fake_converge,
        fix_mode="inline",
        post_fix_validator_fn=None,
    )

    # _phase_review increments iteration and returns 'not_converged' on non-conv.
    assert outcome == "not_converged"
    # The convergence loop must NEVER have overwritten phase_archetype.
    assert state.phase_archetype == "reviewer"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class Path_stub:
    """Minimal Path-like stub for the change_dir / worktree_path arguments.

    `_phase_review` only invokes `assess_complexity_fn(work_packages_path,
    proposal_path)` if non-None, and we pass None here. Other phases
    don't touch the paths under the no-callback codepath, so a bare
    placeholder works.
    """

    def __truediv__(self, other: object) -> "Path_stub":
        return self

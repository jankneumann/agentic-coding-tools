"""Contract tests for `runner.py apply-outcome` and the D9 escalation wrapper.

Spec: openspec/changes/fix-autopilot-archetype-and-apply-outcome/specs/
      skill-workflow/spec.md
      Requirements:
        - "`apply-outcome` Does Not Transition `current_phase`"
        - "apply-outcome failure transitions orchestrator to ESCALATE"

Covers Task 7.2-7.6:
  - apply-outcome updates last_handoff_id but never current_phase.
  - a --phase mismatch errors out mentioning --allow-phase-mismatch.
  - --allow-phase-mismatch bypasses the guard but still never touches
    current_phase.
  - the orchestrator's apply_outcome_or_escalate wrapper transitions to
    ESCALATE (and retains the handoff) when apply-outcome exits non-zero.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import autopilot
import phase_agent
import pytest

_WRITE_CAPABLE_PHASES = [
    "PLAN", "PLAN_ITERATE", "PLAN_REVIEW", "PLAN_FIX",
    "IMPLEMENT", "IMPL_ITERATE", "IMPL_REVIEW", "IMPL_FIX",
    "VALIDATE", "VAL_REVIEW", "VAL_FIX",
]


def _seed_state(repo_root: Path, change_id: str, **overrides: Any) -> Path:
    change_dir = repo_root / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {
        "schema_version": 4,
        "change_id": change_id,
        "current_phase": "IMPLEMENT",
        "handoff_ids": [],
        "last_handoff_id": None,
        "previous_phase": None,
        "phase_archetype": None,
        "phase_history": [],
    }
    state.update(overrides)
    state_path = change_dir / "loop-state.json"
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    return state_path


@pytest.fixture()
def chdir_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# 7.2 — match succeeds, updates last_handoff_id, NOT current_phase
# ---------------------------------------------------------------------------


def test_apply_outcome_match_updates_handoff_not_phase(chdir_tmp: Path) -> None:
    state_path = _seed_state(chdir_tmp, "demo", current_phase="IMPLEMENT")

    phase_agent.apply_phase_outcome(
        change_id="demo", phase="IMPLEMENT", outcome="complete", handoff_id="h-1",
    )

    state = json.loads(state_path.read_text())
    assert state["current_phase"] == "IMPLEMENT"  # unchanged
    assert state["last_handoff_id"] == "h-1"
    assert state["handoff_ids"] == ["h-1"]
    # phase_history appended with the outcome.
    assert state["phase_history"][-1]["phase"] == "IMPLEMENT"
    assert state["phase_history"][-1]["outcome"] == "complete"


# ---------------------------------------------------------------------------
# 7.3 — mismatch errors out, mentions --allow-phase-mismatch, state untouched
# ---------------------------------------------------------------------------


def test_apply_outcome_phase_mismatch_raises(chdir_tmp: Path) -> None:
    state_path = _seed_state(chdir_tmp, "demo", current_phase="IMPLEMENT")
    before = state_path.read_text()

    with pytest.raises(ValueError) as exc:
        phase_agent.apply_phase_outcome(
            change_id="demo", phase="PLAN_REVIEW", outcome="converged",
            handoff_id="h-2",
        )

    assert "--allow-phase-mismatch" in str(exc.value)
    assert "IMPLEMENT" in str(exc.value) and "PLAN_REVIEW" in str(exc.value)
    # loop-state untouched.
    assert state_path.read_text() == before


def test_runner_cli_phase_mismatch_exits_nonzero(chdir_tmp: Path) -> None:
    """The runner CLI surfaces the guard as a non-zero exit + stderr message."""
    import runner

    _seed_state(chdir_tmp, "demo", current_phase="IMPLEMENT")
    rc = runner.main([
        "apply-outcome", "--change-id", "demo", "--phase", "VALIDATE",
        "--outcome", "failed", "--handoff-id", "h-x",
    ])
    assert rc != 0


# ---------------------------------------------------------------------------
# 7.4 — --allow-phase-mismatch bypasses guard, still no current_phase change
# ---------------------------------------------------------------------------


def test_allow_phase_mismatch_bypasses_but_no_transition(chdir_tmp: Path) -> None:
    state_path = _seed_state(chdir_tmp, "demo", current_phase="IMPLEMENT")

    phase_agent.apply_phase_outcome(
        change_id="demo", phase="PLAN_REVIEW", outcome="converged",
        handoff_id="h-3", allow_phase_mismatch=True,
    )

    state = json.loads(state_path.read_text())
    assert state["current_phase"] == "IMPLEMENT"  # still untouched
    assert state["last_handoff_id"] == "h-3"


# ---------------------------------------------------------------------------
# 7.5 — never modifies current_phase, all write-capable phases, both flags
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("phase", _WRITE_CAPABLE_PHASES)
@pytest.mark.parametrize("allow", [False, True])
def test_apply_outcome_never_modifies_current_phase(
    chdir_tmp: Path, phase: str, allow: bool
) -> None:
    # current_phase == phase so the guard passes even when allow=False.
    state_path = _seed_state(chdir_tmp, "demo", current_phase=phase)

    phase_agent.apply_phase_outcome(
        change_id="demo", phase=phase, outcome="complete",
        handoff_id="h-loop", allow_phase_mismatch=allow,
    )

    state = json.loads(state_path.read_text())
    assert state["current_phase"] == phase


# ---------------------------------------------------------------------------
# 7.6 — D9: apply-outcome non-zero exit -> orchestrator escalates + retains
# ---------------------------------------------------------------------------


def test_apply_outcome_failure_escalates_and_retains_handoff(chdir_tmp: Path) -> None:
    state_path = _seed_state(chdir_tmp, "demo", current_phase="IMPLEMENT")
    # Simulate a handoff file that must be retained.
    handoffs_dir = chdir_tmp / "openspec" / "changes" / "demo" / "handoffs"
    handoffs_dir.mkdir(parents=True, exist_ok=True)
    handoff_file = handoffs_dir / "h-fail.json"
    handoff_file.write_text('{"phase": "IMPLEMENT"}')

    def failing_runner(**_kwargs: Any) -> int:
        return 1  # simulate apply-outcome non-zero exit

    rc = autopilot.apply_outcome_or_escalate(
        change_id="demo", phase="IMPLEMENT", outcome="complete",
        handoff_id=str(handoff_file), state_path=state_path,
        apply_runner=failing_runner,
    )

    assert rc == 1
    state = json.loads(state_path.read_text())
    assert state["current_phase"] == "ESCALATE"
    assert state["previous_phase"] == "IMPLEMENT"
    # handoff retained.
    assert handoff_file.exists()
    # failure recorded in phase_history.
    assert any(
        e.get("outcome") == "apply_outcome_failed" for e in state["phase_history"]
    )


def test_apply_outcome_success_does_not_escalate(chdir_tmp: Path) -> None:
    state_path = _seed_state(chdir_tmp, "demo", current_phase="IMPLEMENT")

    def ok_runner(**_kwargs: Any) -> int:
        return 0

    rc = autopilot.apply_outcome_or_escalate(
        change_id="demo", phase="IMPLEMENT", outcome="complete",
        handoff_id="h-ok", state_path=state_path, apply_runner=ok_runner,
    )

    assert rc == 0
    state = json.loads(state_path.read_text())
    assert state["current_phase"] == "IMPLEMENT"

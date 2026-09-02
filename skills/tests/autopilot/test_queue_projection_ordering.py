"""Persist-first optional queue projection seam."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import autopilot

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.approval_gate import ApprovalDecision, Outcome, Resolution  # noqa: E402
from shared.trust_posture import Disposition, Gate  # noqa: E402


def _state() -> autopilot.LoopState:
    return autopilot.LoopState(
        change_id="ri-08",
        current_phase="IMPLEMENT",
        total_iterations=9,
    )


class _AutoProceedGateEvaluator:
    """A gate evaluator that always proceeds.

    Used to exercise ESCALATE-bound edges (GATEKEEPER escalation, PR/merge
    gates ahead of a goal-gate refusal) without a TRUST_POSTURE.md on disk —
    the real default evaluator fails closed (blocks) with none present.
    """

    def evaluate(self, gate: Gate, context: dict | None = None) -> ApprovalDecision:
        return ApprovalDecision(
            gate=gate,
            outcome=Outcome.PROCEED,
            resolution=Resolution.AUTO,
            disposition=Disposition.AUTO,
            reason="test-auto-proceed",
            posture_present=True,
        )


def test_persist_completes_before_projection_and_response_is_non_authoritative(
    tmp_path: Path,
) -> None:
    path = tmp_path / "loop-state.json"
    state = _state()

    def project(received: autopilot.LoopState, *, mode: str):
        on_disk = json.loads(path.read_text())
        assert on_disk["current_phase"] == "IMPLEMENT"
        assert mode == "submit"
        return {"phase": "DONE", "transition_sequence": 999}

    result = autopilot.persist_and_project(state, path, project, mode="submit")

    assert result["status"] == "ok"
    assert state.current_phase == "IMPLEMENT"
    assert state.total_iterations == 9


def test_save_failure_short_circuits_projection(monkeypatch, tmp_path: Path) -> None:
    called = False

    def fail_save(*_args):
        raise OSError("disk full")

    def project(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(autopilot, "save_state", fail_save)
    with pytest.raises(OSError, match="disk full"):
        autopilot.persist_and_project(_state(), tmp_path / "state.json", project)
    assert called is False


def test_projection_failure_leaves_state_durable(tmp_path: Path) -> None:
    path = tmp_path / "loop-state.json"

    def fail(*_args, **_kwargs):
        raise RuntimeError("offline")

    result = autopilot.persist_and_project(_state(), path, fail)

    assert json.loads(path.read_text())["total_iterations"] == 9
    assert result["status"] == "failed"
    assert result["reason"] == "projection_failed"


def test_resume_reconciles_loaded_state_before_phase_execution(tmp_path: Path) -> None:
    path = tmp_path / "loop-state.json"
    state = _state()
    autopilot.save_state(state, path)
    calls: list[tuple[str, str, int, int]] = []

    def project(received: autopilot.LoopState, *, mode: str):
        calls.append(
            (
                mode,
                received.current_phase,
                received.total_iterations,
                received.iteration,
            )
        )
        return {"phase": "DONE", "transition_sequence": 999}

    result = autopilot.run_loop(
        "ri-08",
        tmp_path,
        tmp_path,
        state_path=path,
        queue_projection_fn=project,
        max_global_iterations=state.total_iterations,
    )

    assert calls == [("reconcile", "IMPLEMENT", 9, state.iteration)]
    assert result.current_phase == "IMPLEMENT"
    assert result.total_iterations == 9


def test_phase_transition_persists_before_submit_projection(tmp_path: Path) -> None:
    path = tmp_path / "loop-state.json"
    state = _state()
    state.total_iterations = 0
    autopilot.save_state(state, path)
    calls: list[tuple[str, str, int]] = []

    def project(received: autopilot.LoopState, *, mode: str):
        on_disk = json.loads(path.read_text())
        assert on_disk["current_phase"] == received.current_phase
        assert on_disk["total_iterations"] == received.total_iterations
        calls.append((mode, received.current_phase, received.total_iterations))
        return {"success": True}

    result = autopilot.run_loop(
        "ri-08",
        tmp_path,
        tmp_path,
        state_path=path,
        implement_fn=lambda _state: "complete",
        queue_projection_fn=project,
        max_global_iterations=1,
    )

    assert result.current_phase == "IMPL_ITERATE"
    assert calls == [
        ("reconcile", "IMPLEMENT", 0),
        ("submit", "IMPL_ITERATE", 1),
    ]


def test_callback_absence_has_no_projection_side_effect(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "loop-state.json"
    autopilot.save_state(_state(), path)
    monkeypatch.setattr(
        autopilot,
        "persist_and_project",
        lambda *_args, **_kwargs: pytest.fail("projection seam invoked"),
    )

    autopilot.run_loop(
        "ri-08",
        tmp_path,
        tmp_path,
        state_path=path,
        max_global_iterations=9,
    )


# ---------------------------------------------------------------------------
# Escalation paths must also reach the projection seam (VAL_FIX finding 2).
#
# Before this fix, only the ordinary "phase advanced" branch called
# persist_and_project; the exception handler, the "phase handler already
# changed current_phase" branch (e.g. enter_escalate called inside a phase
# handler), and the GoalGateRefused handler all persisted with plain
# save_state() and never reached the projection callback. A coordinated run
# could therefore enter ESCALATE durably while the previous queue generation
# stayed active.
# ---------------------------------------------------------------------------


def test_exception_branch_projects_the_escalate_transition(tmp_path: Path) -> None:
    """An exception raised inside a phase handler still projects ESCALATE."""
    path = tmp_path / "loop-state.json"
    state = autopilot.LoopState(
        change_id="ri-08", current_phase="IMPLEMENT", total_iterations=0,
    )
    autopilot.save_state(state, path)
    calls: list[tuple[str, str]] = []

    def project(received: autopilot.LoopState, *, mode: str):
        calls.append((mode, received.current_phase))
        return {"status": "ok"}

    def boom(_state: autopilot.LoopState) -> str:
        raise RuntimeError("boom")

    result = autopilot.run_loop(
        "ri-08",
        tmp_path,
        tmp_path,
        state_path=path,
        implement_fn=boom,
        queue_projection_fn=project,
        max_global_iterations=1,
    )

    assert result.current_phase == "ESCALATE"
    assert result.error is not None
    assert ("submit", "ESCALATE") in calls


def test_phase_raise_branch_projects_the_escalate_transition(tmp_path: Path) -> None:
    """A phase handler that calls enter_escalate itself still projects.

    _phase_gatekeeper calls enter_escalate() directly (rather than returning
    an outcome the normal transition table resolves), which the run loop
    detects as "state.current_phase != phase" and used to persist with plain
    save_state().
    """
    path = tmp_path / "loop-state.json"
    change_dir = tmp_path / "change"
    change_dir.mkdir()
    worktree = tmp_path / "wt"
    worktree.mkdir()
    calls: list[tuple[str, str]] = []

    def project(received: autopilot.LoopState, *, mode: str):
        calls.append((mode, received.current_phase))
        return {"status": "ok"}

    result = autopilot.run_loop(
        "ri-08",
        change_dir,
        worktree,
        state_path=path,
        gatekeeper_fn=lambda _s: "escalate",
        assess_complexity_fn=lambda **_kw: {
            "force_required": False,
            "signals": {"has_security_signal": True},
        },
        gate_check_fn=lambda _s: False,
        gate_evaluator=_AutoProceedGateEvaluator(),
        queue_projection_fn=project,
        max_global_iterations=2,
    )

    assert result.current_phase == "ESCALATE"
    assert result.previous_phase == "GATEKEEPER"
    assert ("submit", "ESCALATE") in calls


def test_goal_gate_refusal_branch_projects_the_escalate_transition(tmp_path: Path) -> None:
    """A GoalGateRefused raised out of _apply_transition still projects."""
    path = tmp_path / "loop-state.json"
    change_dir = tmp_path / "change"
    change_dir.mkdir()
    (change_dir / "proposal.md").write_text("---\ndeployable: false\n---\n\n# Proposal\n")
    (change_dir / "validation-report.md").write_text(
        "# Validation Report\n\n"
        "## Spec Compliance\n\n**Status**: pass\n\n"
        "## Validation Review\n\n**Status**: pass\n"
    )
    worktree = tmp_path / "wt"
    worktree.mkdir()

    # No VALIDATE-passed phase_history entry, so the goal gate refuses the
    # SUBMIT_PR -> DONE edge with GoalGateRefused.
    state = autopilot.LoopState(
        change_id="ri-08", current_phase="SUBMIT_PR", total_iterations=0,
    )
    autopilot.save_state(state, path)
    calls: list[tuple[str, str]] = []

    def project(received: autopilot.LoopState, *, mode: str):
        calls.append((mode, received.current_phase))
        return {"status": "ok"}

    result = autopilot.run_loop(
        "ri-08",
        change_dir,
        worktree,
        state_path=path,
        gate_evaluator=_AutoProceedGateEvaluator(),
        queue_projection_fn=project,
        max_global_iterations=1,
    )

    assert result.current_phase == "ESCALATE"
    assert result.escalation_reason is not None
    assert "goal gate refused" in result.escalation_reason
    assert ("submit", "ESCALATE") in calls


# ---------------------------------------------------------------------------
# persist_and_project must classify non-raising failure envelopes
# (VAL_FIX finding 4).
#
# The coordination-bridge helpers return structured
# {"status": "skipped"|"failed", ...} envelopes instead of raising when the
# coordinator is unreachable or refuses the payload. Before this fix,
# persist_and_project reported every non-raising callback response as
# status="ok", silently swallowing the refusal.
# ---------------------------------------------------------------------------


def test_persist_and_project_classifies_failed_envelope(tmp_path: Path) -> None:
    path = tmp_path / "loop-state.json"

    def project(_state, *, mode: str):
        return {"status": "failed", "reason": "coordinator_unreachable"}

    result = autopilot.persist_and_project(_state(), path, project)

    assert result["status"] == "failed"
    assert result["reason"] == "coordinator_unreachable"
    # State must still be durable — this is best-effort projection, not a
    # rollback of the persisted state.
    assert json.loads(path.read_text())["current_phase"] == "IMPLEMENT"


def test_persist_and_project_classifies_skipped_envelope(tmp_path: Path) -> None:
    path = tmp_path / "loop-state.json"

    def project(_state, *, mode: str):
        return {"status": "skipped", "reason": "queue_work_unavailable"}

    result = autopilot.persist_and_project(_state(), path, project)

    assert result["status"] == "skipped"
    assert result["reason"] == "queue_work_unavailable"


def test_persist_and_project_classifies_skipped_envelope_error_key(tmp_path: Path) -> None:
    """Some envelopes carry `error` rather than `reason` — either is surfaced."""
    path = tmp_path / "loop-state.json"

    def project(_state, *, mode: str):
        return {"status": "failed", "error": "HTTP 503"}

    result = autopilot.persist_and_project(_state(), path, project)

    assert result["status"] == "failed"
    assert result["reason"] == "HTTP 503"


def test_persist_and_project_logs_warning_on_non_success_envelope(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    path = tmp_path / "loop-state.json"

    def project(_state, *, mode: str):
        return {"status": "skipped", "reason": "queue_work_unavailable"}

    with caplog.at_level(logging.WARNING, logger="autopilot"):
        autopilot.persist_and_project(_state(), path, project)

    assert "skipped" in caplog.text
    assert "queue_work_unavailable" in caplog.text


def test_persist_and_project_keeps_ok_status_for_success_envelope(tmp_path: Path) -> None:
    """A success envelope (status == "ok") is unaffected by the new classification."""
    path = tmp_path / "loop-state.json"

    def project(_state, *, mode: str):
        return {"status": "ok", "task_id": "abc-123"}

    result = autopilot.persist_and_project(_state(), path, project)

    assert result["status"] == "ok"


def test_persist_and_project_keeps_ok_status_for_statusless_mapping(tmp_path: Path) -> None:
    """A mapping response with no "status" key is treated as success, matching
    the pre-existing contract (e.g. reconcile responses shaped like
    {"phase": ..., "transition_sequence": ...})."""
    path = tmp_path / "loop-state.json"

    def project(_state, *, mode: str):
        return {"phase": "DONE", "transition_sequence": 999}

    result = autopilot.persist_and_project(_state(), path, project)

    assert result["status"] == "ok"

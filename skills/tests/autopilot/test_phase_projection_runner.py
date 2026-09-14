"""RED/GREEN tests for the canonical phase-state runner boundary."""

from __future__ import annotations

import json
from pathlib import Path

import autopilot
import pytest
import queue_projection
import runner


def test_runner_init_and_transition_are_canonical_writers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.main(["init", "--change-id", "demo"]) == 0
    state_path = tmp_path / "openspec/changes/demo/loop-state.json"
    created = json.loads(state_path.read_text())
    assert created["current_phase"] == "INIT"
    assert created["total_iterations"] == 0

    created["current_phase"] = "PLAN"
    state_path.write_text(json.dumps(created))
    assert runner.main(["init", "--change-id", "demo"]) == 0
    assert json.loads(state_path.read_text())["current_phase"] == "PLAN"

    assert runner.main(["transition", "--change-id", "demo", "--outcome", "exists"]) == 0
    transitioned = json.loads(state_path.read_text())
    assert transitioned["current_phase"] == "PLAN_ITERATE"
    assert transitioned["total_iterations"] == 1


def test_runner_project_state_loads_durable_state_and_is_read_only(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.main(["init", "--change-id", "demo"]) == 0
    state_path = tmp_path / "openspec/changes/demo/loop-state.json"
    before = state_path.read_bytes()
    captured: dict[str, object] = {}

    class FakeAdapter:
        def __init__(self, **kwargs):
            captured["config"] = kwargs

        def __call__(self, state, *, mode):
            captured["identity"] = (
                state.change_id,
                state.current_phase,
                state.total_iterations,
            )
            captured["mode"] = mode
            return {"status": "ok", "task_id": "phase-row", "cleaned": 0}

    monkeypatch.setattr(queue_projection, "QueueProjectionAdapter", FakeAdapter)
    assert (
        runner.main(
            [
                "project-state",
                "--change-id",
                "demo",
                "--mode",
                "reconcile",
                "--coordinator-url",
                "https://coordinator.invalid",
            ]
        )
        == 0
    )
    assert captured["identity"] == ("demo", "INIT", 0)
    assert captured["mode"] == "reconcile"
    assert state_path.read_bytes() == before


def test_crash_resume_reconcile_derives_adapter_key_only_from_durable_file(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.main(["init", "--change-id", "demo"]) == 0
    state_path = tmp_path / "openspec/changes/demo/loop-state.json"
    durable = json.loads(state_path.read_text())
    durable["current_phase"] = "VALIDATE"
    durable["total_iterations"] = 11
    state_path.write_text(json.dumps(durable))
    before = state_path.read_bytes()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        queue_projection.bridge,
        "detect_coordination",
        lambda **_kw: {
            "COORDINATOR_AVAILABLE": True,
            "COORDINATION_TRANSPORT": "http",
            "CAN_QUEUE_WORK": True,
            "CAN_ISSUES": True,
        },
    )

    def reconcile(**kwargs):
        captured["key"] = kwargs["projection_key"]
        return {
            "status": "ok",
            "response": {
                "success": True,
                "task_id": "current",
                "cancelled_task_ids": ["pre-crash-generation"],
            },
        }

    monkeypatch.setattr(queue_projection.bridge, "try_reconcile_work_projection", reconcile)
    assert (
        runner.main(
            [
                "project-state",
                "--change-id",
                "demo",
                "--mode",
                "reconcile",
                "--coordinator-url",
                "https://coordinator.invalid",
            ]
        )
        == 0
    )
    assert captured["key"] == {
        "change_id": "demo",
        "phase": "VALIDATE",
        "transition_sequence": 11,
    }
    assert state_path.read_bytes() == before


def test_runner_transition_treats_pending_gate_as_clean_stop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.main(["init", "--change-id", "demo"]) == 0
    state_path = tmp_path / "openspec/changes/demo/loop-state.json"
    state = json.loads(state_path.read_text())
    state["pending_gate"] = {"gate": "proposal_approval"}
    state_path.write_text(json.dumps(state))

    assert runner.main(["transition", "--change-id", "demo", "--outcome", "exists"]) == 0


def test_runner_transition_validation_and_project_state_io_exit_codes(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.main(["init", "--change-id", "demo"]) == 0
    assert runner.main(["transition", "--change-id", "demo", "--outcome", "unknown"]) == 2
    assert (
        runner.main(
            [
                "project-state",
                "--change-id",
                "missing",
                "--mode",
                "submit",
                "--coordinator-url",
                "https://coordinator.invalid",
            ]
        )
        == 1
    )


@pytest.mark.parametrize(
    ("phase", "outcome"),
    [
        ("PLAN", "failed"),
        ("PLAN_ITERATE", "failed"),
        ("PLAN_REVIEW", "max_iter"),
        ("PLAN_FIX", "stuck"),
        ("IMPLEMENT", "failed"),
        ("IMPL_ITERATE", "failed"),
        ("IMPL_REVIEW", "max_iter"),
        ("IMPL_FIX", "stuck"),
        ("VAL_REVIEW", "max_iter"),
        ("VAL_FIX", "stuck"),
    ],
)
def test_every_table_transition_to_escalate_is_resumable(phase: str, outcome: str) -> None:
    state = autopilot.LoopState(
        change_id="demo",
        current_phase=phase,
        total_iterations=7,
    )

    autopilot._apply_transition(state, outcome)

    assert state.current_phase == "ESCALATE"
    assert state.previous_phase == phase
    assert state.escalation_reason
    assert state.total_iterations == 8
    autopilot._apply_transition(state, "resolved")
    assert state.current_phase == phase


def test_runner_transition_persists_goal_gate_refusal_as_escalate(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.main(["init", "--change-id", "demo"]) == 0
    state_path = tmp_path / "openspec/changes/demo/loop-state.json"
    state = json.loads(state_path.read_text())
    state["current_phase"] = "SUBMIT_PR"
    state_path.write_text(json.dumps(state))

    assert runner.main(["transition", "--change-id", "demo", "--outcome", "created"]) == 0

    refused = json.loads(state_path.read_text())
    assert refused["current_phase"] == "ESCALATE"
    assert refused["previous_phase"] == "SUBMIT_PR"
    assert "goal gate refused" in refused["escalation_reason"]
    assert refused["total_iterations"] == 1


def test_runner_project_state_reports_degraded_without_halting_authoritative_work(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.main(["init", "--change-id", "demo"]) == 0
    state_path = tmp_path / "openspec/changes/demo/loop-state.json"
    before = state_path.read_bytes()

    class DegradedAdapter:
        def __init__(self, **_kwargs):
            pass

        def __call__(self, _state, *, mode):
            assert mode == "submit"
            return {"status": "failed", "reason": "coordinator_unavailable"}

    monkeypatch.setattr(queue_projection, "QueueProjectionAdapter", DegradedAdapter)
    assert (
        runner.main(
            [
                "project-state",
                "--change-id",
                "demo",
                "--mode",
                "submit",
                "--coordinator-url",
                "https://coordinator.invalid",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "failed"
    assert state_path.read_bytes() == before

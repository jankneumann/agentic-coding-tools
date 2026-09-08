"""RED/GREEN tests for the canonical phase-state runner boundary."""

from __future__ import annotations

import json
from pathlib import Path

import queue_projection
import runner


def test_runner_init_and_transition_are_canonical_writers(
    tmp_path: Path, monkeypatch
) -> None:
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

    assert runner.main(
        ["transition", "--change-id", "demo", "--outcome", "exists"]
    ) == 0
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
    assert runner.main(
        [
            "project-state",
            "--change-id",
            "demo",
            "--mode",
            "reconcile",
            "--coordinator-url",
            "https://coordinator.invalid",
        ]
    ) == 0
    assert captured["identity"] == ("demo", "INIT", 0)
    assert captured["mode"] == "reconcile"
    assert state_path.read_bytes() == before

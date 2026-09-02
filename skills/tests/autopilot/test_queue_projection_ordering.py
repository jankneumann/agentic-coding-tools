"""Persist-first optional queue projection seam."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import autopilot


def _state() -> autopilot.LoopState:
    return autopilot.LoopState(
        change_id="ri-08",
        current_phase="IMPLEMENT",
        total_iterations=9,
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

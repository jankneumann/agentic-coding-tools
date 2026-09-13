"""Boundary validation and legacy omission for bridge projection keys."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest


BRIDGE_PATH = (
    Path(__file__).resolve().parents[3]
    / "skills/coordination-bridge/scripts/coordination_bridge.py"
)


def _load_bridge():
    spec = importlib.util.spec_from_file_location("bridge_validation", BRIDGE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "key",
    [
        {"change_id": "ri-08", "phase": "IMPLEMENT"},
        {"change_id": "Bad ID", "phase": "IMPLEMENT", "transition_sequence": 1},
        {"change_id": "ri-08", "phase": "UNKNOWN", "transition_sequence": 1},
        {"change_id": "ri-08", "phase": "IMPLEMENT", "transition_sequence": True},
        {"change_id": "ri-08", "phase": "IMPLEMENT", "transition_sequence": -1},
        {
            "change_id": "ri-08",
            "phase": "IMPLEMENT",
            "transition_sequence": 2147483648,
        },
    ],
)
def test_invalid_projection_key_is_rejected_before_transport(key) -> None:
    bridge = _load_bridge()
    result = bridge.try_submit_work(
        task_type="autopilot-phase",
        task_description="project",
        projection_key=key,
    )
    assert result == {"status": "failed", "reason": "invalid_projection_key"}


def test_unkeyed_submit_omits_projection_key_for_legacy_contract(monkeypatch) -> None:
    bridge = _load_bridge()
    captured: dict[str, Any] = {}

    def execute(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"status": "ok"}

    monkeypatch.setattr(bridge, "_execute_single_endpoint_operation", execute)
    bridge.try_submit_work(task_type="legacy", task_description="ordinary task")

    assert "projection_key" not in captured["payload"]

"""Projection submit/reconcile helpers preserve the bridge no-raise contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
BRIDGE_PATH = REPO_ROOT / "skills/coordination-bridge/scripts/coordination_bridge.py"


def _load_bridge():
    spec = importlib.util.spec_from_file_location("bridge_projection", BRIDGE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _key() -> dict[str, Any]:
    return {"change_id": "ri-08", "phase": "IMPLEMENT", "transition_sequence": 9}


def test_submit_forwards_projection_key_and_deduplication(monkeypatch) -> None:
    bridge = _load_bridge()
    captured: dict[str, Any] = {}

    def execute(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "status": "ok",
            "response": {
                "success": True,
                "task_id": "00000000-0000-0000-0000-000000000001",
                "created": False,
                "deduplicated": True,
                "status": "pending",
                "cancelled_task_ids": [],
            },
        }

    monkeypatch.setattr(bridge, "_execute_single_endpoint_operation", execute)
    result = bridge.try_submit_work(
        task_type="autopilot-phase",
        task_description="project phase",
        projection_key=_key(),
    )

    assert captured["payload"]["projection_key"] == _key()
    assert result["response"]["created"] is False
    assert result["response"]["deduplicated"] is True


def test_reconcile_derives_payload_and_never_raises_transport_failure(monkeypatch) -> None:
    bridge = _load_bridge()
    captured: dict[str, Any] = {}

    def execute(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"status": "skipped", "reason": "coordinator_unreachable"}

    monkeypatch.setattr(bridge, "_execute_single_endpoint_operation", execute)
    result = bridge.try_reconcile_work_projection(
        projection_key=_key(),
        task_type="autopilot-phase",
        task_description="repair phase projection",
    )

    assert captured["path"] == "/work/reconcile"
    assert captured["payload"]["projection_key"] == _key()
    assert result == {"status": "skipped", "reason": "coordinator_unreachable"}


@pytest.mark.parametrize("field", ["change_id", "phase", "transition_sequence"])
def test_reserved_identity_cannot_be_duplicated_in_input_data(field: str) -> None:
    bridge = _load_bridge()
    with pytest.raises(ValueError, match="reserved projection identity"):
        bridge.try_reconcile_work_projection(
            projection_key=_key(),
            task_type="autopilot-phase",
            task_description="repair",
            input_data={field: "duplicate"},
        )

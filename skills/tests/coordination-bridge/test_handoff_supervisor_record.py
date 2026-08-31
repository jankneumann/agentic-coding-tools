"""Supervisor-record pass-through coverage for the coordination bridge."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
BRIDGE_PATH = REPO_ROOT / "skills/coordination-bridge/scripts/coordination_bridge.py"


def _load_bridge():
    spec = importlib.util.spec_from_file_location(
        "coordination_bridge_under_test", BRIDGE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_handoff_write_conditionally_forwards_supervisor_record(monkeypatch) -> None:
    bridge = _load_bridge()
    captured: list[dict[str, Any]] = []

    def capture(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return {"status": "ok"}

    monkeypatch.setattr(bridge, "_execute_multi_endpoint_operation", capture)
    monkeypatch.setattr(bridge, "_resolve_api_key", lambda _value: "secret")
    record = {"schema_version": 1, "active_changes": []}

    bridge.try_handoff_write(
        agent_id="supervisor",
        summary="checkpoint",
        content={"supervisor_record": record},
    )

    assert captured[0]["payload"]["supervisor_record"] is record


def test_handoff_write_without_record_preserves_previous_payload(monkeypatch) -> None:
    bridge = _load_bridge()
    captured: list[dict[str, Any]] = []

    def capture(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return {"status": "ok"}

    monkeypatch.setattr(bridge, "_execute_multi_endpoint_operation", capture)
    monkeypatch.setattr(bridge, "_resolve_api_key", lambda _value: "secret")

    bridge.try_handoff_write(
        agent_id="supervisor",
        summary="checkpoint",
        content={"completed_work": ["done"]},
    )

    assert captured[0]["payload"] == {
        "session_id": None,
        "summary": "checkpoint",
        "completed_work": ["done"],
        "in_progress": None,
        "decisions": None,
        "next_steps": None,
        "relevant_files": None,
    }


def test_handoff_read_forwards_supervisor_only(monkeypatch) -> None:
    bridge = _load_bridge()
    captured: list[dict[str, Any]] = []

    def capture(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return {"status": "ok", "handoffs": [{"supervisor_record": {}}]}

    monkeypatch.setattr(bridge, "_execute_multi_endpoint_operation", capture)

    result = bridge.try_handoff_read(
        agent_id="supervisor", limit=1, supervisor_only=True
    )

    assert result["handoffs"][0]["supervisor_record"] == {}
    assert captured[0]["payload"]["supervisor_only"] is True

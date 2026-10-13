"""Feature-registry bridge helpers resolve from the generated OPERATIONS table.

Spec: coordination-bridge "Feature Registry Bridge Helpers" (design D3, D6).
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import coordination_bridge

OPERATIONS = coordination_bridge._FEATURE_OPERATIONS


def _state(**overrides: Any) -> dict[str, Any]:
    base = {
        "status": "ok",
        "COORDINATOR_AVAILABLE": True,
        "COORDINATION_TRANSPORT": "http",
        "http_url": "http://coord.example",
        "CAN_FEATURE_REGISTRY": True,
    }
    base.update(overrides)
    return base


# helper name -> (operationId, kwargs, expected payload or None)
HELPERS: dict[str, tuple[str, dict[str, Any], dict[str, Any] | None]] = {
    "try_register_feature": (
        "registerFeature",
        {"feature_id": "f-1", "resource_claims": ["db:x"]},
        {
            "feature_id": "f-1",
            "resource_claims": ["db:x"],
            "title": None,
            "agent_id": None,
            "branch_name": None,
            "merge_priority": 5,
            "metadata": None,
        },
    ),
    "try_deregister_feature": (
        "deregisterFeature",
        {"feature_id": "f-1"},
        {"feature_id": "f-1", "status": "completed"},
    ),
    "try_get_feature": ("getFeature", {"feature_id": "f-1"}, None),
    "try_list_active_features": ("listActiveFeatures", {}, None),
    "try_analyze_feature_conflicts": (
        "analyzeFeatureConflicts",
        {"candidate_feature_id": "f-2", "candidate_claims": ["db:x"]},
        {"candidate_feature_id": "f-2", "candidate_claims": ["db:x"]},
    ),
}


def _capture(monkeypatch, response: dict[str, Any]) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(coordination_bridge, "detect_coordination", lambda **_: _state())

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return response

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http_request)
    return captured


@pytest.mark.parametrize("helper", sorted(HELPERS))
def test_helper_sends_request_resolved_from_operations(monkeypatch, helper: str) -> None:
    op_id, kwargs, payload = HELPERS[helper]
    captured = _capture(monkeypatch, {"status_code": 200, "data": {"ok": 1}, "error": None})

    result = getattr(coordination_bridge, helper)(**kwargs)

    op = OPERATIONS[op_id]
    expected_path = op.path.replace("{feature_id}", kwargs.get("feature_id", ""))
    assert captured[0]["method"] == op.method
    assert captured[0]["path"] == expected_path
    assert captured[0]["payload"] == payload
    assert result["status"] == "ok"
    assert result["operation"] == helper
    assert result["data"] == {"ok": 1}


@pytest.mark.parametrize("helper", sorted(HELPERS))
def test_helper_follows_a_changed_operations_table(monkeypatch, helper: str) -> None:
    op_id, kwargs, _payload = HELPERS[helper]
    moved = OPERATIONS[op_id]._replace(method="PUT", path="/v2" + OPERATIONS[op_id].path)
    monkeypatch.setitem(OPERATIONS, op_id, moved)
    captured = _capture(monkeypatch, {"status_code": 200, "data": {}, "error": None})

    getattr(coordination_bridge, helper)(**kwargs)

    assert captured[0]["method"] == "PUT"
    assert captured[0]["path"].startswith("/v2/features/")


@pytest.mark.parametrize("helper", sorted(HELPERS))
def test_helper_skips_when_coordinator_unreachable(monkeypatch, helper: str) -> None:
    _op_id, kwargs, _payload = HELPERS[helper]
    _capture(monkeypatch, {"status_code": None, "data": None, "error": "timed out"})

    result = getattr(coordination_bridge, helper)(**kwargs)

    assert result["status"] == "skipped"
    assert result["reason"] == "coordinator_unreachable"


@pytest.mark.parametrize("helper", sorted(HELPERS))
def test_helper_skips_without_feature_registry_capability(monkeypatch, helper: str) -> None:
    _op_id, kwargs, _payload = HELPERS[helper]
    monkeypatch.setattr(
        coordination_bridge,
        "detect_coordination",
        lambda **_: _state(CAN_FEATURE_REGISTRY=False),
    )

    result = getattr(coordination_bridge, helper)(**kwargs)

    assert result["status"] == "skipped"
    assert result["reason"] == "capability_unavailable"


def test_get_feature_url_encodes_identifier(monkeypatch) -> None:
    captured = _capture(monkeypatch, {"status_code": 200, "data": {}, "error": None})

    coordination_bridge.try_get_feature(feature_id="a/b c?d")

    assert captured[0]["method"] == "GET"
    assert captured[0]["path"] == "/features/a%2Fb%20c%3Fd"


def test_get_unknown_feature_returns_non_ok_without_raising(monkeypatch) -> None:
    _capture(
        monkeypatch,
        {"status_code": 404, "data": {"detail": "Feature not found"}, "error": "not found"},
    )

    result = coordination_bridge.try_get_feature(feature_id="missing")

    assert result["status"] != "ok"
    assert result["operation"] == "try_get_feature"


def test_register_and_deregister_keep_their_keyword_parameters() -> None:
    register = inspect.signature(coordination_bridge.try_register_feature).parameters
    assert {name: p.default for name, p in register.items()} == {
        "feature_id": inspect.Parameter.empty,
        "resource_claims": inspect.Parameter.empty,
        "title": None,
        "agent_id": None,
        "branch_name": None,
        "merge_priority": 5,
        "metadata": None,
        "http_url": None,
        "api_key": None,
    }
    deregister = inspect.signature(coordination_bridge.try_deregister_feature).parameters
    assert {name: p.default for name, p in deregister.items()} == {
        "feature_id": inspect.Parameter.empty,
        "status": "completed",
        "http_url": None,
        "api_key": None,
    }
    for params in (register, deregister):
        assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params.values())


def test_capability_probe_reports_feature_registry_when_active_list_returns_200(
    monkeypatch,
) -> None:
    """A coordinator serving GET /features/active (route-order fix, D6) is detected."""
    monkeypatch.setattr(
        coordination_bridge, "_resolve_http_url", lambda http_url=None: "http://coord.example"
    )
    monkeypatch.setattr(coordination_bridge, "_resolve_api_key", lambda api_key=None: "token")

    def fake_http_request(*, method: str, path: str, **_: Any) -> dict[str, Any]:
        if path == "/features/active":
            assert method == "GET"
            return {
                "status_code": 200,
                "data": {"features": [], "count": 0, "truncated": False},
                "error": None,
            }
        if path == "/health":
            return {"status_code": 200, "data": {"status": "ok"}, "error": None}
        return {"status_code": 404, "data": {}, "error": "not found"}

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http_request)

    result = coordination_bridge.detect_coordination()

    assert result["CAN_FEATURE_REGISTRY"] is True
    assert result["capabilities"]["feature_registry"] is True

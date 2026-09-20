"""Tests for coordination_bridge.try_select_model_for_task (dg-04 design D8).

Change: implement-the-task-router-vendor-x-location-x-model (dg-04), package
        "Local fallback and bridge".
Spec: openspec/changes/implement-the-task-router-vendor-x-location-x-model/
      specs/task-routing/spec.md -- Requirement: Honest local fallback.

Mirrors the coordinator-first / never-raises contract test style already
established for ``try_resolve_archetype_for_phase``
(test_archetype_resolve.py), plus the local-static fallback path this helper
adds on top of it.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import pytest

_BRIDGE_DIR = Path(__file__).resolve().parents[2] / "coordination-bridge" / "scripts"
if str(_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_DIR))

import coordination_bridge  # noqa: E402
import routing_fallback  # noqa: E402

_COORDINATOR_RESPONSE: dict[str, Any] = {
    "decision_id": "3f1b7c1e-9a3d-4f9d-8b1a-2c6e5d4a9b0c",
    "selected": {"vendor": "claude_code", "model": "claude-sonnet-4-6", "score": 0.9},
    "alternatives": [],
    "fallback": False,
}

_LOCAL_RESPONSE: dict[str, Any] = {
    "decision_id": "local-uuid",
    "selected": {"vendor": "claude_code", "model": "claude-sonnet-4-6"},
    "alternatives": [],
    "fallback": True,
    "provenance": {"source": "local-static"},
}


@pytest.fixture(autouse=True)
def _coordinator_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COORDINATION_API_URL", "http://localhost:8081")
    monkeypatch.setenv("COORDINATION_API_KEY", "test-key")
    for key in ("COORDINATOR_HTTP_URL", "AGENT_COORDINATOR_API_URL", "AGENT_COORDINATOR_HTTP_URL"):
        monkeypatch.delenv(key, raising=False)


def _stub_http(monkeypatch: pytest.MonkeyPatch, response: dict[str, Any]) -> dict[str, Any]:
    recorded: dict[str, Any] = {}

    def fake(**kwargs: Any) -> dict[str, Any]:
        recorded.update(kwargs)
        return response

    monkeypatch.setattr(coordination_bridge, "_http_request", fake)
    return recorded


def test_coordinator_success_returns_data_without_local_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _stub_http(
        monkeypatch, {"status_code": 200, "data": _COORDINATOR_RESPONSE, "error": None}
    )
    called = {"local": False}
    monkeypatch.setattr(
        routing_fallback,
        "local_static_route",
        lambda *a, **k: called.update(local=True) or {},
    )

    result = coordination_bridge.try_select_model_for_task(
        {"archetype": "implementer"}, static_provider="claude_code", static_model="claude-sonnet-4-6"
    )

    assert result == _COORDINATOR_RESPONSE
    assert recorded["path"] == "/routing/select_model"
    assert called["local"] is False


def test_coordinator_failure_falls_back_to_local_static(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _stub_http(monkeypatch, {"status_code": 503, "data": None, "error": "HTTP 503"})
    recorded: dict[str, Any] = {}

    def fake_local(task_signals: Any, **kwargs: Any) -> dict[str, Any]:
        recorded["task_signals"] = task_signals
        recorded.update(kwargs)
        return _LOCAL_RESPONSE

    monkeypatch.setattr(routing_fallback, "local_static_route", fake_local)

    with caplog.at_level(logging.WARNING, logger="coordination_bridge"):
        result = coordination_bridge.try_select_model_for_task(
            {"archetype": "implementer"},
            static_provider="claude_code",
            static_model="claude-sonnet-4-6",
        )

    assert result == _LOCAL_RESPONSE
    assert recorded["static_provider"] == "claude_code"
    assert recorded["static_model"] == "claude-sonnet-4-6"
    assert any("coordinator call failed" in r.message for r in caplog.records)


def test_missing_static_provider_model_returns_none_without_local_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_http(monkeypatch, {"status_code": 503, "data": None, "error": "HTTP 503"})
    called = {"local": False}
    monkeypatch.setattr(
        routing_fallback,
        "local_static_route",
        lambda *a, **k: called.update(local=True) or {},
    )

    result = coordination_bridge.try_select_model_for_task({"archetype": "implementer"})

    assert result is None
    assert called["local"] is False


def test_missing_http_url_still_attempts_local_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(coordination_bridge, "_resolve_http_url", lambda http_url=None: None)
    monkeypatch.setattr(routing_fallback, "local_static_route", lambda *a, **k: _LOCAL_RESPONSE)

    result = coordination_bridge.try_select_model_for_task(
        {"archetype": "implementer"}, static_provider="claude_code", static_model="claude-sonnet-4-6"
    )

    assert result == _LOCAL_RESPONSE


def test_local_fallback_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_http(monkeypatch, {"status_code": 503, "data": None, "error": "HTTP 503"})

    def raise_fallback(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise routing_fallback.LocalRoutingFallbackError("no exact lane")

    monkeypatch.setattr(routing_fallback, "local_static_route", raise_fallback)

    result = coordination_bridge.try_select_model_for_task(
        {"archetype": "implementer"}, static_provider="claude_code", static_model="claude-sonnet-4-6"
    )

    assert result is None


def test_malformed_coordinator_response_falls_back_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_http(monkeypatch, {"status_code": 200, "data": {"unexpected": "shape"}, "error": None})
    monkeypatch.setattr(routing_fallback, "local_static_route", lambda *a, **k: _LOCAL_RESPONSE)

    result = coordination_bridge.try_select_model_for_task(
        {"archetype": "implementer"}, static_provider="claude_code", static_model="claude-sonnet-4-6"
    )

    assert result == _LOCAL_RESPONSE


def test_never_raises_when_local_config_is_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_http(monkeypatch, {"status_code": 503, "data": None, "error": "HTTP 503"})

    def raise_value_error(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ValueError("routing.yaml at ... is missing policy_version")

    monkeypatch.setattr(routing_fallback, "local_static_route", raise_value_error)

    result = coordination_bridge.try_select_model_for_task(
        {"archetype": "implementer"}, static_provider="claude_code", static_model="claude-sonnet-4-6"
    )

    assert result is None

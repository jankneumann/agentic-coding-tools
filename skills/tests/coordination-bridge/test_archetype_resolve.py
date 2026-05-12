"""Tests for coordination_bridge.try_resolve_archetype_for_phase.

Spec: openspec/changes/add-per-phase-archetype-resolution/specs/agent-coordinator/spec.md
      Requirement: Phase Archetype Resolution Bridge Helper.
Contract: openspec/changes/add-per-phase-archetype-resolution/contracts/openapi/v1.yaml
Design decisions: D4 (bridge helper), D9 (failure mode).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import pytest

# Make the bridge importable without needing an editable install.
_BRIDGE_DIR = Path(__file__).resolve().parents[2] / "coordination-bridge" / "scripts"
if str(_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_DIR))

import coordination_bridge  # noqa: E402

_VALID_RESPONSE: dict[str, Any] = {
    "model": "opus",
    "system_prompt": "You are a software architect.",
    "archetype": "architect",
    "reasons": ["phase=PLAN maps to archetype=architect"],
}


@pytest.fixture(autouse=True)
def _coordinator_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide a deterministic coordinator URL + API key for every test."""
    monkeypatch.setenv("COORDINATION_API_URL", "http://localhost:8081")
    monkeypatch.setenv("COORDINATION_API_KEY", "test-key")
    # Drop any conflicting overrides so _resolve_http_url is deterministic.
    for key in (
        "COORDINATOR_HTTP_URL",
        "AGENT_COORDINATOR_API_URL",
        "AGENT_COORDINATOR_HTTP_URL",
    ):
        monkeypatch.delenv(key, raising=False)


def _stub_http(monkeypatch: pytest.MonkeyPatch, response: dict[str, Any]) -> dict[str, Any]:
    """Replace _http_request with a stub. Return the recorded call dict."""
    recorded: dict[str, Any] = {}

    def fake(*, method: str, path: str, payload: dict[str, Any] | None = None,
             http_url: str | None = None, api_key: str | None = None,
             timeout: float = coordination_bridge.DEFAULT_TIMEOUT_SECONDS,
             ) -> dict[str, Any]:
        recorded["method"] = method
        recorded["path"] = path
        recorded["payload"] = payload
        recorded["http_url"] = http_url
        recorded["api_key"] = api_key
        recorded["timeout"] = timeout
        return response

    monkeypatch.setattr(coordination_bridge, "_http_request", fake)
    return recorded


def test_resolve_success_returns_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _stub_http(
        monkeypatch,
        {"status_code": 200, "data": _VALID_RESPONSE, "error": None},
    )

    result = coordination_bridge.try_resolve_archetype_for_phase(
        "PLAN", {"capabilities_touched": 3}
    )

    assert result == _VALID_RESPONSE
    assert recorded["method"] == "POST"
    assert recorded["path"] == "/archetypes/resolve_for_phase"
    assert recorded["payload"] == {"phase": "PLAN", "signals": {"capabilities_touched": 3}}
    assert recorded["http_url"] == "http://localhost:8081"
    assert recorded["api_key"] == "test-key"


def test_resolve_success_with_no_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _stub_http(
        monkeypatch,
        {"status_code": 200, "data": _VALID_RESPONSE, "error": None},
    )

    result = coordination_bridge.try_resolve_archetype_for_phase("PLAN")

    assert result == _VALID_RESPONSE
    assert recorded["payload"] == {"phase": "PLAN", "signals": {}}


def test_resolve_5xx_returns_none_and_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _stub_http(
        monkeypatch,
        {"status_code": 503, "data": {"error": "Service Unavailable"}, "error": "HTTP 503"},
    )

    with caplog.at_level(logging.WARNING, logger="coordination_bridge"):
        result = coordination_bridge.try_resolve_archetype_for_phase("PLAN", {})

    assert result is None
    assert any(
        "PLAN" in r.message and "503" in r.message
        for r in caplog.records
    ), f"expected WARNING mentioning phase + status, got: {[r.message for r in caplog.records]}"


def test_resolve_4xx_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_http(
        monkeypatch,
        {"status_code": 404, "data": {"error": "Phase 'BOGUS' not found"}, "error": "HTTP 404"},
    )

    result = coordination_bridge.try_resolve_archetype_for_phase("BOGUS", {})

    assert result is None


def test_resolve_timeout_returns_none(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _stub_http(
        monkeypatch,
        {"status_code": None, "data": None, "error": "timed out"},
    )

    with caplog.at_level(logging.WARNING, logger="coordination_bridge"):
        result = coordination_bridge.try_resolve_archetype_for_phase("PLAN", {})

    assert result is None
    assert any("PLAN" in r.message for r in caplog.records)


def test_resolve_malformed_response_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # 200 OK but missing required fields
    _stub_http(
        monkeypatch,
        {"status_code": 200, "data": {"model": "opus"}, "error": None},
    )

    result = coordination_bridge.try_resolve_archetype_for_phase("PLAN", {})

    assert result is None


def test_resolve_non_dict_response_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_http(
        monkeypatch,
        {"status_code": 200, "data": "not a dict", "error": None},
    )

    result = coordination_bridge.try_resolve_archetype_for_phase("PLAN", {})

    assert result is None


def test_resolve_missing_url_returns_none(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("COORDINATION_API_URL", raising=False)
    monkeypatch.delenv("AGENT_COORDINATOR_REST_PORT", raising=False)
    monkeypatch.setattr(coordination_bridge, "_resolve_http_url", lambda http_url=None: None)

    with caplog.at_level(logging.WARNING, logger="coordination_bridge"):
        result = coordination_bridge.try_resolve_archetype_for_phase("PLAN", {})

    assert result is None
    assert any("missing_http_url" in r.message or "PLAN" in r.message for r in caplog.records)


def test_resolve_explicit_url_and_key_override_env(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _stub_http(
        monkeypatch,
        {"status_code": 200, "data": _VALID_RESPONSE, "error": None},
    )

    coordination_bridge.try_resolve_archetype_for_phase(
        "PLAN",
        {},
        http_url="http://localhost:9999",
        api_key="explicit-key",
    )

    assert recorded["http_url"] == "http://localhost:9999"
    assert recorded["api_key"] == "explicit-key"


def test_resolve_never_raises_on_unexpected_response_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # _http_request returning an unexpected shape should still degrade gracefully.
    monkeypatch.setattr(
        coordination_bridge,
        "_http_request",
        lambda **_: {"status_code": 200, "data": None, "error": None},
    )
    assert coordination_bridge.try_resolve_archetype_for_phase("PLAN", {}) is None

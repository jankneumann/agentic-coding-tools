"""Tests for scripts/coordination_bridge.py."""

from __future__ import annotations

from typing import Any

import coordination_bridge


def _state(**overrides: Any) -> dict[str, Any]:
    base = {
        "status": "ok",
        "COORDINATOR_AVAILABLE": True,
        "COORDINATION_TRANSPORT": "http",
        "http_url": "http://coord.example",
        "CAN_LOCK": False,
        "CAN_QUEUE_WORK": False,
        "CAN_HANDOFF": False,
        "CAN_MEMORY": False,
        "CAN_GUARDRAILS": False,
    }
    base.update(overrides)
    return base


def test_validate_url_allows_localhost() -> None:
    assert coordination_bridge._validate_url("http://localhost:3000") is not None
    assert coordination_bridge._validate_url("http://127.0.0.1:3000") is not None
    assert coordination_bridge._validate_url("https://localhost:3000") is not None


def test_validate_url_rejects_external_hosts() -> None:
    assert coordination_bridge._validate_url("http://evil.example.com:3000") is None
    assert coordination_bridge._validate_url("http://attacker.internal") is None


def test_validate_url_rejects_bad_schemes() -> None:
    assert coordination_bridge._validate_url("ftp://localhost:3000") is None
    assert coordination_bridge._validate_url("file:///etc/passwd") is None


def test_validate_url_allows_extra_hosts(monkeypatch) -> None:
    monkeypatch.setenv("COORDINATION_ALLOWED_HOSTS", "coordinator.internal,10.0.0.5")
    assert coordination_bridge._validate_url("http://coordinator.internal:3000") is not None
    assert coordination_bridge._validate_url("http://10.0.0.5:3000") is not None
    assert coordination_bridge._validate_url("http://evil.example.com") is None


def test_resolve_http_url_rejects_invalid_port(monkeypatch) -> None:
    monkeypatch.delenv("COORDINATION_API_URL", raising=False)
    monkeypatch.delenv("COORDINATOR_HTTP_URL", raising=False)
    monkeypatch.delenv("AGENT_COORDINATOR_API_URL", raising=False)
    monkeypatch.delenv("AGENT_COORDINATOR_HTTP_URL", raising=False)
    monkeypatch.setenv("AGENT_COORDINATOR_REST_PORT", "99999")
    assert coordination_bridge._resolve_http_url() is None


def test_resolve_http_url_rejects_non_numeric_port(monkeypatch) -> None:
    monkeypatch.delenv("COORDINATION_API_URL", raising=False)
    monkeypatch.delenv("COORDINATOR_HTTP_URL", raising=False)
    monkeypatch.delenv("AGENT_COORDINATOR_API_URL", raising=False)
    monkeypatch.delenv("AGENT_COORDINATOR_HTTP_URL", raising=False)
    monkeypatch.setenv("AGENT_COORDINATOR_REST_PORT", "abc")
    assert coordination_bridge._resolve_http_url() is None


def test_detect_coordination_missing_url(monkeypatch) -> None:
    monkeypatch.setattr(coordination_bridge, "_resolve_http_url", lambda http_url=None: None)

    result = coordination_bridge.detect_coordination()

    assert result["status"] == "skipped"
    assert result["COORDINATOR_AVAILABLE"] is False
    assert result["COORDINATION_TRANSPORT"] == "none"
    assert result["CAN_LOCK"] is False
    assert result["CAN_QUEUE_WORK"] is False
    assert result["CAN_HANDOFF"] is False
    assert result["CAN_MEMORY"] is False
    assert result["CAN_GUARDRAILS"] is False


def test_detect_coordination_partial_capabilities(monkeypatch) -> None:
    monkeypatch.setattr(
        coordination_bridge,
        "_resolve_http_url",
        lambda http_url=None: "http://coord.example",
    )
    monkeypatch.setattr(coordination_bridge, "_resolve_api_key", lambda api_key=None: "token")

    def fake_http_request(*, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        del method, kwargs
        responses = {
            "/health": {"status_code": 200, "data": {"status": "ok"}, "error": None},
            "/locks/acquire": {"status_code": 422, "data": {}, "error": "validation"},
            "/work/claim": {"status_code": 404, "data": {}, "error": "not found"},
            "/memory/query": {"status_code": 422, "data": {}, "error": "validation"},
            "/guardrails/check": {"status_code": 401, "data": {}, "error": "unauthorized"},
            "/handoff/write": {"status_code": 404, "data": {}, "error": "not found"},
            "/handoffs/write": {"status_code": 404, "data": {}, "error": "not found"},
            "/handoffs/latest": {"status_code": 404, "data": {}, "error": "not found"},
        }
        return responses[path]

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http_request)

    result = coordination_bridge.detect_coordination()

    assert result["status"] == "ok"
    assert result["COORDINATOR_AVAILABLE"] is True
    assert result["COORDINATION_TRANSPORT"] == "http"
    assert result["CAN_LOCK"] is True
    assert result["CAN_MEMORY"] is True
    assert result["CAN_QUEUE_WORK"] is False
    assert result["CAN_HANDOFF"] is False
    assert result["CAN_GUARDRAILS"] is False


def test_try_lock_skips_when_capability_missing(monkeypatch) -> None:
    monkeypatch.setattr(coordination_bridge, "detect_coordination", lambda **_: _state(CAN_LOCK=False))

    result = coordination_bridge.try_lock(
        file_path="a.py",
        agent_id="agent-1",
        agent_type="codex",
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "capability_unavailable"


def test_try_lock_returns_ok(monkeypatch) -> None:
    monkeypatch.setattr(coordination_bridge, "detect_coordination", lambda **_: _state(CAN_LOCK=True))
    monkeypatch.setattr(
        coordination_bridge,
        "_http_request",
        lambda **_: {"status_code": 200, "data": {"success": True}, "error": None},
    )

    result = coordination_bridge.try_lock(
        file_path="a.py",
        agent_id="agent-1",
        agent_type="codex",
    )

    assert result["status"] == "ok"
    assert result["status_code"] == 200
    assert result["response"] == {"success": True}


def test_try_lock_degrades_on_unreachable(monkeypatch) -> None:
    monkeypatch.setattr(coordination_bridge, "detect_coordination", lambda **_: _state(CAN_LOCK=True))
    monkeypatch.setattr(
        coordination_bridge,
        "_http_request",
        lambda **_: {"status_code": None, "data": None, "error": "timed out"},
    )

    result = coordination_bridge.try_lock(
        file_path="a.py",
        agent_id="agent-1",
        agent_type="codex",
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "coordinator_unreachable"


def test_try_handoff_write_skips_when_endpoints_missing(monkeypatch) -> None:
    monkeypatch.setattr(coordination_bridge, "detect_coordination", lambda **_: _state(CAN_HANDOFF=True))
    monkeypatch.setattr(
        coordination_bridge,
        "_http_request",
        lambda **_: {"status_code": 404, "data": {}, "error": "not found"},
    )

    result = coordination_bridge.try_handoff_write(
        agent_id="agent-1",
        session_id="session-1",
        summary="done",
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "capability_unavailable"


def test_try_submit_work_passes_payload(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []

    monkeypatch.setattr(
        coordination_bridge,
        "detect_coordination",
        lambda **_: _state(CAN_QUEUE_WORK=True),
    )

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return {"status_code": 200, "data": {"task_id": "t-1"}, "error": None}

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http_request)

    result = coordination_bridge.try_submit_work(
        task_type="implementation",
        task_description="Update docs",
        input_data={"files": ["docs/skills-workflow.md"]},
        priority=3,
        depends_on=["a", "b"],
    )

    assert result["status"] == "ok"
    assert captured
    payload = captured[0]["payload"]
    assert captured[0]["path"] == "/work/submit"
    assert payload["task_type"] == "implementation"
    assert payload["priority"] == 3
    assert payload["depends_on"] == ["a", "b"]


def test_try_recall_skips_when_coordinator_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        coordination_bridge,
        "detect_coordination",
        lambda **_: _state(
            status="skipped",
            COORDINATOR_AVAILABLE=False,
            COORDINATION_TRANSPORT="none",
        ),
    )

    result = coordination_bridge.try_recall(agent_id="agent-1")

    assert result["status"] == "skipped"
    assert result["reason"] == "coordinator_unavailable"

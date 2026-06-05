"""Tests for coordination_bridge.py."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
        "CAN_FEATURE_REGISTRY": False,
        "CAN_MERGE_QUEUE": False,
        "CAN_ISSUES": False,
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
        responses: dict[str, dict[str, Any]] = {
            "/health": {"status_code": 200, "data": {"status": "ok"}, "error": None},
            "/locks/acquire": {"status_code": 422, "data": {}, "error": "validation"},
            "/work/claim": {"status_code": 404, "data": {}, "error": "not found"},
            "/memory/query": {"status_code": 422, "data": {}, "error": "validation"},
            "/guardrails/check": {"status_code": 401, "data": {}, "error": "unauthorized"},
            "/handoffs/write": {"status_code": 404, "data": {}, "error": "not found"},
            "/features/active": {"status_code": 404, "data": {}, "error": "not found"},
            "/merge-queue": {"status_code": 404, "data": {}, "error": "not found"},
            "/issues/list": {"status_code": 200, "data": {"success": True, "issues": [], "count": 0}, "error": None},
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
    assert result["CAN_FEATURE_REGISTRY"] is False
    assert result["CAN_MERGE_QUEUE"] is False
    assert result["CAN_ISSUES"] is True


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


def test_try_handoff_write_sends_http_contract_payload(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []

    monkeypatch.delenv("COORDINATION_API_KEY", raising=False)
    monkeypatch.delenv("COORDINATOR_API_KEY", raising=False)
    monkeypatch.setattr(
        coordination_bridge,
        "detect_coordination",
        lambda **_: _state(CAN_HANDOFF=True),
    )

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return {"status_code": 200, "data": {"success": True}, "error": None}

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http_request)

    result = coordination_bridge.try_handoff_write(
        agent_id="agent-1",
        agent_type="codex",
        session_id="session-1",
        summary="done",
        content={
            "completed_work": ["finished"],
            "decisions": [{"summary": "structured"}],
            "next_steps": ["ship"],
            "relevant_files": [{"path": "a.py"}],
            "ignored": "legacy",
        },
    )

    assert result["status"] == "ok"
    payload = captured[0]["payload"]
    assert payload == {
        "agent_id": "agent-1",
        "agent_type": "codex",
        "session_id": "session-1",
        "summary": "done",
        "completed_work": ["finished"],
        "in_progress": None,
        "decisions": [{"summary": "structured"}],
        "next_steps": ["ship"],
        "relevant_files": [{"path": "a.py"}],
    }


def test_try_handoff_write_omits_identity_when_bound_api_key(monkeypatch) -> None:
    """Bound-key path: server resolves identity from the principal, so the
    bridge must not send caller-provided agent_id / agent_type — that path
    triggers a 403 in resolve_identity when the bound identity differs."""
    captured: list[dict[str, Any]] = []

    monkeypatch.delenv("COORDINATION_API_KEY", raising=False)
    monkeypatch.delenv("COORDINATOR_API_KEY", raising=False)
    monkeypatch.setattr(
        coordination_bridge,
        "detect_coordination",
        lambda **_: _state(CAN_HANDOFF=True),
    )
    monkeypatch.setattr(
        coordination_bridge,
        "_http_request",
        lambda **kwargs: (captured.append(kwargs) or {"status_code": 200, "data": {"success": True}, "error": None}),
    )

    # Explicit api_key — should suppress identity fields in the payload.
    result = coordination_bridge.try_handoff_write(
        agent_id="claude-code-local",
        agent_type="claude_code",
        session_id="session-1",
        summary="done",
        api_key="bound-key-xyz",
    )

    assert result["status"] == "ok"
    payload = captured[0]["payload"]
    assert "agent_id" not in payload
    assert "agent_type" not in payload
    # Other fields still propagate.
    assert payload["session_id"] == "session-1"
    assert payload["summary"] == "done"

    # Same suppression when api_key arrives via COORDINATION_API_KEY env var.
    captured.clear()
    monkeypatch.setenv("COORDINATION_API_KEY", "env-bound-key")
    coordination_bridge.try_handoff_write(
        agent_id="claude-code-local",
        agent_type="claude_code",
        session_id="session-2",
        summary="done",
    )
    payload = captured[0]["payload"]
    assert "agent_id" not in payload
    assert "agent_type" not in payload


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


def test_validate_url_allows_custom_domain(monkeypatch) -> None:
    """Custom domain in COORDINATION_ALLOWED_HOSTS is accepted."""
    monkeypatch.setenv("COORDINATION_ALLOWED_HOSTS", "coord.example.com")
    assert coordination_bridge._validate_url("https://coord.example.com/health") is not None
    assert coordination_bridge._validate_url("https://coord.example.com:443/health") is not None
    # Unlisted hosts still blocked
    assert coordination_bridge._validate_url("https://evil.example.com") is None


def test_validate_url_allows_wildcard_subdomain(monkeypatch) -> None:
    """Wildcard *.domain.com matches any subdomain."""
    monkeypatch.setenv("COORDINATION_ALLOWED_HOSTS", "*.example.com")
    assert coordination_bridge._validate_url("https://coord.example.com") is not None
    assert coordination_bridge._validate_url("https://mcp.example.com") is not None
    assert coordination_bridge._validate_url("https://vault.example.com:8200") is not None
    # Bare domain should NOT match wildcard (*.example.com != example.com)
    assert coordination_bridge._validate_url("https://example.com") is None
    # Unlisted domains still blocked
    assert coordination_bridge._validate_url("https://evil.other.com") is None


def test_validate_url_wildcard_deep_subdomain(monkeypatch) -> None:
    """Wildcard *.domain.com matches multi-level subdomains (a.b.domain.com)."""
    monkeypatch.setenv("COORDINATION_ALLOWED_HOSTS", "*.example.com")
    assert coordination_bridge._validate_url("https://deep.sub.example.com") is not None
    assert coordination_bridge._validate_url("https://a.b.c.example.com") is not None


def test_validate_url_wildcard_mixed_with_exact(monkeypatch) -> None:
    """Wildcard and exact entries can coexist in COORDINATION_ALLOWED_HOSTS."""
    monkeypatch.setenv(
        "COORDINATION_ALLOWED_HOSTS",
        "*.example.com,specific.railway.app",
    )
    assert coordination_bridge._validate_url("https://coord.example.com") is not None
    assert coordination_bridge._validate_url("https://specific.railway.app") is not None
    assert coordination_bridge._validate_url("https://other.railway.app") is None


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


# --------------------------------------------------------------------------- #
# try_issue_* helpers
# --------------------------------------------------------------------------- #


def test_can_issues_is_in_capability_flags() -> None:
    assert "CAN_ISSUES" in coordination_bridge._CAPABILITY_FLAGS
    assert "CAN_ISSUES" in coordination_bridge._CAPABILITY_PROBES


def test_try_issue_create_skips_when_capability_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        coordination_bridge, "detect_coordination", lambda **_: _state(CAN_ISSUES=False)
    )

    result = coordination_bridge.try_issue_create(title="Fix CORS")

    assert result["status"] == "skipped"
    assert result["reason"] == "capability_unavailable"


def test_try_issue_create_passes_payload(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        coordination_bridge, "detect_coordination", lambda **_: _state(CAN_ISSUES=True)
    )

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return {
            "status_code": 200,
            "data": {"success": True, "issue": {"id": "i-1"}},
            "error": None,
        }

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http_request)

    result = coordination_bridge.try_issue_create(
        title="Fix CORS",
        description="Add CORS middleware",
        issue_type="bug",
        priority=3,
        labels=["api", "followup"],
        parent_id="epic-1",
        depends_on=["a", "b"],
    )

    assert result["status"] == "ok"
    assert captured[0]["path"] == "/issues/create"
    payload = captured[0]["payload"]
    assert payload["title"] == "Fix CORS"
    assert payload["issue_type"] == "bug"
    assert payload["priority"] == 3
    assert payload["labels"] == ["api", "followup"]
    assert payload["parent_id"] == "epic-1"
    assert payload["depends_on"] == ["a", "b"]
    # Optional fields that weren't passed must NOT appear in the payload:
    assert "assignee" not in payload


def test_try_issue_create_degrades_on_unreachable(monkeypatch) -> None:
    monkeypatch.setattr(
        coordination_bridge, "detect_coordination", lambda **_: _state(CAN_ISSUES=True)
    )
    monkeypatch.setattr(
        coordination_bridge,
        "_http_request",
        lambda **_: {"status_code": None, "data": None, "error": "timed out"},
    )

    result = coordination_bridge.try_issue_create(title="Fix CORS")

    assert result["status"] == "skipped"
    assert result["reason"] == "coordinator_unreachable"


def test_try_issue_list_omits_none_filters(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        coordination_bridge, "detect_coordination", lambda **_: _state(CAN_ISSUES=True)
    )

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return {
            "status_code": 200,
            "data": {"success": True, "issues": [], "count": 0},
            "error": None,
        }

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http_request)

    result = coordination_bridge.try_issue_list(status="open", limit=20)

    assert result["status"] == "ok"
    payload = captured[0]["payload"]
    assert payload == {"status": "open", "limit": 20}


def test_try_issue_show_uses_get_with_id_in_path(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        coordination_bridge, "detect_coordination", lambda **_: _state(CAN_ISSUES=True)
    )

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return {
            "status_code": 200,
            "data": {"success": True, "issue": {"id": "i-1"}},
            "error": None,
        }

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http_request)

    result = coordination_bridge.try_issue_show(issue_id="i-1")

    assert result["status"] == "ok"
    assert captured[0]["method"] == "GET"
    assert captured[0]["path"] == "/issues/i-1"
    assert captured[0]["payload"] is None


def test_try_issue_update_always_includes_issue_id(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        coordination_bridge, "detect_coordination", lambda **_: _state(CAN_ISSUES=True)
    )

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return {"status_code": 200, "data": {"success": True}, "error": None}

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http_request)

    coordination_bridge.try_issue_update(issue_id="i-1", status="in_progress")

    payload = captured[0]["payload"]
    assert payload["issue_id"] == "i-1"
    assert payload["status"] == "in_progress"
    assert "labels" not in payload  # omitted because None


def test_try_issue_close_single(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        coordination_bridge, "detect_coordination", lambda **_: _state(CAN_ISSUES=True)
    )

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return {"status_code": 200, "data": {"success": True, "count": 1}, "error": None}

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http_request)

    coordination_bridge.try_issue_close(issue_id="i-1", reason="merged")
    payload = captured[0]["payload"]
    assert payload == {"issue_id": "i-1", "reason": "merged"}


def test_try_issue_close_batch(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        coordination_bridge, "detect_coordination", lambda **_: _state(CAN_ISSUES=True)
    )

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return {"status_code": 200, "data": {"success": True, "count": 2}, "error": None}

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http_request)

    coordination_bridge.try_issue_close(issue_ids=["a", "b"])
    payload = captured[0]["payload"]
    assert payload == {"issue_ids": ["a", "b"]}


def test_try_issue_comment_payload(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        coordination_bridge, "detect_coordination", lambda **_: _state(CAN_ISSUES=True)
    )

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return {"status_code": 200, "data": {"success": True}, "error": None}

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http_request)

    coordination_bridge.try_issue_comment(issue_id="i-1", body="started")
    payload = captured[0]["payload"]
    assert payload == {"issue_id": "i-1", "body": "started"}


def test_try_issue_ready_scoped_to_parent(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        coordination_bridge, "detect_coordination", lambda **_: _state(CAN_ISSUES=True)
    )

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return {
            "status_code": 200,
            "data": {"success": True, "issues": [], "count": 0},
            "error": None,
        }

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http_request)

    coordination_bridge.try_issue_ready(parent_id="epic-1", limit=5)
    payload = captured[0]["payload"]
    assert payload == {"parent_id": "epic-1", "limit": 5}


def test_try_issue_blocked_uses_query_param(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        coordination_bridge, "detect_coordination", lambda **_: _state(CAN_ISSUES=True)
    )

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return {
            "status_code": 200,
            "data": {"success": True, "issues": [], "count": 0},
            "error": None,
        }

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http_request)

    coordination_bridge.try_issue_blocked(limit=7)
    assert captured[0]["method"] == "GET"
    assert captured[0]["path"] == "/issues/blocked?limit=7"
    assert captured[0]["payload"] is None


def test_try_issue_blocked_without_limit(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        coordination_bridge, "detect_coordination", lambda **_: _state(CAN_ISSUES=True)
    )

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return {
            "status_code": 200,
            "data": {"success": True, "issues": [], "count": 0},
            "error": None,
        }

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http_request)

    coordination_bridge.try_issue_blocked()
    assert captured[0]["path"] == "/issues/blocked"


def test_try_issue_search_required_query(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        coordination_bridge, "detect_coordination", lambda **_: _state(CAN_ISSUES=True)
    )

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return {
            "status_code": 200,
            "data": {"success": True, "issues": [], "count": 0},
            "error": None,
        }

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http_request)

    coordination_bridge.try_issue_search(query="CORS", limit=10)
    payload = captured[0]["payload"]
    assert payload == {"query": "CORS", "limit": 10}


def test_try_issue_create_unauthorized_returns_skipped(monkeypatch) -> None:
    monkeypatch.setattr(
        coordination_bridge, "detect_coordination", lambda **_: _state(CAN_ISSUES=True)
    )
    monkeypatch.setattr(
        coordination_bridge,
        "_http_request",
        lambda **_: {"status_code": 401, "data": {}, "error": "unauthorized"},
    )

    result = coordination_bridge.try_issue_create(title="x")

    assert result["status"] == "skipped"
    assert result["reason"] == "unauthorized"

"""Tests for the coordination HTTP API (src/coordination_api.py)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.coordination_api import (
    create_coordination_api,
    resolve_identity,
)

# =============================================================================
# Fixtures
# =============================================================================

_TEST_KEY = "test-key-001"


@pytest.fixture()
def _api_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch config so the API accepts our test key."""
    from src.config import reset_config

    reset_config()

    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("COORDINATION_API_KEYS", _TEST_KEY)
    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")

    reset_config()

    yield  # type: ignore[misc]

    reset_config()


@pytest.fixture()
def client(_api_config: None) -> TestClient:
    app = create_coordination_api()
    return TestClient(app)


def _auth_headers() -> dict[str, str]:
    return {"X-API-Key": _TEST_KEY}


# =============================================================================
# Auth tests
# =============================================================================


def test_missing_api_key_returns_401(client: TestClient) -> None:
    response = client.post(
        "/locks/acquire",
        json={
            "file_path": "src/main.py",
            "agent_id": "agent-1",
            "agent_type": "codex",
        },
    )
    assert response.status_code == 401


def test_invalid_api_key_returns_401(client: TestClient) -> None:
    response = client.post(
        "/locks/acquire",
        headers={"X-API-Key": "wrong-key"},
        json={
            "file_path": "src/main.py",
            "agent_id": "agent-1",
            "agent_type": "codex",
        },
    )
    assert response.status_code == 401


def test_resolve_identity_blocks_spoofed_agent_id() -> None:
    principal: dict[str, Any] = {"agent_id": "bound-agent", "agent_type": "codex"}
    with pytest.raises(HTTPException) as exc_info:
        resolve_identity(principal, "different-agent", "codex")
    assert exc_info.value.status_code == 403
    assert "agent_id" in str(exc_info.value.detail)


def test_resolve_identity_blocks_spoofed_agent_type() -> None:
    principal: dict[str, Any] = {"agent_id": "agent-1", "agent_type": "codex"}
    with pytest.raises(HTTPException) as exc_info:
        resolve_identity(principal, "agent-1", "claude_code")
    assert exc_info.value.status_code == 403
    assert "agent_type" in str(exc_info.value.detail)


def test_resolve_identity_uses_bound_values() -> None:
    principal: dict[str, Any] = {"agent_id": "bound-agent", "agent_type": "codex"}
    agent_id, agent_type = resolve_identity(principal, None, None)
    assert agent_id == "bound-agent"
    assert agent_type == "codex"


def test_resolve_identity_falls_back_to_request() -> None:
    principal: dict[str, Any] = {"agent_id": None, "agent_type": None}
    agent_id, agent_type = resolve_identity(principal, "req-agent", "req-type")
    assert agent_id == "req-agent"
    assert agent_type == "req-type"


def test_resolve_identity_defaults_to_cloud_agent() -> None:
    principal: dict[str, Any] = {"agent_id": None, "agent_type": None}
    agent_id, agent_type = resolve_identity(principal, None, None)
    assert agent_id == "cloud-agent"
    assert agent_type == "cloud_agent"


# =============================================================================
# Lock endpoint tests
# =============================================================================


def test_acquire_lock_delegates_to_service(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.locks import LockResult

    mock_service = AsyncMock()
    mock_service.acquire.return_value = LockResult(
        success=True,
        action="acquired",
        file_path="src/main.py",
        expires_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    monkeypatch.setattr("src.coordination_api.authorize_operation", AsyncMock())

    import src.locks

    monkeypatch.setattr(src.locks, "_lock_service", mock_service)

    response = client.post(
        "/locks/acquire",
        headers=_auth_headers(),
        json={
            "file_path": "src/main.py",
            "agent_id": "agent-1",
            "agent_type": "codex",
            "ttl_minutes": 30,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["action"] == "acquired"
    mock_service.acquire.assert_called_once()


def test_release_lock_delegates_to_service(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.locks import LockResult

    mock_service = AsyncMock()
    mock_service.release.return_value = LockResult(
        success=True,
        action="released",
        file_path="src/main.py",
    )
    monkeypatch.setattr("src.coordination_api.authorize_operation", AsyncMock())

    import src.locks

    monkeypatch.setattr(src.locks, "_lock_service", mock_service)

    response = client.post(
        "/locks/release",
        headers=_auth_headers(),
        json={"file_path": "src/main.py", "agent_id": "agent-1"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_lock_status_returns_unlocked(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_service = AsyncMock()
    mock_service.check.return_value = []

    import src.locks

    monkeypatch.setattr(src.locks, "_lock_service", mock_service)

    response = client.get("/locks/status/src/main.py")
    assert response.status_code == 200
    assert response.json()["locked"] is False


def test_lock_status_returns_locked(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.locks import Lock

    now = datetime(2026, 1, 1, tzinfo=UTC)
    mock_service = AsyncMock()
    mock_service.check.return_value = [
        Lock(
            file_path="src/main.py",
            locked_by="agent-1",
            agent_type="codex",
            locked_at=now,
            expires_at=now,
            reason="testing",
        )
    ]

    import src.locks

    monkeypatch.setattr(src.locks, "_lock_service", mock_service)

    response = client.get("/locks/status/src/main.py")
    assert response.status_code == 200
    data = response.json()
    assert data["locked"] is True
    assert data["lock"]["locked_by"] == "agent-1"


# =============================================================================
# Memory endpoint tests
# =============================================================================


def test_store_memory_delegates_to_service(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.memory import MemoryResult

    mock_service = AsyncMock()
    mock_service.remember.return_value = MemoryResult(
        success=True, memory_id="mem-123", action="created"
    )
    monkeypatch.setattr("src.coordination_api.authorize_operation", AsyncMock())

    import src.memory

    monkeypatch.setattr(src.memory, "_memory_service", mock_service)

    response = client.post(
        "/memory/store",
        headers=_auth_headers(),
        json={
            "agent_id": "agent-1",
            "event_type": "discovery",
            "summary": "Found a pattern",
        },
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["memory_id"] == "mem-123"


def test_query_memories_delegates_to_service(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.memory import RecallResult

    mock_service = AsyncMock()
    mock_service.recall.return_value = RecallResult(memories=[])
    monkeypatch.setattr("src.coordination_api.authorize_operation", AsyncMock())

    import src.memory

    monkeypatch.setattr(src.memory, "_memory_service", mock_service)

    response = client.post(
        "/memory/query",
        headers=_auth_headers(),
        json={"agent_id": "agent-1", "limit": 5},
    )
    assert response.status_code == 200
    assert response.json()["memories"] == []


# =============================================================================
# Work queue endpoint tests
# =============================================================================


def test_claim_work_delegates_to_service(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.work_queue import ClaimResult

    mock_service = AsyncMock()
    mock_service.claim.return_value = ClaimResult(
        success=True,
        task_id=UUID("12345678-1234-1234-1234-123456789abc"),
        task_type="test",
        description="Run tests",
    )
    monkeypatch.setattr("src.coordination_api.authorize_operation", AsyncMock())

    import src.work_queue

    monkeypatch.setattr(src.work_queue, "_work_queue_service", mock_service)

    response = client.post(
        "/work/claim",
        headers=_auth_headers(),
        json={"agent_id": "agent-1", "agent_type": "codex", "task_types": ["test"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["task_type"] == "test"


def test_complete_work_delegates_to_service(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.work_queue import CompleteResult

    task_uuid = UUID("12345678-1234-1234-1234-123456789abc")
    mock_service = AsyncMock()
    mock_service.complete.return_value = CompleteResult(
        success=True, status="completed", task_id=task_uuid
    )
    monkeypatch.setattr("src.coordination_api.authorize_operation", AsyncMock())

    import src.work_queue

    monkeypatch.setattr(src.work_queue, "_work_queue_service", mock_service)

    response = client.post(
        "/work/complete",
        headers=_auth_headers(),
        json={
            "task_id": str(task_uuid),
            "agent_id": "agent-1",
            "success": True,
            "result": {"ok": True},
        },
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["status"] == "completed"


def test_submit_work_delegates_to_service(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.work_queue import SubmitResult

    task_uuid = UUID("12345678-1234-1234-1234-123456789abc")
    mock_service = AsyncMock()
    mock_service.submit.return_value = SubmitResult(success=True, task_id=task_uuid)
    monkeypatch.setattr("src.coordination_api.authorize_operation", AsyncMock())

    import src.work_queue

    monkeypatch.setattr(src.work_queue, "_work_queue_service", mock_service)

    response = client.post(
        "/work/submit",
        headers=_auth_headers(),
        json={
            "task_type": "test",
            "task_description": "Run tests",
            "priority": 4,
        },
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


# =============================================================================
# Policy denial test
# =============================================================================


def test_policy_denial_returns_403(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def deny(*_args: Any, **_kwargs: Any) -> None:
        raise HTTPException(status_code=403, detail="denied-by-policy")

    monkeypatch.setattr("src.coordination_api.authorize_operation", deny)

    response = client.post(
        "/work/claim",
        headers=_auth_headers(),
        json={"agent_id": "agent-1", "agent_type": "codex", "task_types": ["test"]},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "denied-by-policy"


# =============================================================================
# Health endpoint test
# =============================================================================


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


# =============================================================================
# Guardrails endpoint test
# =============================================================================


def test_guardrails_check_delegates_to_service(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.guardrails import GuardrailResult

    mock_service = AsyncMock()
    mock_service.check_operation.return_value = GuardrailResult(
        safe=True, violations=[]
    )

    import src.guardrails

    monkeypatch.setattr(src.guardrails, "_guardrails_service", mock_service)

    response = client.post(
        "/guardrails/check",
        headers=_auth_headers(),
        json={"operation_text": "echo hello"},
    )
    assert response.status_code == 200
    assert response.json()["safe"] is True


# =============================================================================
# Profiles endpoint test
# =============================================================================


def test_profiles_me_delegates_to_service(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.profiles import AgentProfile, ProfileResult

    mock_service = AsyncMock()
    mock_service.get_profile.return_value = ProfileResult(
        success=True,
        profile=AgentProfile(
            id="prof-1",
            name="cloud-agent",
            agent_type="cloud_agent",
            trust_level=2,
            allowed_operations=["acquire_lock"],
            blocked_operations=[],
            max_file_modifications=50,
        ),
        source="default",
    )

    import src.profiles

    monkeypatch.setattr(src.profiles, "_profiles_service", mock_service)

    response = client.get("/profiles/me", headers=_auth_headers())
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["profile"]["trust_level"] == 2


# =============================================================================
# Audit endpoint test
# =============================================================================


def test_audit_query_delegates_to_service(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_service = AsyncMock()
    mock_service.query.return_value = []

    import src.audit

    monkeypatch.setattr(src.audit, "_audit_service", mock_service)

    response = client.get("/audit", headers=_auth_headers())
    assert response.status_code == 200
    assert response.json()["entries"] == []


# =============================================================================
# Identity spoofing integration test
# =============================================================================


def test_acquire_lock_rejects_identity_spoofing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API key bound to one agent cannot be used to act as another."""
    from src.config import reset_config

    reset_config()
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("COORDINATION_API_KEYS", _TEST_KEY)
    monkeypatch.setenv(
        "COORDINATION_API_KEY_IDENTITIES",
        '{"' + _TEST_KEY + '": {"agent_id": "bound-agent", "agent_type": "codex"}}',
    )
    reset_config()

    app = create_coordination_api()
    test_client = TestClient(app)

    response = test_client.post(
        "/locks/acquire",
        headers=_auth_headers(),
        json={
            "file_path": "src/main.py",
            "agent_id": "different-agent",
            "agent_type": "codex",
        },
    )
    assert response.status_code == 403
    assert "agent_id" in response.json()["detail"]

    reset_config()

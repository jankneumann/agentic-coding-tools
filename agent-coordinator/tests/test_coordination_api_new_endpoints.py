"""Tests for the 14 new HTTP endpoints added in add-mcp-http-proxy-transport.

These tests verify the endpoints are registered, enforce auth where required
(HTTP-1a), and route to the correct service layer. They use FastAPI TestClient
with service-layer mocks to avoid DB dependencies.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.coordination_api import create_coordination_api

# =============================================================================
# Fixtures (reuse pattern from test_coordination_api.py)
# =============================================================================

_TEST_KEY = "test-key-001"


@pytest.fixture()
def _api_config(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Patch config so the API accepts our test key."""
    from src.config import reset_config

    reset_config()

    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("COORDINATION_API_KEYS", _TEST_KEY)
    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")

    reset_config()

    yield

    reset_config()


@pytest.fixture()
def client(_api_config: None) -> TestClient:
    app = create_coordination_api()
    return TestClient(app)


def _auth_headers() -> dict[str, str]:
    return {"X-API-Key": _TEST_KEY}


# =============================================================================
# Endpoint registration (smoke tests — routes exist)
# =============================================================================


def test_all_14_new_routes_registered(_api_config: None) -> None:
    """Smoke test: verify all 14 new endpoints are registered on the app."""
    app = create_coordination_api()
    paths = {route.path for route in app.routes if hasattr(route, "path")}  # type: ignore[attr-defined]

    expected = {
        "/discovery/register",
        "/discovery/agents",
        "/discovery/heartbeat",
        "/discovery/cleanup",
        "/gen-eval/scenarios",
        "/gen-eval/validate",
        "/gen-eval/create",
        "/gen-eval/run",
        "/issues/search",
        "/issues/ready",
        "/issues/blocked",
        "/permissions/request",
        "/approvals/request",
        "/approvals/{request_id}",
    }
    missing = expected - paths
    assert not missing, f"Missing endpoints: {missing}"


# =============================================================================
# Auth tests (HTTP-1a, and analogous scenarios for other write endpoints)
# =============================================================================


def test_discovery_register_requires_auth(client: TestClient) -> None:
    """HTTP-1a: POST /discovery/register without API key → 401."""
    response = client.post(
        "/discovery/register",
        json={"agent_id": "a", "agent_type": "claude_code"},
    )
    assert response.status_code == 401


def test_discovery_heartbeat_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/discovery/heartbeat",
        json={"agent_id": "a", "agent_type": "claude_code"},
    )
    assert response.status_code == 401


def test_discovery_cleanup_requires_auth(client: TestClient) -> None:
    response = client.post("/discovery/cleanup", json={})
    assert response.status_code == 401


def test_gen_eval_validate_requires_auth(client: TestClient) -> None:
    response = client.post("/gen-eval/validate", json={"yaml_content": "x"})
    assert response.status_code == 401


def test_gen_eval_create_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/gen-eval/create",
        json={
            "category": "x",
            "description": "y",
            "interfaces": ["http"],
        },
    )
    assert response.status_code == 401


def test_gen_eval_run_requires_auth(client: TestClient) -> None:
    response = client.post("/gen-eval/run", json={})
    assert response.status_code == 401


def test_issues_search_requires_auth(client: TestClient) -> None:
    response = client.post("/issues/search", json={"query": "bug"})
    assert response.status_code == 401


def test_issues_ready_requires_auth(client: TestClient) -> None:
    response = client.post("/issues/ready", json={})
    assert response.status_code == 401


def test_permissions_request_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/permissions/request",
        json={
            "agent_id": "a",
            "operation": "read_config",
        },
    )
    assert response.status_code == 401


def test_approvals_request_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/approvals/request",
        json={"agent_id": "a", "operation": "delete"},
    )
    assert response.status_code == 401


# =============================================================================
# Read-only endpoints SHOULD NOT require auth
# =============================================================================


def test_discovery_agents_is_public(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /discovery/agents is read-only and requires no auth."""
    from unittest.mock import AsyncMock

    from src import discovery

    mock_service = AsyncMock()
    mock_service.discover = AsyncMock(return_value=type("R", (), {"agents": []})())
    monkeypatch.setattr(
        discovery, "get_discovery_service", lambda: mock_service
    )

    response = client.get("/discovery/agents")
    # No auth header — expect 200 (or similar non-401), not 401
    assert response.status_code != 401


def test_gen_eval_scenarios_is_public(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /gen-eval/scenarios is read-only and requires no auth."""
    response = client.get("/gen-eval/scenarios")
    # Either 200 with empty list, or 5xx if service not mocked — but NOT 401
    assert response.status_code != 401


def test_issues_blocked_is_public(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /issues/blocked is read-only and requires no auth."""
    from unittest.mock import AsyncMock

    from src import issue_service

    mock_service = AsyncMock()
    mock_service.blocked = AsyncMock(return_value=[])
    monkeypatch.setattr(issue_service, "get_issue_service", lambda: mock_service)

    response = client.get("/issues/blocked")
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_approvals_get_by_id_requires_auth(client: TestClient) -> None:
    """GET /approvals/{request_id} requires auth.

    Consistent with GET /approvals/pending, which is also auth-required.
    Approval data is considered sensitive.
    """
    response = client.get("/approvals/some-request-id")
    assert response.status_code == 401

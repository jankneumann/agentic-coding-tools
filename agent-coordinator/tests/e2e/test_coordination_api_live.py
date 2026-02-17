"""E2E tests for the coordination HTTP API against live services.

These tests start a FastAPI TestClient using the real service layer
connected to the running docker-compose PostgreSQL + PostgREST stack.

Requires:
  - docker-compose up -d
  - Environment (optional overrides): AGENT_COORDINATOR_REST_PORT

Run with: pytest tests/e2e/ -m e2e
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

_API_KEY = "e2e-test-key"
_JWT_SECRET = "super-secret-jwt-token-for-local-dev"


def _generate_service_key() -> str:
    """Generate a PostgREST-compatible JWT with postgres role."""
    now = datetime.now(UTC)
    payload = {
        "role": "postgres",
        "iss": "supabase",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm="HS256")


def _make_test_client() -> TestClient:
    """Create a FastAPI TestClient wired to the live database."""
    rest_port = os.environ.get("AGENT_COORDINATOR_REST_PORT", "3000")
    os.environ["SUPABASE_URL"] = f"http://localhost:{rest_port}"
    os.environ["SUPABASE_SERVICE_KEY"] = _generate_service_key()
    os.environ["COORDINATION_API_KEYS"] = _API_KEY
    os.environ["COORDINATION_API_KEY_IDENTITIES"] = "{}"
    os.environ["SUPABASE_REST_PREFIX"] = ""

    from src.config import reset_config

    reset_config()

    # Reset service and DB singletons so they pick up fresh config
    from src.db import reset_db

    reset_db()

    import src.audit
    import src.guardrails
    import src.locks
    import src.memory
    import src.profiles
    import src.work_queue

    src.locks._lock_service = None
    src.memory._memory_service = None
    src.work_queue._work_queue_service = None
    src.guardrails._guardrails_service = None
    src.profiles._profiles_service = None
    src.audit._audit_service = None

    from src.coordination_api import create_coordination_api

    app = create_coordination_api()
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {"X-API-Key": _API_KEY}


@pytest.mark.e2e
class TestHealthEndpoint:
    """Health endpoint should always work regardless of DB state."""

    def test_health_returns_ok(self) -> None:
        client = _make_test_client()
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data


@pytest.mark.e2e
class TestAuthEnforcement:
    """API key auth is enforced on all write endpoints."""

    def test_no_key_returns_401(self) -> None:
        client = _make_test_client()
        response = client.post(
            "/locks/acquire",
            json={"file_path": "x", "agent_id": "a", "agent_type": "t"},
        )
        assert response.status_code == 401

    def test_wrong_key_returns_401(self) -> None:
        client = _make_test_client()
        response = client.post(
            "/locks/acquire",
            headers={"X-API-Key": "bad-key"},
            json={"file_path": "x", "agent_id": "a", "agent_type": "t"},
        )
        assert response.status_code == 401

    def test_lock_status_no_auth_required(self) -> None:
        client = _make_test_client()
        response = client.get("/locks/status/some/file.py")
        # Should not be 401 — lock status is read-only
        assert response.status_code != 401


@pytest.mark.e2e
class TestLockEndpointsLive:
    """Lock endpoints against live database."""

    def test_lock_status_unlocked_file(self) -> None:
        client = _make_test_client()
        response = client.get("/locks/status/e2e-test-nonexistent.py")
        assert response.status_code == 200
        data = response.json()
        assert data["locked"] is False

    def test_acquire_and_check_lock(self) -> None:
        """Acquire a lock, verify it shows as locked, then release it."""
        client = _make_test_client()
        test_file = f"e2e-test-lock-{int(time.time())}.py"

        # Acquire
        acq_response = client.post(
            "/locks/acquire",
            headers=_headers(),
            json={
                "file_path": test_file,
                "agent_id": "e2e-agent",
                "agent_type": "test",
                "reason": "e2e validation",
                "ttl_minutes": 5,
            },
        )
        assert acq_response.status_code == 200
        acq_data = acq_response.json()
        assert acq_data["success"] is True

        # Check status
        status_response = client.get(f"/locks/status/{test_file}")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["locked"] is True

        # Release
        rel_response = client.post(
            "/locks/release",
            headers=_headers(),
            json={"file_path": test_file, "agent_id": "e2e-agent"},
        )
        assert rel_response.status_code == 200
        rel_data = rel_response.json()
        assert rel_data["success"] is True

        # Verify unlocked
        final_response = client.get(f"/locks/status/{test_file}")
        assert final_response.status_code == 200
        assert final_response.json()["locked"] is False


@pytest.mark.e2e
class TestGuardrailsEndpointLive:
    """Guardrails endpoint against live database."""

    def test_safe_operation_passes(self) -> None:
        client = _make_test_client()
        response = client.post(
            "/guardrails/check",
            headers=_headers(),
            json={"operation_text": "echo hello world"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["safe"] is True
        assert data["violations"] == []

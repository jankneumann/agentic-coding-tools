"""E2E tests for the coordination HTTP API against live services.

These tests start a FastAPI TestClient using the real service layer
connected to the running docker-compose PostgreSQL (ParadeDB) stack.

Requires:
  - docker-compose up -d
  - Environment (optional overrides): POSTGRES_DSN

Run with: pytest tests/e2e/ -m e2e
"""

from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

_API_KEY = "e2e-test-key"

POSTGRES_DSN = os.environ.get(
    "POSTGRES_DSN", "postgresql://postgres:postgres@localhost:54322/postgres"
)


def _make_app():
    """Create a fresh FastAPI app wired to DirectPostgresClient."""
    os.environ["DB_BACKEND"] = "postgres"
    os.environ["POSTGRES_DSN"] = POSTGRES_DSN
    os.environ["COORDINATION_API_KEYS"] = _API_KEY
    os.environ["COORDINATION_API_KEY_IDENTITIES"] = "{}"
    os.environ["AGENT_ID"] = "e2e-agent"
    os.environ["AGENT_TYPE"] = "test_agent"
    os.environ.pop("SESSION_ID", None)

    from src.config import reset_config
    from src.db import reset_db

    reset_config()
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

    return create_coordination_api()


def _headers() -> dict[str, str]:
    return {"X-API-Key": _API_KEY}


@pytest.mark.e2e
class TestHealthEndpoint:
    """Health endpoint should always work regardless of DB state."""

    def test_health_returns_ok(self) -> None:
        app = _make_app()
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert "version" in data


@pytest.mark.e2e
class TestAuthEnforcement:
    """API key auth is enforced on all write endpoints."""

    def test_no_key_returns_401(self) -> None:
        app = _make_app()
        with TestClient(app) as client:
            response = client.post(
                "/locks/acquire",
                json={"file_path": "x", "agent_id": "a", "agent_type": "t"},
            )
            assert response.status_code == 401

    def test_wrong_key_returns_401(self) -> None:
        app = _make_app()
        with TestClient(app) as client:
            response = client.post(
                "/locks/acquire",
                headers={"X-API-Key": "bad-key"},
                json={"file_path": "x", "agent_id": "a", "agent_type": "t"},
            )
            assert response.status_code == 401

    def test_lock_status_no_auth_required(self) -> None:
        app = _make_app()
        with TestClient(app) as client:
            response = client.get("/locks/status/some/file.py")
            # Should not be 401 — lock status is read-only
            assert response.status_code != 401


@pytest.mark.e2e
class TestLockEndpointsLive:
    """Lock endpoints against live database."""

    def test_lock_status_unlocked_file(self) -> None:
        app = _make_app()
        with TestClient(app) as client:
            response = client.get("/locks/status/e2e-test-nonexistent.py")
            assert response.status_code == 200
            data = response.json()
            assert data["locked"] is False

    def test_acquire_and_check_lock(self) -> None:
        """Acquire a lock, verify it shows as locked, then release it."""
        app = _make_app()
        with TestClient(app) as client:
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
        app = _make_app()
        with TestClient(app) as client:
            response = client.post(
                "/guardrails/check",
                headers=_headers(),
                json={"operation_text": "echo hello world"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["safe"] is True
            assert data["violations"] == []

"""Tests for port allocator HTTP endpoints and MCP tools."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.coordination_api import create_coordination_api
from src.port_allocator import reset_port_allocator

# ================================================================== #
# Fixtures
# ================================================================== #

_TEST_KEY = "test-key-001"


@pytest.fixture(autouse=True)
def _reset_allocator() -> None:  # type: ignore[misc]
    """Ensure a fresh port allocator for each test."""
    reset_port_allocator()
    yield  # type: ignore[misc]
    reset_port_allocator()


@pytest.fixture()
def _api_config(monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[misc]
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


def _auth() -> dict[str, str]:
    return {"X-API-Key": _TEST_KEY}


# ================================================================== #
# 1. POST /ports/allocate — successful allocation
# ================================================================== #


class TestAllocateEndpoint:
    """Verify successful port allocation via HTTP."""

    def test_allocate_returns_success(self, client: TestClient) -> None:
        resp = client.post(
            "/ports/allocate",
            headers=_auth(),
            json={"session_id": "http-sess-1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "allocation" in data
        assert "env_snippet" in data

    def test_allocate_returns_port_fields(self, client: TestClient) -> None:
        resp = client.post(
            "/ports/allocate",
            headers=_auth(),
            json={"session_id": "http-sess-2"},
        )
        alloc = resp.json()["allocation"]
        assert "db_port" in alloc
        assert "rest_port" in alloc
        assert "realtime_port" in alloc
        assert "api_port" in alloc
        assert "compose_project_name" in alloc
        assert "session_id" in alloc

    def test_allocate_idempotent(self, client: TestClient) -> None:
        resp1 = client.post(
            "/ports/allocate",
            headers=_auth(),
            json={"session_id": "idem"},
        )
        resp2 = client.post(
            "/ports/allocate",
            headers=_auth(),
            json={"session_id": "idem"},
        )
        assert resp1.json()["allocation"]["db_port"] == resp2.json()["allocation"]["db_port"]

    def test_allocate_env_snippet_format(self, client: TestClient) -> None:
        resp = client.post(
            "/ports/allocate",
            headers=_auth(),
            json={"session_id": "snippet-test"},
        )
        snippet = resp.json()["env_snippet"]
        for line in snippet.strip().split("\n"):
            assert line.startswith("export ")
            assert "=" in line


# ================================================================== #
# 2. POST /ports/allocate — auth required
# ================================================================== #


class TestAllocateAuth:
    """Allocate endpoint requires valid API key."""

    def test_missing_api_key_returns_401(self, client: TestClient) -> None:
        resp = client.post(
            "/ports/allocate",
            json={"session_id": "no-key"},
        )
        assert resp.status_code == 401

    def test_invalid_api_key_returns_401(self, client: TestClient) -> None:
        resp = client.post(
            "/ports/allocate",
            headers={"X-API-Key": "bad-key"},
            json={"session_id": "bad-key"},
        )
        assert resp.status_code == 401


# ================================================================== #
# 3. POST /ports/allocate — validation errors
# ================================================================== #


class TestAllocateValidation:
    """Allocate endpoint rejects missing/invalid session_id."""

    def test_missing_session_id_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/ports/allocate",
            headers=_auth(),
            json={},
        )
        assert resp.status_code == 422


# ================================================================== #
# 4. POST /ports/allocate — exhaustion
# ================================================================== #


class TestAllocateExhaustion:
    """When all port blocks are taken, allocate returns success=false."""

    def test_exhaustion_returns_error(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PORT_ALLOC_MAX_SESSIONS", "1")

        from src.config import reset_config

        reset_config()
        reset_port_allocator()

        app = create_coordination_api()
        c = TestClient(app)

        c.post("/ports/allocate", headers=_auth(), json={"session_id": "a"})
        resp = c.post("/ports/allocate", headers=_auth(), json={"session_id": "b"})

        data = resp.json()
        assert data["success"] is False
        assert data["error"] == "no_ports_available"


# ================================================================== #
# 5. POST /ports/release — successful release
# ================================================================== #


class TestReleaseEndpoint:
    """Verify port release via HTTP."""

    def test_release_returns_success(self, client: TestClient) -> None:
        client.post(
            "/ports/allocate", headers=_auth(), json={"session_id": "rel"}
        )
        resp = client.post(
            "/ports/release", headers=_auth(), json={"session_id": "rel"}
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_release_idempotent(self, client: TestClient) -> None:
        resp = client.post(
            "/ports/release",
            headers=_auth(),
            json={"session_id": "never-allocated"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True


# ================================================================== #
# 6. POST /ports/release — auth required
# ================================================================== #


class TestReleaseAuth:
    """Release endpoint requires valid API key."""

    def test_missing_api_key_returns_401(self, client: TestClient) -> None:
        resp = client.post(
            "/ports/release",
            json={"session_id": "no-key"},
        )
        assert resp.status_code == 401

    def test_missing_session_id_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/ports/release",
            headers=_auth(),
            json={},
        )
        assert resp.status_code == 422


# ================================================================== #
# 7. GET /ports/status — read-only, no auth
# ================================================================== #


class TestStatusEndpoint:
    """Status endpoint is read-only and needs no API key."""

    def test_status_no_auth_required(self, client: TestClient) -> None:
        resp = client.get("/ports/status")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_status_shows_allocations(self, client: TestClient) -> None:
        client.post(
            "/ports/allocate", headers=_auth(), json={"session_id": "vis"}
        )
        resp = client.get("/ports/status")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["session_id"] == "vis"
        assert "remaining_ttl_minutes" in data[0]

    def test_status_shows_port_fields(self, client: TestClient) -> None:
        client.post(
            "/ports/allocate", headers=_auth(), json={"session_id": "fields"}
        )
        entry = client.get("/ports/status").json()[0]
        for field in ("db_port", "rest_port", "realtime_port", "api_port",
                       "compose_project_name", "remaining_ttl_minutes"):
            assert field in entry

    def test_status_empty_after_release(self, client: TestClient) -> None:
        client.post(
            "/ports/allocate", headers=_auth(), json={"session_id": "gone"}
        )
        client.post(
            "/ports/release", headers=_auth(), json={"session_id": "gone"}
        )
        assert client.get("/ports/status").json() == []


# ================================================================== #
# 8. Standalone operation — no DB needed
# ================================================================== #


class TestStandaloneApi:
    """Port allocator endpoints don't touch the database."""

    def test_allocate_does_not_use_db(self, client: TestClient) -> None:
        """Port allocation succeeds even though no real DB is available."""
        resp = client.post(
            "/ports/allocate",
            headers=_auth(),
            json={"session_id": "standalone"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_status_does_not_use_db(self, client: TestClient) -> None:
        """Port status is pure in-memory, no DB call."""
        resp = client.get("/ports/status")
        assert resp.status_code == 200

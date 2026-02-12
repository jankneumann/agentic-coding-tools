"""Integration test fixtures for Agent Coordinator.

Requires local Supabase running via docker-compose:

    docker-compose up -d

Tests are automatically skipped if PostgREST is not reachable.
"""

import time

import httpx
import jwt
import pytest

from src.config import SupabaseConfig, reset_config
from src.db import SupabaseClient
from src.locks import LockService
from src.work_queue import WorkQueueService

# Local Supabase connection details (from docker-compose.yml)
POSTGREST_URL = "http://localhost:3000"
JWT_SECRET = "super-secret-jwt-token-for-local-dev"


def _generate_service_jwt() -> str:
    """Generate a JWT with service_role claim for local PostgREST."""
    payload = {
        "role": "service_role",
        "iss": "supabase",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _is_supabase_running() -> bool:
    """Check if local PostgREST is reachable."""
    try:
        response = httpx.get(POSTGREST_URL, timeout=2.0)
        return response.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


# Check once at import time
_supabase_available = _is_supabase_running()


@pytest.fixture
def service_key():
    """Generate a service role JWT for PostgREST."""
    return _generate_service_jwt()


@pytest.fixture
def supabase_config(service_key):
    """Supabase config pointing at local PostgREST (no /rest/v1 prefix)."""
    return SupabaseConfig(url=POSTGREST_URL, service_key=service_key, rest_prefix="")


@pytest.fixture(autouse=True)
def setup_env(monkeypatch, service_key):
    """Override parent's setup_env with integration test settings."""
    monkeypatch.setenv("SUPABASE_URL", POSTGREST_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", service_key)
    monkeypatch.setenv("SUPABASE_REST_PREFIX", "")
    monkeypatch.setenv("AGENT_ID", "integ-agent-1")
    monkeypatch.setenv("AGENT_TYPE", "test_agent")
    monkeypatch.setenv("SESSION_ID", "integ-session-1")
    monkeypatch.setenv("LOCK_TTL_MINUTES", "5")
    yield
    reset_config()


@pytest.fixture
def db_client(supabase_config):
    """Supabase client for integration tests."""
    return SupabaseClient(supabase_config)


@pytest.fixture
def lock_service(db_client):
    """Lock service for integration tests."""
    return LockService(db=db_client)


@pytest.fixture
def work_queue(db_client):
    """Work queue service for integration tests."""
    return WorkQueueService(db=db_client)


@pytest.fixture
def make_agent(supabase_config):
    """Factory fixture to create services for additional agents.

    Returns (SupabaseClient, LockService, WorkQueueService) tuple.
    """
    def _make(agent_id: str):
        client = SupabaseClient(supabase_config)
        return client, LockService(db=client), WorkQueueService(db=client)
    return _make


@pytest.fixture(autouse=True)
async def cleanup_tables(supabase_config):
    """Clean up all test data before and after each test.

    Also handles skipping when Supabase is not available — this must be
    checked here (not in a separate fixture) because async fixtures can
    run before sync autouse fixtures.
    """
    if not _supabase_available:
        pytest.skip("Local Supabase not running (start with: docker-compose up -d)")

    async def _truncate():
        headers = {
            "apikey": supabase_config.service_key,
            "Authorization": f"Bearer {supabase_config.service_key}",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            for table, col in [("file_locks", "file_path"), ("work_queue", "id")]:
                await client.delete(
                    f"{POSTGREST_URL}/{table}?{col}=not.is.null",
                    headers=headers,
                )

    await _truncate()
    yield
    await _truncate()

"""E2E test fixtures for coordination HTTP API with DirectPostgresClient.

Tests the full HTTP API stack (FastAPI → Service Layer → asyncpg → PostgreSQL)
without requiring PostgREST.

Requires: docker-compose up -d
"""

import asyncio
import os

import asyncpg
import pytest
from fastapi.testclient import TestClient

POSTGRES_DSN = os.environ.get(
    "POSTGRES_DSN", "postgresql://postgres:postgres@localhost:54322/postgres"
)

_API_KEY = "e2e-test-key"

# Tables to truncate between tests (audit_log is immutable)
_TABLES = [
    "handoff_documents",
    "memory_episodic",
    "memory_working",
    "memory_procedural",
    "work_queue",
    "file_locks",
    "agent_sessions",
]


def _is_postgres_running() -> bool:
    """Check if PostgreSQL is reachable."""

    async def _check() -> bool:
        try:
            conn = await asyncpg.connect(dsn=POSTGRES_DSN, timeout=2.0)
            await conn.close()
            return True
        except (OSError, asyncpg.PostgresError, TimeoutError, Exception):
            return False

    try:
        return asyncio.run(_check())
    except RuntimeError:
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(lambda: asyncio.run(_check())).result(timeout=5)


_postgres_available = _is_postgres_running()


def pytest_collection_modifyitems(items):
    """Automatically mark all tests in the e2e directory with the e2e marker."""
    for item in items:
        if "/e2e/" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)


def _reset_singletons() -> None:
    """Reset all service singletons so they pick up fresh config/db."""
    from src.config import reset_config
    from src.db import reset_db

    reset_config()
    reset_db()

    import src.audit
    import src.guardrails
    import src.handoffs
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
    src.handoffs._handoff_service = None


def _make_app():
    """Create a fresh FastAPI app wired to DirectPostgresClient."""
    os.environ["DB_BACKEND"] = "postgres"
    os.environ["POSTGRES_DSN"] = POSTGRES_DSN
    os.environ["COORDINATION_API_KEYS"] = _API_KEY
    os.environ["COORDINATION_API_KEY_IDENTITIES"] = "{}"
    os.environ["AGENT_ID"] = "e2e-agent"
    os.environ["AGENT_TYPE"] = "test_agent"
    os.environ["COORDINATOR_PROFILE"] = "local"
    # Ensure SESSION_ID is unset so handoff writes don't hit FK constraint
    os.environ.pop("SESSION_ID", None)

    _reset_singletons()

    from src.coordination_api import create_coordination_api

    return create_coordination_api()


@pytest.fixture
def api_client():
    """FastAPI TestClient with DirectPostgresClient backend.

    Uses context manager to maintain a single event loop across
    multiple requests within the same test (required for asyncpg).
    """
    app = _make_app()
    with TestClient(app) as client:
        yield client
    _reset_singletons()


@pytest.fixture
def auth_headers():
    """Authentication headers for API requests."""
    return {"X-API-Key": _API_KEY}


@pytest.fixture(autouse=True)
async def cleanup_tables():
    """Truncate test data before/after each test."""
    if not _postgres_available:
        pytest.skip("PostgreSQL not running (start with: docker-compose up -d)")

    async def _truncate():
        conn = await asyncpg.connect(dsn=POSTGRES_DSN, timeout=5.0)
        try:
            for table in _TABLES:
                await conn.execute(f"DELETE FROM {table}")
        finally:
            await conn.close()

    await _truncate()
    yield
    await _truncate()

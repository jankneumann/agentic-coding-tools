"""Integration test fixtures for DirectPostgresClient (asyncpg).

Requires local PostgreSQL running via docker-compose:

    docker-compose up -d

Tests are automatically skipped if PostgreSQL is not reachable.
"""

import asyncio
import os

import asyncpg
import pytest

from src.db_postgres import DirectPostgresClient
from src.locks import LockService
from src.memory import MemoryService
from src.work_queue import WorkQueueService

# Local PostgreSQL connection details (from docker-compose.yml)
POSTGRES_DSN = os.environ.get(
    "POSTGRES_DSN", "postgresql://postgres:postgres@localhost:54322/postgres"
)

# Tables to truncate between tests (order matters for FK constraints).
# audit_log is immutable (has a trigger preventing DELETE) — skip it.
_TABLES = [
    "handoff_documents",
    "work_queue_projection_heads",
    "memory_episodic",
    "work_queue",
    "file_locks",
    "agent_sessions",
]


def _is_postgres_running() -> bool:
    """Check if local PostgreSQL is reachable via asyncpg."""

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
        # Already in an event loop — use a thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(lambda: asyncio.run(_check())).result(timeout=5)


# Check once at import time
_postgres_available = _is_postgres_running()


@pytest.fixture(autouse=True)
async def cleanup_tables():
    """Clean up all test data before and after each test.

    Uses a dedicated connection (not the test's DirectPostgresClient)
    to avoid pool conflicts.
    """
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


@pytest.fixture(autouse=True)
def setup_postgres_env(monkeypatch):
    """Override environment with postgres-backend settings.

    Sets DB_BACKEND=postgres so config.from_env() does not require
    SUPABASE_URL / SUPABASE_SERVICE_KEY.
    """
    monkeypatch.setenv("DB_BACKEND", "postgres")
    monkeypatch.setenv("POSTGRES_DSN", POSTGRES_DSN)
    # Projection publication is a coordinator-only trust-3 operation. These
    # fixtures exercise that publisher path; claim/complete tests still pass
    # their ordinary worker identity explicitly at the call site.
    monkeypatch.setenv("AGENT_ID", "claude-local")
    monkeypatch.setenv("AGENT_TYPE", "claude_code")
    monkeypatch.setenv("SESSION_ID", "integ-pg-session-1")
    monkeypatch.setenv("LOCK_TTL_MINUTES", "5")
    monkeypatch.setenv("COORDINATOR_PROFILE", "local")
    yield
    from src.config import reset_config
    from src.db import reset_db

    reset_config()
    reset_db()


@pytest.fixture
def postgres_db():
    """DirectPostgresClient using the test DSN."""
    from src.config import PostgresConfig

    return DirectPostgresClient(PostgresConfig(dsn=POSTGRES_DSN))


@pytest.fixture
def pg_lock_service(postgres_db):
    """Lock service using DirectPostgresClient."""
    return LockService(db=postgres_db)


@pytest.fixture
def pg_work_queue(postgres_db):
    """Work queue service using DirectPostgresClient."""
    return WorkQueueService(db=postgres_db)


@pytest.fixture
def pg_memory_service(postgres_db):
    """Memory service using DirectPostgresClient."""
    return MemoryService(db=postgres_db)


@pytest.fixture
def make_pg_agent():
    """Factory fixture to create services for additional agents.

    Returns (DirectPostgresClient, LockService, WorkQueueService) tuple.
    """
    from src.config import PostgresConfig

    def _make(agent_id: str):
        client = DirectPostgresClient(PostgresConfig(dsn=POSTGRES_DSN))
        return client, LockService(db=client), WorkQueueService(db=client)

    return _make


def pytest_sessionfinish(session, exitstatus):
    """Required Postgres gates fail closed when integration coverage skips."""
    if os.environ.get("REQUIRE_POSTGRES_TESTS") != "1":
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    skipped = reporter.stats.get("skipped", []) if reporter is not None else []
    if not _postgres_available or skipped:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED

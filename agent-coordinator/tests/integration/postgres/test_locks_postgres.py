"""Integration tests for file locking via DirectPostgresClient (asyncpg).

Tests the PL/pgSQL acquire_lock/release_lock functions through the
Python LockService, hitting real PostgreSQL via asyncpg.

Run with:
    docker-compose up -d
    pytest tests/integration/test_locks_postgres.py -v
"""

import asyncio

import pytest

pytestmark = pytest.mark.integration


# =============================================================================
# Lock Lifecycle
# =============================================================================


class TestLockLifecyclePostgres:
    """Test basic lock acquire/release operations via asyncpg."""

    async def test_acquire_lock(self, pg_lock_service):
        result = await pg_lock_service.acquire(
            "src/main.py",
            agent_id="integ-pg-agent-1",
            agent_type="test_agent",
            reason="integration test",
        )
        assert result.success is True
        assert result.action == "acquired"
        assert result.file_path == "src/main.py"
        assert result.expires_at is not None

    async def test_acquire_and_release(self, pg_lock_service):
        await pg_lock_service.acquire(
            "src/main.py",
            agent_id="integ-pg-agent-1",
            agent_type="test_agent",
        )

        result = await pg_lock_service.release("src/main.py", agent_id="integ-pg-agent-1")
        assert result.success is True
        assert result.action == "released"

        # Verify lock is gone
        lock = await pg_lock_service.is_locked("src/main.py")
        assert lock is None

    async def test_acquire_refresh_same_agent(self, pg_lock_service):
        """Same agent re-acquiring a lock refreshes instead of conflicting."""
        await pg_lock_service.acquire(
            "src/main.py",
            agent_id="integ-pg-agent-1",
            agent_type="test_agent",
            reason="first acquire",
        )

        result = await pg_lock_service.acquire(
            "src/main.py",
            agent_id="integ-pg-agent-1",
            agent_type="test_agent",
            reason="second acquire",
        )
        assert result.success is True
        assert result.action == "refreshed"

    async def test_release_nonexistent_lock(self, pg_lock_service):
        result = await pg_lock_service.release("nonexistent.py", agent_id="integ-pg-agent-1")
        assert result.success is False


# =============================================================================
# Lock Conflicts
# =============================================================================


class TestLockConflictsPostgres:
    """Test lock conflict and ownership scenarios via asyncpg."""

    async def test_acquire_conflict(self, pg_lock_service, make_pg_agent):
        """Second agent cannot acquire a lock held by another."""
        await pg_lock_service.acquire(
            "src/main.py",
            agent_id="integ-pg-agent-1",
            agent_type="test_agent",
        )

        _, agent2_locks, _ = make_pg_agent("integ-pg-agent-2")
        result = await agent2_locks.acquire(
            "src/main.py",
            agent_id="integ-pg-agent-2",
            agent_type="test_agent",
        )
        assert result.success is False
        assert result.reason == "locked_by_other"
        assert result.locked_by == "integ-pg-agent-1"

    async def test_release_wrong_agent(self, pg_lock_service, make_pg_agent):
        """Agent cannot release a lock held by another."""
        await pg_lock_service.acquire(
            "src/main.py",
            agent_id="integ-pg-agent-1",
            agent_type="test_agent",
        )

        _, agent2_locks, _ = make_pg_agent("integ-pg-agent-2")
        result = await agent2_locks.release("src/main.py", agent_id="integ-pg-agent-2")
        assert result.success is False

    async def test_expired_lock_cleanup(self, pg_lock_service, make_pg_agent):
        """Expired locks are cleaned up when a new acquire is attempted."""
        # Acquire with negative TTL so expires_at is in the past (NOW() - 1 min).
        await pg_lock_service.acquire(
            "src/main.py",
            agent_id="integ-pg-agent-1",
            agent_type="test_agent",
            ttl_minutes=-1,
        )

        # Agent 2 can acquire because acquire_lock cleans expired locks first
        _, agent2_locks, _ = make_pg_agent("integ-pg-agent-2")
        result = await agent2_locks.acquire(
            "src/main.py",
            agent_id="integ-pg-agent-2",
            agent_type="test_agent",
        )
        assert result.success is True
        assert result.action == "acquired"

    async def test_concurrent_acquire_one_wins(self, pg_lock_service, make_pg_agent):
        """When two agents race for a lock, exactly one succeeds."""
        _, agent2_locks, _ = make_pg_agent("integ-pg-agent-2")

        results = await asyncio.gather(
            pg_lock_service.acquire(
                "src/main.py",
                agent_id="integ-pg-agent-1",
                agent_type="test_agent",
            ),
            agent2_locks.acquire(
                "src/main.py",
                agent_id="integ-pg-agent-2",
                agent_type="test_agent",
            ),
        )

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 1
        assert len(failures) == 1


# =============================================================================
# Lock Queries
# =============================================================================


class TestLockQueriesPostgres:
    """Test lock query and check operations via asyncpg."""

    async def test_check_all_active_locks(self, pg_lock_service, make_pg_agent):
        await pg_lock_service.acquire(
            "src/main.py",
            agent_id="integ-pg-agent-1",
            agent_type="test_agent",
        )

        _, agent2_locks, _ = make_pg_agent("integ-pg-agent-2")
        await agent2_locks.acquire(
            "src/utils.py",
            agent_id="integ-pg-agent-2",
            agent_type="test_agent",
        )

        locks = await pg_lock_service.check()
        assert len(locks) == 2
        paths = {lock.file_path for lock in locks}
        assert paths == {"src/main.py", "src/utils.py"}

    async def test_check_specific_files(self, pg_lock_service):
        await pg_lock_service.acquire(
            "src/main.py", agent_id="integ-pg-agent-1", agent_type="test_agent"
        )
        await pg_lock_service.acquire(
            "src/utils.py", agent_id="integ-pg-agent-1", agent_type="test_agent"
        )

        locks = await pg_lock_service.check(["src/main.py"])
        assert len(locks) == 1
        assert locks[0].file_path == "src/main.py"

    async def test_is_locked(self, pg_lock_service):
        await pg_lock_service.acquire(
            "src/main.py", agent_id="integ-pg-agent-1", agent_type="test_agent"
        )

        lock = await pg_lock_service.is_locked("src/main.py")
        assert lock is not None
        assert lock.locked_by == "integ-pg-agent-1"

        lock = await pg_lock_service.is_locked("src/other.py")
        assert lock is None

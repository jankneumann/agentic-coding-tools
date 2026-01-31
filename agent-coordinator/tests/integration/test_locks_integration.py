"""Integration tests for file locking against local Supabase.

Tests the PL/pgSQL acquire_lock/release_lock functions through the
Python LockService, hitting real PostgREST + PostgreSQL.

Run with:
    docker-compose up -d
    pytest tests/integration/test_locks_integration.py -v
"""

import asyncio

import pytest

pytestmark = pytest.mark.integration


# =============================================================================
# Lock Lifecycle
# =============================================================================


class TestLockLifecycle:
    """Test basic lock acquire/release operations."""

    async def test_acquire_lock(self, lock_service):
        result = await lock_service.acquire(
            "src/main.py",
            agent_id="integ-agent-1",
            agent_type="test_agent",
            reason="integration test",
        )
        assert result.success is True
        assert result.action == "acquired"
        assert result.file_path == "src/main.py"
        assert result.expires_at is not None

    async def test_acquire_and_release(self, lock_service):
        await lock_service.acquire(
            "src/main.py",
            agent_id="integ-agent-1",
            agent_type="test_agent",
        )

        result = await lock_service.release("src/main.py", agent_id="integ-agent-1")
        assert result.success is True
        assert result.action == "released"

        # Verify lock is gone
        lock = await lock_service.is_locked("src/main.py")
        assert lock is None

    async def test_acquire_refresh_same_agent(self, lock_service):
        """Same agent re-acquiring a lock refreshes instead of conflicting."""
        await lock_service.acquire(
            "src/main.py",
            agent_id="integ-agent-1",
            agent_type="test_agent",
            reason="first acquire",
        )

        result = await lock_service.acquire(
            "src/main.py",
            agent_id="integ-agent-1",
            agent_type="test_agent",
            reason="second acquire",
        )
        assert result.success is True
        assert result.action == "refreshed"

    async def test_release_nonexistent_lock(self, lock_service):
        result = await lock_service.release("nonexistent.py", agent_id="integ-agent-1")
        assert result.success is False


# =============================================================================
# Lock Conflicts
# =============================================================================


class TestLockConflicts:
    """Test lock conflict and ownership scenarios."""

    async def test_acquire_conflict(self, lock_service, make_agent):
        """Second agent cannot acquire a lock held by another."""
        await lock_service.acquire(
            "src/main.py",
            agent_id="integ-agent-1",
            agent_type="test_agent",
        )

        _, agent2_locks, _ = make_agent("integ-agent-2")
        result = await agent2_locks.acquire(
            "src/main.py",
            agent_id="integ-agent-2",
            agent_type="test_agent",
        )
        assert result.success is False
        assert result.reason == "locked_by_other"
        assert result.locked_by == "integ-agent-1"

    async def test_release_wrong_agent(self, lock_service, make_agent):
        """Agent cannot release a lock held by another."""
        await lock_service.acquire(
            "src/main.py",
            agent_id="integ-agent-1",
            agent_type="test_agent",
        )

        _, agent2_locks, _ = make_agent("integ-agent-2")
        result = await agent2_locks.release("src/main.py", agent_id="integ-agent-2")
        assert result.success is False

    async def test_expired_lock_cleanup(self, lock_service, make_agent):
        """Expired locks are cleaned up when a new acquire is attempted."""
        # Acquire with negative TTL so expires_at is in the past (NOW() - 1 min).
        # The cleanup DELETE in acquire_lock removes locks where expires_at < NOW().
        await lock_service.acquire(
            "src/main.py",
            agent_id="integ-agent-1",
            agent_type="test_agent",
            ttl_minutes=-1,
        )

        # Agent 2 can acquire because acquire_lock cleans expired locks first
        _, agent2_locks, _ = make_agent("integ-agent-2")
        result = await agent2_locks.acquire(
            "src/main.py",
            agent_id="integ-agent-2",
            agent_type="test_agent",
        )
        assert result.success is True
        assert result.action == "acquired"

    async def test_concurrent_acquire_one_wins(self, lock_service, make_agent):
        """When two agents race for a lock, exactly one succeeds."""
        _, agent2_locks, _ = make_agent("integ-agent-2")

        results = await asyncio.gather(
            lock_service.acquire(
                "src/main.py",
                agent_id="integ-agent-1",
                agent_type="test_agent",
            ),
            agent2_locks.acquire(
                "src/main.py",
                agent_id="integ-agent-2",
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


class TestLockQueries:
    """Test lock query and check operations."""

    async def test_check_all_active_locks(self, lock_service, make_agent):
        await lock_service.acquire(
            "src/main.py",
            agent_id="integ-agent-1",
            agent_type="test_agent",
        )

        _, agent2_locks, _ = make_agent("integ-agent-2")
        await agent2_locks.acquire(
            "src/utils.py",
            agent_id="integ-agent-2",
            agent_type="test_agent",
        )

        locks = await lock_service.check()
        assert len(locks) == 2
        paths = {lock.file_path for lock in locks}
        assert paths == {"src/main.py", "src/utils.py"}

    async def test_check_specific_files(self, lock_service):
        await lock_service.acquire(
            "src/main.py", agent_id="integ-agent-1", agent_type="test_agent"
        )
        await lock_service.acquire(
            "src/utils.py", agent_id="integ-agent-1", agent_type="test_agent"
        )

        locks = await lock_service.check(["src/main.py"])
        assert len(locks) == 1
        assert locks[0].file_path == "src/main.py"

    async def test_is_locked(self, lock_service):
        await lock_service.acquire(
            "src/main.py", agent_id="integ-agent-1", agent_type="test_agent"
        )

        lock = await lock_service.is_locked("src/main.py")
        assert lock is not None
        assert lock.locked_by == "integ-agent-1"

        lock = await lock_service.is_locked("src/other.py")
        assert lock is None

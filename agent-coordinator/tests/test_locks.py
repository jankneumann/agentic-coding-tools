"""Tests for the file locking service."""

import pytest
from httpx import Response

from src.locks import Lock, LockResult, LockService
from src.policy_engine import PolicyDecision


class TestLockService:
    """Tests for LockService."""

    @pytest.mark.asyncio
    async def test_acquire_lock_success(
        self, mock_supabase, db_client, lock_acquired_response
    ):
        """Test successful lock acquisition."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/acquire_lock"
        ).mock(return_value=Response(200, json=lock_acquired_response))

        service = LockService(db_client)
        result = await service.acquire("src/main.py", reason="testing")

        assert result.success is True
        assert result.action == "acquired"
        assert result.file_path == "src/main.py"
        assert result.expires_at is not None

    @pytest.mark.asyncio
    async def test_acquire_lock_conflict(
        self, mock_supabase, db_client, lock_conflict_response
    ):
        """Test lock acquisition when file is locked by another agent."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/acquire_lock"
        ).mock(return_value=Response(200, json=lock_conflict_response))

        service = LockService(db_client)
        result = await service.acquire("src/main.py")

        assert result.success is False
        assert result.reason == "locked_by_other"
        assert result.locked_by == "other-agent"

    @pytest.mark.asyncio
    async def test_release_lock_success(
        self, mock_supabase, db_client, lock_released_response
    ):
        """Test successful lock release."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/release_lock"
        ).mock(return_value=Response(200, json=lock_released_response))

        service = LockService(db_client)
        result = await service.release("src/main.py")

        assert result.success is True
        assert result.action == "released"
        assert result.file_path == "src/main.py"

    @pytest.mark.asyncio
    async def test_check_all_locks(
        self, mock_supabase, db_client, active_locks_response
    ):
        """Test checking all active locks."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/file_locks"
        ).mock(return_value=Response(200, json=active_locks_response))

        service = LockService(db_client)
        locks = await service.check()

        assert len(locks) == 2
        assert locks[0].file_path == "src/main.py"
        assert locks[0].locked_by == "agent-1"
        assert locks[1].file_path == "src/utils.py"
        assert locks[1].locked_by == "agent-2"

    @pytest.mark.asyncio
    async def test_check_specific_files(
        self, mock_supabase, db_client, active_locks_response
    ):
        """Test checking locks for specific files."""
        # Return only the first lock
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/file_locks"
        ).mock(return_value=Response(200, json=[active_locks_response[0]]))

        service = LockService(db_client)
        locks = await service.check(file_paths=["src/main.py"])

        assert len(locks) == 1
        assert locks[0].file_path == "src/main.py"

    @pytest.mark.asyncio
    async def test_is_locked_returns_lock(
        self, mock_supabase, db_client, active_locks_response
    ):
        """Test is_locked returns lock when file is locked."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/file_locks"
        ).mock(return_value=Response(200, json=[active_locks_response[0]]))

        service = LockService(db_client)
        lock = await service.is_locked("src/main.py")

        assert lock is not None
        assert lock.file_path == "src/main.py"
        assert lock.locked_by == "agent-1"

    @pytest.mark.asyncio
    async def test_is_locked_returns_none(self, mock_supabase, db_client):
        """Test is_locked returns None when file is not locked."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/file_locks"
        ).mock(return_value=Response(200, json=[]))

        service = LockService(db_client)
        lock = await service.is_locked("src/unlocked.py")

        assert lock is None

    @pytest.mark.asyncio
    async def test_extend_lock_success(
        self, mock_supabase, db_client, lock_acquired_response
    ):
        """Test extending a lock you already hold."""
        # Extend returns same response as acquire with action='refreshed'
        response = lock_acquired_response.copy()
        response["action"] = "refreshed"

        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/acquire_lock"
        ).mock(return_value=Response(200, json=response))

        service = LockService(db_client)
        result = await service.extend("src/main.py", ttl_minutes=60)

        assert result.success is True
        assert result.action == "refreshed"

    @pytest.mark.asyncio
    async def test_acquire_lock_denied_by_policy(self, monkeypatch):
        """Acquire is blocked when policy engine denies the operation."""

        class DenyPolicyEngine:
            async def check_operation(self, **_kwargs):
                return PolicyDecision.deny("insufficient_trust_level")

        class FailDB:
            async def rpc(self, *_args, **_kwargs):
                raise AssertionError("DB RPC should not be called when denied")

        monkeypatch.setattr(
            "src.policy_engine.get_policy_engine",
            lambda: DenyPolicyEngine(),
        )

        service = LockService(FailDB())
        result = await service.acquire("src/main.py")

        assert result.success is False
        assert result.reason == "insufficient_trust_level"


class TestLockDataClasses:
    """Tests for Lock and LockResult dataclasses."""

    def test_lock_from_dict(self, active_locks_response):
        """Test creating a Lock from a dictionary."""
        lock = Lock.from_dict(active_locks_response[0])

        assert lock.file_path == "src/main.py"
        assert lock.locked_by == "agent-1"
        assert lock.agent_type == "claude_code"
        assert lock.reason == "refactoring"
        assert lock.locked_at is not None
        assert lock.expires_at is not None

    def test_lock_result_from_dict_success(self, lock_acquired_response):
        """Test creating a LockResult from a success response."""
        result = LockResult.from_dict(lock_acquired_response)

        assert result.success is True
        assert result.action == "acquired"
        assert result.file_path == "src/main.py"
        assert result.expires_at is not None

    def test_lock_result_from_dict_failure(self, lock_conflict_response):
        """Test creating a LockResult from a failure response."""
        result = LockResult.from_dict(lock_conflict_response)

        assert result.success is False
        assert result.reason == "locked_by_other"
        assert result.locked_by == "other-agent"


class TestLockAtomicity:
    """Tests for lock atomicity and race conditions."""

    @pytest.mark.asyncio
    async def test_concurrent_acquire_first_wins(self, mock_supabase, db_client):
        """Test that only the first agent acquires the lock."""
        # First request succeeds
        first_response = {
            "success": True,
            "action": "acquired",
            "file_path": "src/main.py",
            "expires_at": "2024-01-01T12:00:00+00:00",
        }

        # Second request fails (lock already held)
        second_response = {
            "success": False,
            "reason": "locked_by_other",
            "locked_by": "agent-1",
        }

        # Mock to return different responses
        call_count = [0]

        def response_callback(request):
            call_count[0] += 1
            if call_count[0] == 1:
                return Response(200, json=first_response)
            return Response(200, json=second_response)

        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/acquire_lock"
        ).mock(side_effect=response_callback)

        service = LockService(db_client)

        # First acquire succeeds
        result1 = await service.acquire("src/main.py")
        assert result1.success is True

        # Second acquire fails
        result2 = await service.acquire("src/main.py")
        assert result2.success is False
        assert result2.reason == "locked_by_other"

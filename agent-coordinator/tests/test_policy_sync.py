"""Tests for the PostgreSQL LISTEN/NOTIFY policy sync service."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.policy_sync import (
    CHANNEL,
    PgListenNotifyPolicySyncService,
    get_policy_sync_service,
    reset_policy_sync_service,
)


def _make_mock_connection(*, is_closed: bool = False) -> MagicMock:
    """Create a mock asyncpg connection with the required interface."""
    conn = MagicMock()
    conn.add_listener = AsyncMock()
    conn.remove_listener = AsyncMock()
    conn.close = AsyncMock()
    conn.is_closed = MagicMock(return_value=is_closed)
    return conn


class TestStartStopLifecycle:
    """Verify start sets running, stop cancels the listen task."""

    async def test_start_sets_running(self) -> None:
        svc = PgListenNotifyPolicySyncService(max_retries=0, backoff_seconds=0.0)
        mock_conn = _make_mock_connection()

        with patch("asyncpg.connect", AsyncMock(return_value=mock_conn)):
            await svc.start()
            assert svc.running is True
            # Give the listen task a moment to start
            await asyncio.sleep(0.05)
            await svc.stop()
            assert svc.running is False

    async def test_start_is_idempotent(self) -> None:
        svc = PgListenNotifyPolicySyncService(max_retries=0, backoff_seconds=0.0)
        mock_conn = _make_mock_connection()

        with patch("asyncpg.connect", AsyncMock(return_value=mock_conn)):
            await svc.start()
            task1 = svc._listen_task
            await svc.start()  # second call should be no-op
            task2 = svc._listen_task
            assert task1 is task2
            await svc.stop()

    async def test_stop_without_start(self) -> None:
        """Stopping a service that was never started should not raise."""
        svc = PgListenNotifyPolicySyncService()
        await svc.stop()  # should not raise
        assert svc.running is False


class TestOnPolicyChange:
    """Verify callback registration."""

    def test_registers_callback(self) -> None:
        svc = PgListenNotifyPolicySyncService()

        async def my_callback(payload: str) -> None:
            pass

        svc.on_policy_change(my_callback)
        assert my_callback in svc._callbacks

    def test_registers_multiple_callbacks(self) -> None:
        svc = PgListenNotifyPolicySyncService()

        async def cb1(payload: str) -> None:
            pass

        async def cb2(payload: str) -> None:
            pass

        svc.on_policy_change(cb1)
        svc.on_policy_change(cb2)
        assert len(svc._callbacks) == 2


class TestNotificationTriggersCallback:
    """Verify that a simulated NOTIFY fires registered callbacks."""

    async def test_notification_invokes_callback(self) -> None:
        svc = PgListenNotifyPolicySyncService(max_retries=0, backoff_seconds=0.0)
        received: list[str] = []

        async def track(payload: str) -> None:
            received.append(payload)

        svc.on_policy_change(track)

        mock_conn = _make_mock_connection()
        # Capture the notification handler registered via add_listener
        captured_handler: list = []

        async def capture_add_listener(channel: str, handler: object) -> None:
            captured_handler.append(handler)

        mock_conn.add_listener = capture_add_listener  # type: ignore[assignment]

        # Make the connection close itself after we grab the handler
        call_count = 0

        def is_closed_side_effect() -> bool:
            nonlocal call_count
            call_count += 1
            # Let it run one iteration, then report closed
            return call_count > 2

        mock_conn.is_closed = is_closed_side_effect

        with patch("asyncpg.connect", AsyncMock(return_value=mock_conn)):
            await svc.start()
            # Wait for connect and listener registration
            await asyncio.sleep(0.1)

            assert len(captured_handler) == 1
            handler = captured_handler[0]

            # Simulate a notification
            handler(mock_conn, 12345, CHANNEL, "my_policy")
            # Let the callback task run
            await asyncio.sleep(0.05)

            assert received == ["my_policy"]
            await svc.stop()


class TestReconnectionOnFailure:
    """Verify retry with exponential backoff on connection failure."""

    async def test_retries_on_connect_failure(self) -> None:
        svc = PgListenNotifyPolicySyncService(
            max_retries=3, backoff_seconds=0.01
        )
        connect_attempts = 0

        async def failing_connect(*args: object, **kwargs: object) -> MagicMock:
            nonlocal connect_attempts
            connect_attempts += 1
            if connect_attempts <= 2:
                raise ConnectionError("simulated failure")
            # Third attempt succeeds — stop the service from inside
            svc._running = False
            conn = _make_mock_connection(is_closed=True)
            return conn

        with patch("asyncpg.connect", side_effect=failing_connect):
            await svc.start()
            # Give it time to retry
            await asyncio.sleep(0.3)
            await svc.stop()

        # Should have attempted at least 3 connections (2 failures + 1 success)
        assert connect_attempts >= 3


class TestMaxRetriesExceeded:
    """Verify the service gives up after max retries."""

    async def test_stops_after_max_retries(self) -> None:
        svc = PgListenNotifyPolicySyncService(
            max_retries=2, backoff_seconds=0.01
        )

        async def always_fail(*args: object, **kwargs: object) -> MagicMock:
            raise ConnectionError("permanent failure")

        with patch("asyncpg.connect", side_effect=always_fail):
            await svc.start()
            # Wait for retries to exhaust
            await asyncio.sleep(0.5)

        # Service should have stopped itself after max retries
        assert svc.running is False


class TestSafeCallbackHandlesErrors:
    """Verify callback errors don't crash the service."""

    async def test_error_in_callback_is_caught(self) -> None:
        async def bad_callback(payload: str) -> None:
            raise ValueError("boom")

        # _safe_callback should log but not propagate
        await PgListenNotifyPolicySyncService._safe_callback(bad_callback, "test")
        # If we get here, the exception was caught

    async def test_one_bad_callback_doesnt_block_others(self) -> None:
        svc = PgListenNotifyPolicySyncService(max_retries=0, backoff_seconds=0.0)
        results: list[str] = []

        async def bad_cb(payload: str) -> None:
            raise RuntimeError("fail")

        async def good_cb(payload: str) -> None:
            results.append(payload)

        svc.on_policy_change(bad_cb)
        svc.on_policy_change(good_cb)

        mock_conn = _make_mock_connection()
        captured_handler: list = []

        async def capture_add_listener(channel: str, handler: object) -> None:
            captured_handler.append(handler)

        mock_conn.add_listener = capture_add_listener  # type: ignore[assignment]

        call_count = 0

        def is_closed_side_effect() -> bool:
            nonlocal call_count
            call_count += 1
            return call_count > 2

        mock_conn.is_closed = is_closed_side_effect

        with patch("asyncpg.connect", AsyncMock(return_value=mock_conn)):
            await svc.start()
            await asyncio.sleep(0.1)

            assert len(captured_handler) == 1
            captured_handler[0](mock_conn, 1, CHANNEL, "p1")
            await asyncio.sleep(0.1)

            assert results == ["p1"]
            await svc.stop()


class TestSingleton:
    """Verify the factory returns the same instance."""

    def test_get_returns_same_instance(self) -> None:
        reset_policy_sync_service()
        svc1 = get_policy_sync_service()
        svc2 = get_policy_sync_service()
        assert svc1 is svc2
        reset_policy_sync_service()

    def test_reset_clears_singleton(self) -> None:
        reset_policy_sync_service()
        svc1 = get_policy_sync_service()
        reset_policy_sync_service()
        svc2 = get_policy_sync_service()
        assert svc1 is not svc2
        reset_policy_sync_service()

    def test_returns_pg_listen_notify_type(self) -> None:
        reset_policy_sync_service()
        svc = get_policy_sync_service()
        assert isinstance(svc, PgListenNotifyPolicySyncService)
        reset_policy_sync_service()

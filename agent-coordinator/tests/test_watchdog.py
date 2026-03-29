"""Tests for WatchdogService."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.watchdog import WatchdogService, reset_watchdog


class FakeTime:
    """Controllable time source for tests."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def _make_mock_db() -> AsyncMock:
    db = AsyncMock()
    db.query = AsyncMock(return_value=[])
    db.rpc = AsyncMock(return_value={"success": True, "agents_cleaned": 0, "locks_released": 0})
    db.update = AsyncMock(return_value=[])
    db.delete = AsyncMock(return_value=None)
    return db


def _make_service(db: AsyncMock | None = None, time_fn=None) -> WatchdogService:
    return WatchdogService(
        db=db or _make_mock_db(),
        check_interval=60,
        time_fn=time_fn,
    )


class TestWatchdogInitialState:
    def test_watchdog_initial_state(self):
        db = _make_mock_db()
        svc = WatchdogService(db=db, check_interval=120)
        assert svc.running is False
        assert svc._task is None
        assert svc._interval == 120
        assert svc._last_reminders == {}


class TestRunOnceCallsAllChecks:
    @patch("src.watchdog.get_event_bus")
    async def test_run_once_calls_all_checks(self, mock_get_bus):
        mock_bus = MagicMock()
        mock_bus.failed = False
        mock_get_bus.return_value = mock_bus

        db = _make_mock_db()
        svc = _make_service(db=db)

        await svc.run_once()

        # Should have queried agent_discovery, approval_queue, file_locks, notification_tokens
        tables_queried = [call.args[0] for call in db.query.call_args_list]
        assert "agent_discovery" in tables_queried
        assert "approval_queue" in tables_queried
        assert "file_locks" in tables_queried
        assert "notification_tokens" in tables_queried


class TestStaleAgentDetection:
    @patch("src.watchdog.get_event_bus")
    async def test_stale_agent_detection(self, mock_get_bus):
        mock_bus = MagicMock()
        mock_bus.failed = False
        mock_get_bus.return_value = mock_bus

        db = _make_mock_db()
        stale_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        db.query = AsyncMock(side_effect=lambda table, *args, **kwargs: {
            "agent_discovery": [
                {"agent_id": "stale-agent-1", "status": "active", "last_heartbeat": stale_time}
            ],
            "approval_queue": [],
            "file_locks": [],
            "notification_tokens": [],
        }.get(table, []))

        svc = _make_service(db=db)
        await svc.run_once()

        # Should have called rpc for cleanup_dead_agents
        rpc_calls = [call.args[0] for call in db.rpc.call_args_list]
        assert "cleanup_dead_agents" in rpc_calls

        # Should have called rpc for pg_notify_direct (the stale agent event)
        assert "pg_notify_direct" in rpc_calls


class TestAgingApprovalReminder:
    @patch("src.watchdog.get_event_bus")
    async def test_aging_approval_reminder(self, mock_get_bus):
        mock_bus = MagicMock()
        mock_bus.failed = False
        mock_get_bus.return_value = mock_bus

        db = _make_mock_db()
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        db.query = AsyncMock(side_effect=lambda table, *args, **kwargs: {
            "agent_discovery": [],
            "approval_queue": [
                {
                    "id": "approval-1",
                    "agent_id": "agent-1",
                    "operation": "deploy",
                    "status": "pending",
                    "created_at": old_time,
                }
            ],
            "file_locks": [],
            "notification_tokens": [],
        }.get(table, []))

        fake_time = FakeTime(start=5000.0)  # Must exceed debounce window (1800s)
        svc = _make_service(db=db, time_fn=fake_time)
        await svc.run_once()

        # Should have emitted a reminder via pg_notify_direct
        rpc_calls = [call.args[0] for call in db.rpc.call_args_list]
        assert "pg_notify_direct" in rpc_calls

        # Check the event payload
        notify_call = [c for c in db.rpc.call_args_list if c.args[0] == "pg_notify_direct"][0]
        assert "approval.reminder" in notify_call.args[1]["p_payload"]


class TestApprovalReminderDebounce:
    @patch("src.watchdog.get_event_bus")
    async def test_approval_reminder_debounce(self, mock_get_bus):
        mock_bus = MagicMock()
        mock_bus.failed = False
        mock_get_bus.return_value = mock_bus

        db = _make_mock_db()
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        db.query = AsyncMock(side_effect=lambda table, *args, **kwargs: {
            "agent_discovery": [],
            "approval_queue": [
                {
                    "id": "approval-debounce",
                    "agent_id": "agent-1",
                    "operation": "deploy",
                    "status": "pending",
                    "created_at": old_time,
                }
            ],
            "file_locks": [],
            "notification_tokens": [],
        }.get(table, []))

        fake_time = FakeTime(start=5000.0)  # Must exceed debounce window (1800s)
        svc = _make_service(db=db, time_fn=fake_time)

        # First run: should emit reminder
        await svc.run_once()
        first_rpc_count = len([c for c in db.rpc.call_args_list if c.args[0] == "pg_notify_direct"])
        assert first_rpc_count >= 1

        # Reset mock call tracking
        db.rpc.reset_mock()

        # Second run: within 30 min debounce window, should NOT emit reminder
        fake_time.advance(60)  # only 1 minute later
        await svc.run_once()
        second_notify_calls = [c for c in db.rpc.call_args_list if c.args[0] == "pg_notify_direct"]
        # No approval reminder should have been emitted
        approval_reminders = [
            c for c in second_notify_calls
            if "approval.reminder" in c.args[1].get("p_payload", "")
        ]
        assert len(approval_reminders) == 0


class TestExpiringLockWarning:
    @patch("src.watchdog.get_event_bus")
    async def test_expiring_lock_warning(self, mock_get_bus):
        mock_bus = MagicMock()
        mock_bus.failed = False
        mock_get_bus.return_value = mock_bus

        db = _make_mock_db()
        soon = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        db.query = AsyncMock(side_effect=lambda table, *args, **kwargs: {
            "agent_discovery": [],
            "approval_queue": [],
            "file_locks": [
                {
                    "file_path": "src/main.py",
                    "locked_by": "agent-2",
                    "expires_at": soon,
                }
            ],
            "notification_tokens": [],
        }.get(table, []))

        svc = _make_service(db=db)
        await svc.run_once()

        # Should have emitted a lock_expiring event
        notify_calls = [c for c in db.rpc.call_args_list if c.args[0] == "pg_notify_direct"]
        lock_warnings = [
            c for c in notify_calls
            if "agent.lock_expiring" in c.args[1].get("p_payload", "")
        ]
        assert len(lock_warnings) == 1


class TestExpiredTokenCleanup:
    @patch("src.watchdog.get_event_bus")
    async def test_expired_token_cleanup(self, mock_get_bus):
        mock_bus = MagicMock()
        mock_bus.failed = False
        mock_get_bus.return_value = mock_bus

        db = _make_mock_db()
        expired_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        db.query = AsyncMock(side_effect=lambda table, *args, **kwargs: {
            "agent_discovery": [],
            "approval_queue": [],
            "file_locks": [],
            "notification_tokens": [
                {"id": "token-1", "expires_at": expired_time},
                {"id": "token-2", "expires_at": expired_time},
            ],
        }.get(table, []))

        svc = _make_service(db=db)
        await svc.run_once()

        # Should have deleted both expired tokens
        assert db.delete.call_count == 2
        deleted_tables = [call.args[0] for call in db.delete.call_args_list]
        assert all(t == "notification_tokens" for t in deleted_tables)


class TestEventBusHealthCheck:
    @patch("src.watchdog.get_event_bus")
    async def test_event_bus_health_check_on_failure(self, mock_get_bus):
        mock_bus = MagicMock()
        mock_bus.failed = True
        mock_bus.restart = AsyncMock()
        mock_get_bus.return_value = mock_bus

        db = _make_mock_db()
        svc = _make_service(db=db)
        await svc.run_once()

        # Should have attempted to restart the bus
        mock_bus.restart.assert_called_once()

        # Should have emitted a bus.connection_failed event
        notify_calls = [c for c in db.rpc.call_args_list if c.args[0] == "pg_notify_direct"]
        bus_events = [
            c for c in notify_calls
            if "bus.connection_failed" in c.args[1].get("p_payload", "")
        ]
        assert len(bus_events) == 1

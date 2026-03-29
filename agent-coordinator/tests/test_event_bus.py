"""Tests for the EventBusService and CoordinatorEvent."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.event_bus import (
    CHANNELS,
    CoordinatorEvent,
    EventBusService,
    classify_urgency,
    get_event_bus,
    reset_event_bus,
)


# --- CoordinatorEvent tests ---


class TestCoordinatorEvent:
    def test_creates_with_defaults(self) -> None:
        event = CoordinatorEvent(
            event_type="approval.submitted",
            channel="coordinator_approval",
            entity_id="abc-123",
            agent_id="claude-1",
            urgency="high",
            summary="Test event",
        )
        assert event.event_type == "approval.submitted"
        assert event.timestamp  # auto-generated
        assert event.context == {}
        assert event.change_id is None

    def test_truncates_long_summary(self) -> None:
        event = CoordinatorEvent(
            event_type="test",
            channel="test",
            entity_id="id",
            agent_id="a",
            urgency="low",
            summary="x" * 300,
        )
        assert len(event.summary) <= 200

    def test_to_json_round_trip(self) -> None:
        event = CoordinatorEvent(
            event_type="task.completed",
            channel="coordinator_task",
            entity_id="task-1",
            agent_id="codex-1",
            urgency="medium",
            summary="Task done",
            change_id="my-feature",
            context={"files": ["src/main.py"]},
        )
        raw = event.to_json()
        restored = CoordinatorEvent.from_json(raw)
        assert restored.event_type == event.event_type
        assert restored.entity_id == event.entity_id
        assert restored.change_id == "my-feature"
        assert restored.context == {"files": ["src/main.py"]}

    def test_to_json_truncates_large_context(self) -> None:
        big_context = {"data": "x" * 10_000}
        event = CoordinatorEvent(
            event_type="test",
            channel="test",
            entity_id="id",
            agent_id="a",
            urgency="low",
            summary="Big event",
            context=big_context,
        )
        raw = event.to_json()
        assert len(raw.encode()) <= 7 * 1024
        parsed = json.loads(raw)
        assert parsed["context"].get("_truncated") is True

    def test_from_json_ignores_unknown_fields(self) -> None:
        raw = json.dumps({
            "event_type": "test",
            "channel": "ch",
            "entity_id": "id",
            "agent_id": "a",
            "urgency": "low",
            "summary": "s",
            "unknown_field": 42,
        })
        event = CoordinatorEvent.from_json(raw)
        assert event.event_type == "test"


# --- Urgency classification ---


class TestClassifyUrgency:
    def test_high_urgency_events(self) -> None:
        assert classify_urgency("approval.submitted") == "high"
        assert classify_urgency("agent.stale") == "high"
        assert classify_urgency("status.escalated") == "high"

    def test_medium_urgency_events(self) -> None:
        assert classify_urgency("task.completed") == "medium"
        assert classify_urgency("task.failed") == "medium"
        assert classify_urgency("approval.decided") == "medium"

    def test_low_urgency_default(self) -> None:
        assert classify_urgency("agent.registered") == "low"
        assert classify_urgency("unknown.event") == "low"


# --- EventBusService tests ---


class TestEventBusService:
    def test_initial_state(self) -> None:
        bus = EventBusService(dsn="postgresql://test")
        assert not bus.running
        assert not bus.failed

    def test_on_event_registers_channel_callback(self) -> None:
        bus = EventBusService(dsn="postgresql://test")
        cb = AsyncMock()
        bus.on_event("coordinator_approval", cb)
        assert cb in bus._callbacks["coordinator_approval"]

    def test_on_event_registers_global_callback(self) -> None:
        bus = EventBusService(dsn="postgresql://test")
        cb = AsyncMock()
        bus.on_event(None, cb)
        assert cb in bus._global_callbacks

    @pytest.mark.asyncio
    async def test_dispatch_calls_channel_callbacks(self) -> None:
        bus = EventBusService(dsn="postgresql://test")
        cb = AsyncMock()
        bus.on_event("coordinator_approval", cb)

        event = CoordinatorEvent(
            event_type="approval.submitted",
            channel="coordinator_approval",
            entity_id="req-1",
            agent_id="claude-1",
            urgency="high",
            summary="Test",
        )
        await bus._dispatch("coordinator_approval", event.to_json())
        await asyncio.sleep(0.05)  # let the task run
        cb.assert_called_once()
        dispatched = cb.call_args[0][0]
        assert dispatched.event_type == "approval.submitted"

    @pytest.mark.asyncio
    async def test_dispatch_calls_global_callbacks(self) -> None:
        bus = EventBusService(dsn="postgresql://test")
        global_cb = AsyncMock()
        bus.on_event(None, global_cb)

        event = CoordinatorEvent(
            event_type="task.completed",
            channel="coordinator_task",
            entity_id="t-1",
            agent_id="a",
            urgency="medium",
            summary="Done",
        )
        await bus._dispatch("coordinator_task", event.to_json())
        await asyncio.sleep(0.05)
        global_cb.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_handles_invalid_json(self) -> None:
        bus = EventBusService(dsn="postgresql://test")
        cb = AsyncMock()
        bus.on_event("coordinator_task", cb)
        await bus._dispatch("coordinator_task", "not-json")
        await asyncio.sleep(0.05)
        cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_callback_error_does_not_propagate(self) -> None:
        bus = EventBusService(dsn="postgresql://test")
        bad_cb = AsyncMock(side_effect=ValueError("boom"))
        good_cb = AsyncMock()
        bus.on_event("coordinator_approval", bad_cb)
        bus.on_event("coordinator_approval", good_cb)

        event = CoordinatorEvent(
            event_type="approval.submitted",
            channel="coordinator_approval",
            entity_id="r-1",
            agent_id="a",
            urgency="high",
            summary="Test",
        )
        await bus._dispatch("coordinator_approval", event.to_json())
        await asyncio.sleep(0.05)
        bad_cb.assert_called_once()
        good_cb.assert_called_once()

    @pytest.mark.asyncio
    async def test_listen_loop_retries_and_fails(self) -> None:
        bus = EventBusService(
            dsn="postgresql://test",
            max_retries=2,
            backoff_seconds=0.01,
        )
        bus._running = True

        with patch.object(
            bus, "_connect_and_listen", side_effect=ConnectionError("fail")
        ):
            await bus._listen_loop()

        assert bus.failed
        assert not bus.running

    @pytest.mark.asyncio
    async def test_listen_loop_resets_retries_on_success(self) -> None:
        bus = EventBusService(
            dsn="postgresql://test",
            max_retries=3,
            backoff_seconds=0.01,
        )
        call_count = 0

        async def connect_and_listen() -> None:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ConnectionError("transient")
            bus._running = False  # stop after success

        bus._running = True
        with patch.object(bus, "_connect_and_listen", side_effect=connect_and_listen):
            await bus._listen_loop()

        assert not bus.failed
        assert call_count == 3


# --- Singleton ---


class TestSingleton:
    def test_get_event_bus_returns_same_instance(self) -> None:
        reset_event_bus()
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2
        reset_event_bus()

    def test_reset_clears_singleton(self) -> None:
        reset_event_bus()
        bus1 = get_event_bus()
        reset_event_bus()
        bus2 = get_event_bus()
        assert bus1 is not bus2
        reset_event_bus()

"""Tests for NotifierService."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.event_bus import CoordinatorEvent
from src.notifications.base import GmailChannelFake, NotificationChannel
from src.notifications.notifier import NotifierService, reset_notifier


def _make_event(
    event_type: str = "task.completed",
    urgency: str = "high",
    change_id: str | None = "test-change",
) -> CoordinatorEvent:
    return CoordinatorEvent(
        event_type=event_type,
        channel="coordinator_task",
        entity_id="entity-1",
        agent_id="agent-1",
        urgency=urgency,
        summary="Test event",
        change_id=change_id,
    )


@pytest.fixture(autouse=True)
def _reset():
    yield
    reset_notifier()


class TestNotifierService:
    def test_register_channel(self):
        svc = NotifierService()
        fake = GmailChannelFake()
        svc.register_channel("gmail_fake", fake)
        assert svc.enabled is True
        assert "gmail_fake" in svc._channels

    async def test_send_dispatches_to_all_channels(self):
        fake1 = GmailChannelFake()
        fake2 = GmailChannelFake()
        fake2.channel_id = "gmail_fake_2"
        svc = NotifierService(channels={"c1": fake1, "c2": fake2})

        event = _make_event()
        results = await svc.send(event)

        assert results == {"c1": True, "c2": True}
        assert len(fake1.sent_events) == 1
        assert len(fake2.sent_events) == 1
        assert fake1.sent_events[0] is event

    async def test_send_returns_per_channel_results(self):
        fake_ok = GmailChannelFake()

        class FailChannel:
            channel_id = "fail"
            async def send(self, event: CoordinatorEvent) -> bool:
                raise RuntimeError("boom")
            async def test(self) -> bool:
                return False
            def supports_reply(self) -> bool:
                return False

        svc = NotifierService(channels={"ok": fake_ok, "fail": FailChannel()})
        event = _make_event()
        results = await svc.send(event)

        assert results["ok"] is True
        assert results["fail"] is False

    async def test_failed_channel_does_not_block_others(self):
        fake_ok = GmailChannelFake()

        class SlowFailChannel:
            channel_id = "slow_fail"
            async def send(self, event: CoordinatorEvent) -> bool:
                raise ConnectionError("timeout")
            async def test(self) -> bool:
                return False
            def supports_reply(self) -> bool:
                return False

        svc = NotifierService(channels={"ok": fake_ok, "slow": SlowFailChannel()})
        event = _make_event()
        results = await svc.send(event)

        assert results["ok"] is True
        assert results["slow"] is False
        assert len(fake_ok.sent_events) == 1

    async def test_event_filter_drops_unmatched_events(self, monkeypatch):
        monkeypatch.setenv("NOTIFICATION_EVENT_FILTER_FILTERED", "approval.submitted,task.failed")

        fake = GmailChannelFake()
        fake.channel_id = "filtered"
        svc = NotifierService(channels={"filtered": fake})

        # This event type is not in the filter
        event = _make_event(event_type="task.completed")
        results = await svc.send(event)

        assert "filtered" not in results
        assert len(fake.sent_events) == 0

    async def test_event_filter_allows_matched_events(self, monkeypatch):
        monkeypatch.setenv("NOTIFICATION_EVENT_FILTER_ALLOWED", "task.completed")

        fake = GmailChannelFake()
        fake.channel_id = "allowed"
        svc = NotifierService(channels={"allowed": fake})

        event = _make_event(event_type="task.completed")
        results = await svc.send(event)

        assert results["allowed"] is True
        assert len(fake.sent_events) == 1

    def test_disabled_when_no_channels(self):
        svc = NotifierService()
        assert svc.enabled is False

    async def test_send_empty_when_no_channels(self):
        svc = NotifierService()
        results = await svc.send(_make_event())
        assert results == {}

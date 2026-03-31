"""Base notification channel protocol and test doubles."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.event_bus import CoordinatorEvent


@runtime_checkable
class NotificationChannel(Protocol):
    """Protocol that all notification channels must implement."""

    channel_id: str

    async def send(self, event: CoordinatorEvent) -> bool:
        """Send an event notification. Returns True on success."""
        ...

    async def test(self) -> bool:
        """Test connectivity. Returns True if channel is reachable."""
        ...

    def supports_reply(self) -> bool:
        """Whether this channel supports reply-based interactions."""
        ...


class GmailChannelFake:
    """In-memory test double implementing NotificationChannel."""

    channel_id: str = "gmail_fake"

    def __init__(self) -> None:
        self.sent_events: list[CoordinatorEvent] = []

    async def send(self, event: CoordinatorEvent) -> bool:
        self.sent_events.append(event)
        return True

    async def test(self) -> bool:
        return True

    def supports_reply(self) -> bool:
        return True

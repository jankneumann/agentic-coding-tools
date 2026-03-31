"""NotifierService: dispatch events to registered notification channels."""

from __future__ import annotations

import asyncio
import logging
import os

from src.event_bus import CoordinatorEvent

from .base import NotificationChannel

logger = logging.getLogger(__name__)

# Retry configuration
_RETRY_BASE_SECONDS = 2.0
_RETRY_MAX_SECONDS = 60.0
_RETRY_MAX_ATTEMPTS = 3

# Default medium-urgency delay (seconds)
_MEDIUM_DELAY_SECONDS = float(os.environ.get("NOTIFICATION_MEDIUM_DELAY", "30"))

# Low-urgency events are batched; callers should use digest rendering externally.
# Here we simply delay them like medium but with a longer default.
_LOW_DELAY_SECONDS = float(os.environ.get("NOTIFICATION_LOW_DELAY", "300"))


class NotifierService:
    """Dispatch CoordinatorEvents to all registered notification channels."""

    def __init__(self, channels: dict[str, NotificationChannel] | None = None) -> None:
        self._channels: dict[str, NotificationChannel] = dict(channels) if channels else {}

    def register_channel(self, channel_id: str, channel: NotificationChannel) -> None:
        """Register a notification channel."""
        self._channels[channel_id] = channel

    @property
    def enabled(self) -> bool:
        """True if at least one channel is registered."""
        return len(self._channels) > 0

    async def send(self, event: CoordinatorEvent) -> dict[str, bool]:
        """Dispatch event to all channels in parallel.

        Applies per-channel event filters, urgency-based delays, and retry
        with exponential backoff on failure.

        Returns:
            Mapping of channel_id -> success boolean.
        """
        if not self._channels:
            return {}

        # Build filtered channel list first (before any delay)
        filtered: dict[str, NotificationChannel] = {}
        for channel_id, channel in self._channels.items():
            if _passes_filter(channel_id, event):
                filtered[channel_id] = channel

        if not filtered:
            return {}

        # Apply urgency delay (high = immediate)
        if event.urgency == "medium":
            await asyncio.sleep(_MEDIUM_DELAY_SECONDS)
        elif event.urgency == "low":
            await asyncio.sleep(_LOW_DELAY_SECONDS)

        tasks: dict[str, asyncio.Task[bool]] = {}
        for channel_id, channel in filtered.items():
            tasks[channel_id] = asyncio.create_task(
                self._send_with_retry(channel, event)
            )

        results: dict[str, bool] = {}
        if tasks:
            done = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for cid, result in zip(tasks.keys(), done):
                if isinstance(result, BaseException):
                    logger.warning(
                        "Channel %s raised during send: %s", cid, result
                    )
                    results[cid] = False
                else:
                    results[cid] = result
        return results

    @staticmethod
    async def _send_with_retry(channel: NotificationChannel, event: CoordinatorEvent) -> bool:
        """Try sending with exponential backoff."""
        last_exc: BaseException | None = None
        for attempt in range(_RETRY_MAX_ATTEMPTS):
            try:
                result = await channel.send(event)
                if result:
                    return True
                # send returned False — treat as failure, retry
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Channel %s attempt %d failed: %s",
                    channel.channel_id,
                    attempt + 1,
                    exc,
                )
            if attempt < _RETRY_MAX_ATTEMPTS - 1:
                delay = min(
                    _RETRY_BASE_SECONDS * (2 ** attempt),
                    _RETRY_MAX_SECONDS,
                )
                await asyncio.sleep(delay)

        if last_exc:
            logger.warning(
                "Channel %s exhausted retries: %s",
                channel.channel_id,
                last_exc,
            )
        else:
            logger.warning(
                "Channel %s exhausted retries: send returned False on all %d attempts",
                channel.channel_id,
                _RETRY_MAX_ATTEMPTS,
            )
        return False


def _passes_filter(channel_id: str, event: CoordinatorEvent) -> bool:
    """Check NOTIFICATION_EVENT_FILTER_{CHANNEL_ID} env var."""
    env_key = f"NOTIFICATION_EVENT_FILTER_{channel_id.upper()}"
    filter_val = os.environ.get(env_key)
    if filter_val is None:
        return True
    allowed = {t.strip() for t in filter_val.split(",") if t.strip()}
    return event.event_type in allowed


# --- Singleton ---

_notifier: NotifierService | None = None


def get_notifier() -> NotifierService:
    """Return the singleton NotifierService."""
    global _notifier
    if _notifier is None:
        _notifier = NotifierService()
    return _notifier


def reset_notifier() -> None:
    """Reset the singleton (for tests)."""
    global _notifier
    _notifier = None

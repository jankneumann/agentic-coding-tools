"""Generalized event bus via PostgreSQL LISTEN/NOTIFY.

Extends the single-channel pattern from policy_sync.py into a multi-channel
event bus. Database triggers on approval_queue, work_queue, and agent_discovery
emit NOTIFY events that the bus dispatches to registered callbacks.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

logger = logging.getLogger(__name__)

# NOTIFY channels with their trigger sources
CHANNELS = (
    "coordinator_approval",
    "coordinator_task",
    "coordinator_agent",
    "coordinator_status",
)

# Max NOTIFY payload ~8KB; we leave 1KB margin
_MAX_PAYLOAD_BYTES = 7 * 1024


@dataclass
class CoordinatorEvent:
    """Canonical event flowing through the event bus and notifier."""

    event_type: str
    channel: str
    entity_id: str
    agent_id: str
    urgency: Literal["low", "medium", "high"]
    summary: str
    timestamp: str = ""
    change_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        # Enforce summary length
        if len(self.summary) > 200:
            self.summary = self.summary[:197] + "..."

    def to_json(self) -> str:
        """Serialize to JSON, truncating context if payload exceeds limit."""
        data = asdict(self)
        payload = json.dumps(data)
        if len(payload.encode()) <= _MAX_PAYLOAD_BYTES:
            return payload
        # Truncate context to fit
        data["context"] = {"_truncated": True, "summary": self.summary}
        payload = json.dumps(data)
        if len(payload.encode()) > _MAX_PAYLOAD_BYTES:
            data["context"] = {}
        return json.dumps(data)

    @classmethod
    def from_json(cls, raw: str) -> CoordinatorEvent:
        """Deserialize from a NOTIFY payload."""
        data = json.loads(raw)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# --- Urgency classification ---

_HIGH_EVENTS = frozenset({
    "approval.submitted",
    "status.escalated",
    "agent.stale",
    "bus.connection_failed",
})

_MEDIUM_EVENTS = frozenset({
    "task.completed",
    "task.failed",
    "approval.decided",
    "approval.reminder",
    "status.phase_transition",
    "agent.lock_expiring",
})


def classify_urgency(event_type: str) -> Literal["low", "medium", "high"]:
    """Classify event urgency based on type."""
    if event_type in _HIGH_EVENTS:
        return "high"
    if event_type in _MEDIUM_EVENTS:
        return "medium"
    return "low"


# --- Event Bus Service ---

EventCallback = Callable[[CoordinatorEvent], Awaitable[None]]


class EventBusService:
    """Multi-channel event bus built on PostgreSQL LISTEN/NOTIFY.

    Generalizes the PgListenNotifyPolicySyncService pattern from policy_sync.py
    to listen on multiple channels and dispatch CoordinatorEvent objects.
    """

    def __init__(
        self,
        dsn: str | None = None,
        channels: tuple[str, ...] = CHANNELS,
        max_retries: int = 5,
        backoff_seconds: float = 1.0,
    ) -> None:
        self._dsn = dsn or os.environ.get(
            "POSTGRES_DSN",
            "postgresql://postgres:postgres@localhost:54322/postgres",
        )
        self._channels = channels
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._callbacks: dict[str, list[EventCallback]] = {ch: [] for ch in channels}
        self._global_callbacks: list[EventCallback] = []
        self._connection: Any = None  # asyncpg.Connection
        self._listen_task: asyncio.Task[None] | None = None
        self._running = False
        self._failed = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def failed(self) -> bool:
        """True if all reconnection attempts were exhausted."""
        return self._failed

    def on_event(
        self, channel: str | None, callback: EventCallback
    ) -> None:
        """Register a callback. If channel is None, receives all events."""
        if channel is None:
            self._global_callbacks.append(callback)
        else:
            if channel not in self._callbacks:
                self._callbacks[channel] = []
            self._callbacks[channel].append(callback)

    async def start(self) -> None:
        """Start listening on all configured channels."""
        if self._running:
            return
        self._running = True
        self._failed = False
        self._listen_task = asyncio.create_task(self._listen_loop())
        logger.info(
            "EventBus: started LISTEN on %d channels: %s",
            len(self._channels),
            ", ".join(self._channels),
        )

    async def stop(self) -> None:
        """Stop listening and close the dedicated connection."""
        self._running = False
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        if self._connection and not self._connection.is_closed():
            await self._connection.close()
            self._connection = None
        logger.info("EventBus: stopped")

    async def restart(self) -> None:
        """Restart the event bus (e.g., after watchdog detects failure)."""
        await self.stop()
        await self.start()

    async def _listen_loop(self) -> None:
        """Main listen loop with reconnection and backoff."""
        retries = 0
        while self._running:
            try:
                await self._connect_and_listen()
                retries = 0
            except asyncio.CancelledError:
                break
            except Exception as exc:
                retries += 1
                if retries > self._max_retries:
                    logger.critical(
                        "EventBus: max retries (%d) exceeded, bus FAILED",
                        self._max_retries,
                    )
                    self._failed = True
                    self._running = False
                    break
                wait = self._backoff_seconds * (2 ** (retries - 1))
                logger.warning(
                    "EventBus: connection lost (%s), retry %d/%d in %.1fs",
                    exc,
                    retries,
                    self._max_retries,
                    wait,
                )
                await asyncio.sleep(wait)

    async def _connect_and_listen(self) -> None:
        """Establish connection and listen on all channels."""
        import asyncpg

        self._connection = await asyncpg.connect(self._dsn)

        def _notification_handler(
            _conn: Any, _pid: int, channel: str, payload: str
        ) -> None:
            asyncio.create_task(self._dispatch(channel, payload))

        for ch in self._channels:
            await self._connection.add_listener(ch, _notification_handler)

        logger.info(
            "EventBus: connected and listening on %d channels",
            len(self._channels),
        )

        try:
            while self._running and not self._connection.is_closed():
                await asyncio.sleep(1.0)
        finally:
            if self._connection and not self._connection.is_closed():
                for ch in self._channels:
                    await self._connection.remove_listener(ch, _notification_handler)
                await self._connection.close()
            self._connection = None

    async def _dispatch(self, channel: str, payload: str) -> None:
        """Parse event and dispatch to registered callbacks."""
        try:
            event = CoordinatorEvent.from_json(payload)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.error("EventBus: invalid payload on '%s': %s", channel, exc)
            return

        callbacks = list(self._global_callbacks)
        if channel in self._callbacks:
            callbacks.extend(self._callbacks[channel])

        for cb in callbacks:
            asyncio.create_task(self._safe_callback(cb, event))

    @staticmethod
    async def _safe_callback(callback: EventCallback, event: CoordinatorEvent) -> None:
        try:
            await callback(event)
        except Exception as exc:
            logger.error(
                "EventBus: callback error for '%s': %s", event.event_type, exc
            )


# --- Singleton ---

_event_bus: EventBusService | None = None


def get_event_bus() -> EventBusService:
    """Return the singleton EventBusService."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBusService()
    return _event_bus


def reset_event_bus() -> None:
    """Reset the singleton (for tests)."""
    global _event_bus
    _event_bus = None

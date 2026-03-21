"""Push-based policy cache invalidation via PostgreSQL LISTEN/NOTIFY."""

from __future__ import annotations

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

CHANNEL = "policy_changed"


class PolicySyncService(ABC):
    """Abstract base for policy synchronization backends."""

    @abstractmethod
    async def start(self) -> None:
        """Start listening for policy changes."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop listening and release resources."""

    @abstractmethod
    def on_policy_change(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Register a callback for policy change notifications.

        Args:
            callback: Async function called with the policy name that changed.
        """


class PgListenNotifyPolicySyncService(PolicySyncService):
    """Policy sync via PostgreSQL LISTEN/NOTIFY using asyncpg.

    Acquires a dedicated connection and listens on the 'policy_changed'
    channel. On notification, invokes registered callbacks. Falls back
    gracefully when connection is lost.
    """

    def __init__(
        self,
        dsn: str | None = None,
        max_retries: int = 5,
        backoff_seconds: float = 1.0,
    ) -> None:
        self._dsn = dsn or os.environ.get(
            "POSTGRES_DSN",
            "postgresql://postgres:postgres@localhost:54322/postgres",
        )
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._callbacks: list[Callable[[str], Awaitable[None]]] = []
        self._connection: Any = None  # asyncpg.Connection
        self._listen_task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def running(self) -> bool:
        """Whether the service is currently running."""
        return self._running

    def on_policy_change(self, callback: Callable[[str], Awaitable[None]]) -> None:
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Start listening for policy change notifications."""
        if self._running:
            return
        self._running = True
        self._listen_task = asyncio.create_task(self._listen_loop())
        logger.info("PolicySync: started LISTEN on channel '%s'", CHANNEL)

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
        logger.info("PolicySync: stopped")

    async def _listen_loop(self) -> None:
        """Main listen loop with reconnection and backoff."""
        retries = 0
        while self._running:
            try:
                await self._connect_and_listen()
                retries = 0  # reset on successful connection
            except asyncio.CancelledError:
                break
            except Exception as exc:
                retries += 1
                if retries > self._max_retries:
                    logger.error(
                        "PolicySync: max retries (%d) exceeded, falling back to TTL",
                        self._max_retries,
                    )
                    self._running = False
                    break
                wait = self._backoff_seconds * (2 ** (retries - 1))
                logger.warning(
                    "PolicySync: connection lost (%s), retry %d/%d in %.1fs",
                    exc,
                    retries,
                    self._max_retries,
                    wait,
                )
                await asyncio.sleep(wait)

    async def _connect_and_listen(self) -> None:
        """Establish connection and listen for notifications."""
        import asyncpg

        self._connection = await asyncpg.connect(self._dsn)

        def _notification_handler(
            _conn: Any, _pid: int, _channel: str, payload: str
        ) -> None:
            for cb in self._callbacks:
                asyncio.create_task(self._safe_callback(cb, payload))

        await self._connection.add_listener(CHANNEL, _notification_handler)
        logger.info("PolicySync: connected and listening on '%s'", CHANNEL)

        # Keep connection alive — asyncpg notifications are delivered
        # via the connection's internal event loop processing.
        # We just need to keep the connection open.
        try:
            while self._running and not self._connection.is_closed():
                await asyncio.sleep(1.0)
        finally:
            if self._connection and not self._connection.is_closed():
                await self._connection.remove_listener(CHANNEL, _notification_handler)
                await self._connection.close()
            self._connection = None

    @staticmethod
    async def _safe_callback(
        callback: Callable[[str], Awaitable[None]], payload: str
    ) -> None:
        try:
            await callback(payload)
        except Exception as exc:
            logger.error("PolicySync: callback error for '%s': %s", payload, exc)


# Factory -------------------------------------------------------------------

_policy_sync: PolicySyncService | None = None


def get_policy_sync_service() -> PgListenNotifyPolicySyncService:
    """Return the singleton PolicySyncService instance."""
    global _policy_sync
    if _policy_sync is None:
        _policy_sync = PgListenNotifyPolicySyncService()
    return _policy_sync  # type: ignore[return-value]


def reset_policy_sync_service() -> None:
    """Reset the singleton (useful for tests)."""
    global _policy_sync
    _policy_sync = None

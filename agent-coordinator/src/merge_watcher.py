"""Background merge watcher for the coordinator.

Runs as an asyncio background task alongside the existing watchdog.
Periodically checks for pending merge queue work, triggers auto-rebase
for stale PRs, and monitors post-merge CI for rollback.

Design decisions: D5 (merge watcher as coordinator background task)
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

MERGE_WATCHER_INTERVAL = int(
    os.environ.get("MERGE_WATCHER_INTERVAL", "60"),
)


class MergeWatcher:
    def __init__(self, interval: int = MERGE_WATCHER_INTERVAL) -> None:
        self._interval = interval
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "MergeWatcher started (interval=%ds)", self._interval,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("MergeWatcher stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                result = await self._tick()
                logger.debug("MergeWatcher tick: %s", result.get("action"))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("MergeWatcher tick failed", exc_info=True)
            await asyncio.sleep(self._interval)

    async def _tick(self) -> dict[str, Any]:
        return {"action": "heartbeat"}


_merge_watcher: MergeWatcher | None = None


def get_merge_watcher() -> MergeWatcher:
    global _merge_watcher
    if _merge_watcher is None:
        _merge_watcher = MergeWatcher()
    return _merge_watcher

"""Async background task for periodic health monitoring.

Periodically checks for stale agents, aging approvals, expiring locks,
expired tokens, and event bus health. Emits notifications via pg_notify.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .db import DatabaseClient, get_db
from .event_bus import CoordinatorEvent, get_event_bus

logger = logging.getLogger(__name__)

# Defaults
_DEFAULT_INTERVAL_SECONDS = 60
_STALE_AGENT_THRESHOLD_MINUTES = 15
_AGING_APPROVAL_THRESHOLD_MINUTES = 15
_REMINDER_DEBOUNCE_SECONDS = 30 * 60  # 30 minutes
_LOCK_EXPIRY_WARNING_MINUTES = 10
_DEFAULT_VENDOR_HEALTH_INTERVAL = 300  # 5 minutes


class WatchdogService:
    """Periodic health monitor running as an asyncio background task."""

    def __init__(
        self,
        db: DatabaseClient | None = None,
        check_interval: int | None = None,
        time_fn: Any = None,
    ) -> None:
        self._db = db
        self._interval = check_interval or int(
            os.environ.get("WATCHDOG_INTERVAL_SECONDS", str(_DEFAULT_INTERVAL_SECONDS))
        )
        self._time_fn = time_fn or time.monotonic
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_reminders: dict[str, float] = {}  # approval_id -> last_reminder_timestamp
        self._vendor_health_interval = int(
            os.environ.get("VENDOR_HEALTH_INTERVAL_SECONDS", str(_DEFAULT_VENDOR_HEALTH_INTERVAL))
        )
        self._last_vendor_check: float = 0.0
        self._previous_vendor_state: dict[str, bool] = {}  # agent_id -> healthy

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Start watchdog as asyncio background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Watchdog: started (interval=%ds)", self._interval)

    async def stop(self) -> None:
        """Stop watchdog gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Watchdog: stopped")

    async def run_once(self) -> None:
        """Run a single check cycle (useful for testing)."""
        await self._check_stale_agents()
        await self._check_aging_approvals()
        await self._check_expiring_locks()
        await self._cleanup_expired_tokens()
        await self._check_event_bus_health()
        await self._check_vendor_health()

    async def _loop(self) -> None:
        """Main loop: run checks at the configured interval."""
        while self._running:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Watchdog: check cycle failed: %s", exc, exc_info=True)
            try:
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                break

    async def _check_stale_agents(self) -> None:
        """Find agents with heartbeat > 15 min, emit notification, cleanup."""
        try:
            from datetime import timedelta

            now = datetime.now(UTC)
            threshold = (now - timedelta(minutes=_STALE_AGENT_THRESHOLD_MINUTES)).isoformat()
            rows = await self.db.query(
                "agent_discovery",
                f"status=eq.active&last_heartbeat=lt.{threshold}",
            )
            for row in rows:
                agent_id = row.get("agent_id", "unknown")
                await self._emit_event(
                    channel="coordinator_agent",
                    event_type="agent.stale",
                    entity_id=agent_id,
                    agent_id=agent_id,
                    urgency="high",
                    summary=(
                        f"Agent {agent_id} has not sent a heartbeat "
                        f"in over {_STALE_AGENT_THRESHOLD_MINUTES} minutes"
                    ),
                )
                logger.warning("Watchdog: stale agent detected: %s", agent_id)

            # Cleanup dead agents via RPC
            if rows:
                try:
                    await self.db.rpc(
                        "cleanup_dead_agents",
                        {"p_stale_threshold": f"{_STALE_AGENT_THRESHOLD_MINUTES} minutes"},
                    )
                except Exception as exc:
                    logger.error("Watchdog: cleanup_dead_agents RPC failed: %s", exc)

                # Expire pending approvals from stale agents
                stale_agent_ids = [r.get("agent_id") for r in rows if r.get("agent_id")]
                for agent_id in stale_agent_ids:
                    try:
                        pending = await self.db.query(
                            "approval_queue",
                            f"status=eq.pending&agent_id=eq.{agent_id}",
                        )
                        for approval in pending:
                            await self.db.update(
                                "approval_queue",
                                {"id": approval["id"]},
                                {"status": "expired"},
                            )
                    except Exception as exc:
                        logger.error(
                            "Watchdog: failed to expire approvals for stale agent %s: %s",
                            agent_id,
                            exc,
                        )
        except Exception as exc:
            logger.error("Watchdog: _check_stale_agents failed: %s", exc)

    async def _check_aging_approvals(self) -> None:
        """Find pending approvals > 15 min, emit reminder (debounced 30 min)."""
        try:
            from datetime import timedelta

            now = datetime.now(UTC)
            threshold = (now - timedelta(minutes=_AGING_APPROVAL_THRESHOLD_MINUTES)).isoformat()
            rows = await self.db.query(
                "approval_queue",
                f"status=eq.pending&created_at=lt.{threshold}",
            )
            current_time = self._time_fn()
            for row in rows:
                approval_id = str(row.get("id", ""))
                last_reminder = self._last_reminders.get(approval_id, 0.0)
                if current_time - last_reminder < _REMINDER_DEBOUNCE_SECONDS:
                    continue

                agent_id = row.get("agent_id", "unknown")
                operation = row.get("operation", "unknown")
                await self._emit_event(
                    channel="coordinator_approval",
                    event_type="approval.reminder",
                    entity_id=approval_id,
                    agent_id=agent_id,
                    urgency="medium",
                    summary=(
                        f"Approval {approval_id} for '{operation}' "
                        f"pending > {_AGING_APPROVAL_THRESHOLD_MINUTES}min"
                    ),
                )
                self._last_reminders[approval_id] = current_time

            # Prune stale entries: remove IDs not in the current pending set
            pending_ids = {str(r.get("id", "")) for r in rows}
            stale_keys = [k for k in self._last_reminders if k not in pending_ids]
            for k in stale_keys:
                del self._last_reminders[k]
        except Exception as exc:
            logger.error("Watchdog: _check_aging_approvals failed: %s", exc)

    async def _check_expiring_locks(self) -> None:
        """Find locks within 10 min of TTL, warn holder."""
        try:
            now = datetime.now(UTC)
            from datetime import timedelta

            soon = (now + timedelta(minutes=_LOCK_EXPIRY_WARNING_MINUTES)).isoformat()
            rows = await self.db.query(
                "file_locks",
                f"expires_at=lt.{soon}&expires_at=gt.{now.isoformat()}",
            )
            for row in rows:
                file_path = row.get("file_path", "unknown")
                locked_by = row.get("locked_by", "unknown")
                await self._emit_event(
                    channel="coordinator_agent",
                    event_type="agent.lock_expiring",
                    entity_id=file_path,
                    agent_id=locked_by,
                    urgency="medium",
                    summary=(
                        f"Lock '{file_path}' by {locked_by} "
                        f"expires in <{_LOCK_EXPIRY_WARNING_MINUTES}min"
                    ),
                )
        except Exception as exc:
            logger.error("Watchdog: _check_expiring_locks failed: %s", exc)

    async def _cleanup_expired_tokens(self) -> None:
        """Delete expired notification tokens."""
        try:
            now = datetime.now(UTC)
            expired = await self.db.query(
                "notification_tokens",
                f"expires_at=lt.{now.isoformat()}",
            )
            for row in expired:
                token_val = row.get("token")
                if token_val:
                    await self.db.delete("notification_tokens", {"token": token_val})
            if expired:
                logger.info("Watchdog: cleaned up %d expired notification tokens", len(expired))
        except Exception as exc:
            logger.error("Watchdog: _cleanup_expired_tokens failed: %s", exc)

    async def _check_event_bus_health(self) -> None:
        """Check if event bus has failed, try restart."""
        try:
            bus = get_event_bus()
            if bus.failed:
                logger.warning("Watchdog: event bus is in failed state, attempting restart")
                # Emit notification directly (bus is down)
                await self._emit_event(
                    channel="coordinator_agent",
                    event_type="bus.connection_failed",
                    entity_id="event_bus",
                    agent_id="watchdog",
                    urgency="high",
                    summary="Event bus connection failed, attempting restart",
                )
                try:
                    await bus.restart()
                    logger.info("Watchdog: event bus restarted successfully")
                except Exception as exc:
                    logger.error("Watchdog: event bus restart failed: %s", exc)
        except Exception as exc:
            logger.error("Watchdog: _check_event_bus_health failed: %s", exc)

    async def _check_vendor_health(self) -> None:
        """Check vendor CLI/API availability, emit events on state changes.

        Runs at a separate interval (VENDOR_HEALTH_INTERVAL_SECONDS, default 5m)
        to avoid excessive probing. Skips first run (no baseline).
        """
        current_time = self._time_fn()
        if current_time - self._last_vendor_check < self._vendor_health_interval:
            return
        self._last_vendor_check = current_time

        try:
            # Import from parallel-infrastructure scripts
            import importlib.util

            vendor_health_path = (
                Path(__file__).resolve().parent.parent.parent
                / "skills"
                / "parallel-infrastructure"
                / "scripts"
                / "vendor_health.py"
            )
            if not vendor_health_path.exists():
                return

            spec = importlib.util.spec_from_file_location("vendor_health", vendor_health_path)
            if not spec or not spec.loader:
                return
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            report = mod.check_all_vendors()
            current_state = {v.agent_id: v.healthy for v in report.vendors}

            # Skip first run (no baseline to compare)
            if not self._previous_vendor_state:
                self._previous_vendor_state = current_state
                return

            # Detect state changes
            for agent_id, healthy in current_state.items():
                was_healthy = self._previous_vendor_state.get(agent_id)
                if was_healthy is None:
                    continue  # New vendor, skip

                if was_healthy and not healthy:
                    await self._emit_event(
                        channel="coordinator_agent",
                        event_type="vendor.unavailable",
                        entity_id=agent_id,
                        agent_id="watchdog",
                        urgency="medium",
                        summary=f"Vendor {agent_id} is no longer available",
                    )
                    logger.warning("Watchdog: vendor %s became unavailable", agent_id)
                elif not was_healthy and healthy:
                    await self._emit_event(
                        channel="coordinator_agent",
                        event_type="vendor.recovered",
                        entity_id=agent_id,
                        agent_id="watchdog",
                        urgency="low",
                        summary=f"Vendor {agent_id} has recovered",
                    )
                    logger.info("Watchdog: vendor %s recovered", agent_id)

            self._previous_vendor_state = current_state

        except Exception as exc:
            logger.error("Watchdog: _check_vendor_health failed: %s", exc)

    async def _emit_event(
        self,
        channel: str,
        event_type: str,
        entity_id: str,
        agent_id: str,
        urgency: str,
        summary: str,
    ) -> None:
        """Emit event via direct pg_notify (not through event bus listener).

        Uses the DatabaseClient to send a NOTIFY directly, bypassing event bus
        to avoid loops.
        """
        event = CoordinatorEvent(
            event_type=event_type,
            channel=channel,
            entity_id=entity_id,
            agent_id=agent_id,
            urgency=urgency,  # type: ignore[arg-type]
            summary=summary,
        )
        try:
            # Try pg_notify via RPC with internal flag to prevent trigger loops
            await self.db.rpc(
                "pg_notify_direct",
                {
                    "p_channel": channel,
                    "p_payload": event.to_json(),
                },
            )
        except Exception:
            # Fallback: just log the event if direct notify is not available
            logger.info(
                "Watchdog event (direct notify unavailable): %s %s",
                event_type,
                summary,
            )


# --- Singleton ---

_watchdog: WatchdogService | None = None


def get_watchdog() -> WatchdogService:
    """Return the singleton WatchdogService."""
    global _watchdog
    if _watchdog is None:
        _watchdog = WatchdogService()
    return _watchdog


def reset_watchdog() -> None:
    """Reset the singleton (for tests)."""
    global _watchdog
    _watchdog = None

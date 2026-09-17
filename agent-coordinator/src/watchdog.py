"""Async background task for periodic health monitoring.

Periodically checks for stale agents, aging approvals, expiring locks,
expired tokens, and event bus health. Emits notifications via pg_notify.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
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
_DEFAULT_CATALOG_REFRESH_INTERVAL = 6 * 60 * 60
_DEFAULT_LOCAL_PROBE_INTERVAL = 5 * 60
_DEFAULT_LEDGER_ROLLUP_INTERVAL = 5 * 60

RoutingJob = tuple[Callable[[], Awaitable[Any]], int]


def _positive_int_env(name: str, default: int) -> int:
    """Read a positive interval without letting bad optional config disable watchdog."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r; using %d", name, raw, default)
        return default
    if value <= 0:
        logger.warning("Ignoring non-positive %s=%r; using %d", name, raw, default)
        return default
    return value


class WatchdogService:
    """Periodic health monitor running as an asyncio background task."""

    def __init__(
        self,
        db: DatabaseClient | None = None,
        check_interval: int | None = None,
        time_fn: Any = None,
        routing_jobs: Mapping[str, RoutingJob] | None = None,
        now_fn: Callable[[], datetime] | None = None,
        vendor_health_fn: Callable[[], Any] | None = None,
        vendor_registry: Any | None = None,
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
        self._now_fn = now_fn or (lambda: datetime.now(UTC))
        self._vendor_health_fn = vendor_health_fn
        self._vendor_registry = vendor_registry
        self._routing_jobs = (
            dict(routing_jobs) if routing_jobs is not None else self._default_routing_jobs()
        )
        self._last_routing_run: dict[str, float] = {}

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    @property
    def vendor_registry(self) -> Any:
        if self._vendor_registry is None:
            from .audit import get_audit_service
            from .vendor_registry import VendorRegistryService

            self._vendor_registry = VendorRegistryService(db=self.db, audit=get_audit_service())
        return self._vendor_registry

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
        try:
            await self.vendor_registry.compact_rate_limits()
        except Exception as exc:  # noqa: BLE001
            logger.error("Watchdog: vendor rate-limit compaction failed: %s", exc)
        await self._run_routing_jobs()

    def _default_routing_jobs(self) -> dict[str, RoutingJob]:
        """Build lazy routing jobs; missing optional credentials degrade safely."""

        async def refresh_catalog() -> dict[str, Any]:
            api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
            if not api_key:
                return {"skipped": "OPENROUTER_API_KEY is not configured"}
            from .model_routing.catalog import CatalogService
            from .model_routing.refresher import OpenRouterRefresher

            result = await OpenRouterRefresher(CatalogService(self.db), api_key=api_key).refresh()
            return {"updated": result.updated}

        async def probe_local_endpoints() -> dict[str, Any]:
            from .model_routing.catalog import CatalogService
            from .model_routing.local_endpoints import LocalEndpointService

            service = LocalEndpointService(CatalogService(self.db))
            await service.sync_from_agents_config()
            results = await service.probe_all()
            return {
                "probed": len(results),
                "available": sum(result.available for result in results),
            }

        async def sync_configured_catalog() -> dict[str, Any]:
            from .model_routing.catalog import CatalogService
            from .model_routing.configured_catalog import ConfiguredCatalogSync

            result = await ConfiguredCatalogSync(catalog=CatalogService(self.db)).sync()
            return {
                "inserted": result.inserted,
                "existing": result.existing,
                "skipped": result.skipped,
            }

        async def rollup_ledger() -> dict[str, Any]:
            from .model_routing.ledger import LedgerService

            return await LedgerService(self.db).rollup_current_month()

        return {
            "configured_catalog_sync": (
                sync_configured_catalog,
                _positive_int_env(
                    "ROUTING_CATALOG_REFRESH_INTERVAL_SECONDS",
                    _DEFAULT_CATALOG_REFRESH_INTERVAL,
                ),
            ),
            "catalog_refresh": (
                refresh_catalog,
                _positive_int_env(
                    "ROUTING_CATALOG_REFRESH_INTERVAL_SECONDS",
                    _DEFAULT_CATALOG_REFRESH_INTERVAL,
                ),
            ),
            "local_endpoint_probe": (
                probe_local_endpoints,
                _positive_int_env(
                    "ROUTING_LOCAL_PROBE_INTERVAL_SECONDS",
                    _DEFAULT_LOCAL_PROBE_INTERVAL,
                ),
            ),
            "ledger_rollup": (
                rollup_ledger,
                _positive_int_env(
                    "ROUTING_LEDGER_ROLLUP_INTERVAL_SECONDS",
                    _DEFAULT_LEDGER_ROLLUP_INTERVAL,
                ),
            ),
        }

    async def _run_routing_jobs(self) -> None:
        """Run due routing jobs independently so one failure cannot stop peers."""
        current_time = self._time_fn()
        for name, (job, interval) in self._routing_jobs.items():
            last_run = self._last_routing_run.get(name)
            if last_run is not None and current_time - last_run < interval:
                continue
            self._last_routing_run[name] = current_time
            try:
                await job()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Watchdog routing job %s failed: %s", name, exc, exc_info=True)
                await self._record_routing_job_failure(name, exc)

    async def _record_routing_job_failure(self, name: str, exc: Exception) -> None:
        try:
            await self.db.insert(
                "audit_log",
                {
                    "agent_id": "watchdog",
                    "agent_type": "system",
                    "operation": "signal.routing_job_failed",
                    "parameters": {"job": name},
                    "result": {},
                    "success": False,
                    "error_message": str(exc),
                },
            )
        except Exception as audit_exc:
            logger.error(
                "Watchdog could not record routing job failure for %s: %s",
                name,
                audit_exc,
            )

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

    def _load_vendor_health_report(self) -> Any | None:
        if self._vendor_health_fn is not None:
            return self._vendor_health_fn()

        import importlib.util

        skills_root = Path(
            os.environ.get(
                "SKILLS_ROOT",
                str(Path(__file__).resolve().parent.parent.parent / "skills"),
            )
        )
        vendor_health_path = (
            skills_root / "parallel-infrastructure" / "scripts" / "vendor_health.py"
        )
        if not vendor_health_path.exists():
            logger.warning("Watchdog: vendor health probe missing at %s", vendor_health_path)
            return None
        spec = importlib.util.spec_from_file_location("vendor_health", vendor_health_path)
        if not spec or not spec.loader:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.check_all_vendors()

    async def _check_vendor_health(self) -> None:
        """Persist every lane snapshot and emit transitions after the first poll."""
        current_time = self._time_fn()
        if current_time - self._last_vendor_check < self._vendor_health_interval:
            return
        self._last_vendor_check = current_time

        try:
            report = self._load_vendor_health_report()
            if report is None:
                return
            current_state = {vendor.agent_id: vendor.healthy for vendor in report.vendors}
            observed_at = self._now_fn()
            stale_after = observed_at + timedelta(seconds=2 * self._vendor_health_interval)

            for vendor in report.vendors:
                reason = getattr(vendor, "error", None)
                if reason == "no_probe_method":
                    status = "unknown"
                elif vendor.healthy:
                    status = "available"
                    reason = None
                else:
                    status = "unavailable"
                    reason = reason or "probe_failed"
                try:
                    await self.vendor_registry.persist_probe(
                        vendor.agent_id,
                        observation_id=(
                            f"watchdog:{vendor.agent_id}:{int(observed_at.timestamp())}"
                        ),
                        status=status,
                        source_agent_id="watchdog",
                        reason=reason,
                        observed_at=observed_at,
                        stale_after=stale_after,
                        metadata={"probe": "vendor_health"},
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Watchdog: failed to persist vendor probe for %s: %s",
                        vendor.agent_id,
                        exc,
                    )
                    try:
                        await self.vendor_registry.audit_probe_persistence_failure(
                            vendor.agent_id,
                            source_agent_id="watchdog",
                            reason="probe_persistence_failed",
                        )
                    except Exception as audit_exc:  # noqa: BLE001
                        logger.error(
                            "Watchdog: failed to audit vendor probe persistence "
                            "failure for %s: %s",
                            vendor.agent_id,
                            audit_exc,
                        )

            # The first poll establishes transition state but still persists snapshots.
            if not self._previous_vendor_state:
                self._previous_vendor_state = current_state
                return

            for agent_id, healthy in current_state.items():
                was_healthy = self._previous_vendor_state.get(agent_id)
                if was_healthy is None:
                    continue
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
        except Exception as exc:  # noqa: BLE001
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

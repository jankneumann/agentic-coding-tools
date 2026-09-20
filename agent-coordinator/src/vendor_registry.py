"""Configured vendor-lane registry and durable transient availability state."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, cast

from .agents_config import AgentEntry, get_agents_config, get_provider_model_map
from .db import DatabaseClient, get_db

logger = logging.getLogger(__name__)

DEFAULT_UNKNOWN_LIMIT_TTL = timedelta(seconds=900)
DEFAULT_MAX_LIMIT_TTL = timedelta(seconds=604800)
DEFAULT_AUDIT_RETENTION = timedelta(days=7)


class UnknownVendorLaneError(ValueError):
    """Raised when a registry write or detail read names no configured lane."""


class ObservationConflictError(RuntimeError):
    """Raised when an observation id is replayed with different semantics."""


def _utc_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _utc_datetime(value).isoformat()


class VendorRegistryService:
    """Aggregate configured lanes with probes, limits, and dg-00 catalog rows."""

    def __init__(
        self,
        db: DatabaseClient | None = None,
        *,
        agents: Sequence[AgentEntry] | None = None,
        provider_model_map: Mapping[str, Any] | None = None,
        now_fn: Callable[[], datetime] | None = None,
        unknown_limit_ttl: timedelta = DEFAULT_UNKNOWN_LIMIT_TTL,
        max_limit_ttl: timedelta = DEFAULT_MAX_LIMIT_TTL,
        audit_retention: timedelta = DEFAULT_AUDIT_RETENTION,
        audit: Any | None = None,
    ) -> None:
        self._db = db
        self._agents = list(agents) if agents is not None else None
        self._provider_model_map = provider_model_map
        self._now_fn = now_fn or (lambda: datetime.now(UTC))
        self._unknown_limit_ttl = unknown_limit_ttl
        self._max_limit_ttl = max_limit_ttl
        self._audit_retention = audit_retention
        self._audit = audit

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    @property
    def agents(self) -> list[AgentEntry]:
        if self._agents is None:
            self._agents = list(get_agents_config())
        return self._agents

    def _agent(self, agent_id: str) -> AgentEntry:
        for agent in self.agents:
            if agent.name == agent_id:
                return agent
        raise UnknownVendorLaneError(agent_id)

    async def list_vendors(
        self,
        *,
        capability: str | None = None,
        archetype: str | None = None,
        dispatch_mode: str | None = None,
        location: str | None = None,
        available_only: bool = False,
    ) -> list[dict[str, Any]]:
        agents = [
            agent
            for agent in self.agents
            if (capability is None or capability in agent.capabilities)
            and (archetype is None or archetype in agent.archetypes)
            and (dispatch_mode is None or dispatch_mode in self._dispatch_modes(agent))
            and (location is None or agent.location == location)
        ]
        snapshots = await self._snapshots(agents)
        lanes = [
            await self._lane(
                agent,
                snapshots["probes"].get(agent.name),
                snapshots["limits"].get(agent.name, []),
                snapshots["catalog"],
            )
            for agent in agents
        ]
        if available_only:
            lanes = [lane for lane in lanes if lane["availability"]["available"]]
        return sorted(lanes, key=lambda lane: lane["agent_id"])

    async def list_lanes(self, **filters: Any) -> list[dict[str, Any]]:
        """Compatibility name for consumers that call configured entries lanes."""
        return await self.list_vendors(**filters)

    async def get_vendor(self, agent_id: str) -> dict[str, Any]:
        agent = self._agent(agent_id)
        snapshots = await self._snapshots([agent])
        return await self._lane(
            agent,
            snapshots["probes"].get(agent_id),
            snapshots["limits"].get(agent_id, []),
            snapshots["catalog"],
        )

    async def get_availability(self, agent_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], (await self.get_vendor(agent_id))["availability"])

    async def _snapshots(self, agents: Sequence[AgentEntry]) -> dict[str, Any]:
        if not agents:
            return {"probes": {}, "limits": {}, "catalog": []}
        encoded_ids = ",".join(agent.name for agent in agents)
        now = _iso(self._now_fn())
        probe_rows, limit_rows, catalog_rows = await asyncio.gather(
            self.db.query("vendor_probe_state", f"agent_id=in.({encoded_ids})"),
            self.db.query(
                "vendor_rate_limits",
                f"agent_id=in.({encoded_ids})&reset_at=gt.{now}",
            ),
            self.db.query("model_catalog", "order=vendor.asc"),
        )
        probes = {
            str(row["agent_id"]): row
            for row in probe_rows
            if isinstance(row, dict) and row.get("agent_id")
        }
        limits: dict[str, list[dict[str, Any]]] = {}
        for row in limit_rows:
            if not isinstance(row, dict) or not row.get("agent_id"):
                continue
            limits.setdefault(str(row["agent_id"]), []).append(row)
        return {"probes": probes, "limits": limits, "catalog": catalog_rows}

    async def _lane(
        self,
        agent: AgentEntry,
        probe: dict[str, Any] | None,
        limits: list[dict[str, Any]],
        catalog_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        active_limits = self._active_limits(limits)
        cost = await self._cost_projection(agent, catalog_rows, active_limits)
        availability = self._availability(agent, probe, active_limits, cost["models"])
        return {
            "agent_id": agent.name,
            "vendor_type": agent.type,
            "policy_vendor": agent.policy_vendor or agent.type,
            "catalog_vendor": agent.catalog_vendor,
            "location": agent.location,
            "capabilities": sorted(set(agent.capabilities)),
            "archetypes": sorted(set(agent.archetypes)),
            "isolation": agent.isolation,
            "transport": agent.transport,
            "dispatch_modes": self._dispatch_modes(agent),
            "dispatchable": bool(
                agent.cli is not None or agent.sdk is not None or agent.transport in {"mcp", "http"}
            ),
            "availability": availability,
            "cost": cost,
        }

    @staticmethod
    def _dispatch_modes(agent: AgentEntry) -> list[str]:
        modes = set(agent.cli.dispatch_modes) if agent.cli is not None else set()
        if agent.sdk is not None:
            modes.add("sdk")
        return sorted(modes)

    def _active_limits(self, limits: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        now = _utc_datetime(self._now_fn())
        active: list[dict[str, Any]] = []
        for row in limits:
            reset_at = row.get("reset_at")
            if reset_at is None or now >= _utc_datetime(reset_at):
                continue
            active.append(
                {
                    "observation_id": str(row["observation_id"]),
                    "scope": str(row.get("scope") or "lane"),
                    "model": row.get("model"),
                    "reason": str(row.get("reason") or ""),
                    "source_agent_id": str(row.get("source_agent_id") or ""),
                    "observed_at": _iso(_utc_datetime(row["observed_at"])),
                    "reset_at": _iso(_utc_datetime(reset_at)),
                }
            )
        return sorted(active, key=lambda row: (row["reset_at"], row["observation_id"]))

    def _availability(
        self,
        agent: AgentEntry,
        probe: dict[str, Any] | None,
        limits: list[dict[str, Any]],
        models: list[dict[str, Any]],
    ) -> dict[str, Any]:
        lane_limits = [row for row in limits if row["scope"] == "lane"]
        if lane_limits:
            return self._availability_result(
                agent.name,
                "limited",
                False,
                lane_limits[0]["reason"],
                lane_limits[0]["source_agent_id"],
                lane_limits[0]["observed_at"],
                None,
                lane_limits[0]["reset_at"],
                limits,
            )

        if agent.endpoint_kind == "local":
            eligible = any(row["available"] and not row["stale"] for row in models)
            if not eligible:
                nonstale = any(not row["stale"] for row in models)
                status = "unavailable" if nonstale else "unknown"
                reason = "catalog_unavailable" if nonstale else "catalog_missing_or_stale"
                return self._availability_result(
                    agent.name,
                    status,
                    False,
                    reason,
                    "model_catalog",
                    None,
                    None,
                    None,
                    limits,
                )

        if probe is None:
            return self._availability_result(
                agent.name,
                "unknown",
                False,
                "missing_probe",
                None,
                None,
                None,
                None,
                limits,
            )

        stale_after = _utc_datetime(probe["stale_after"])
        if _utc_datetime(self._now_fn()) >= stale_after:
            return self._availability_result(
                agent.name,
                "unknown",
                False,
                "stale_probe",
                str(probe.get("source_agent_id") or ""),
                _iso(_utc_datetime(probe["observed_at"])),
                _iso(stale_after),
                None,
                limits,
            )

        status = str(probe.get("status") or "unknown")
        return self._availability_result(
            agent.name,
            status,
            status == "available",
            probe.get("reason"),
            str(probe.get("source_agent_id") or ""),
            _iso(_utc_datetime(probe["observed_at"])),
            _iso(stale_after),
            None,
            limits,
        )

    @staticmethod
    def _availability_result(
        agent_id: str,
        status: str,
        available: bool,
        reason: Any,
        source: Any,
        observed_at: Any,
        stale_after: Any,
        reset_at: Any,
        limits: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "agent_id": agent_id,
            "status": status,
            "available": available,
            "reason": reason,
            "source": source,
            "observed_at": observed_at,
            "stale_after": stale_after,
            "reset_at": reset_at,
            "rate_limits": limits,
        }

    async def _cost_projection(
        self,
        agent: AgentEntry,
        rows: Sequence[dict[str, Any]],
        limits: Sequence[dict[str, Any]],
    ) -> dict[str, Any]:
        all_models_matched = True
        model_limits = {
            str(row["model"]) for row in limits if row["scope"] == "model" and row.get("model")
        }
        projections: list[dict[str, Any]] = []
        misses: list[dict[str, Any]] = []
        for model in self._agent_models(agent):
            if agent.catalog_vendor is None or agent.endpoint_kind is None:
                matches: list[dict[str, Any]] = []
            else:
                matches = [
                    row
                    for row in rows
                    if str(row.get("model") or "") == model
                    and row.get("endpoint_kind") == agent.endpoint_kind
                    and row.get("base_url") == agent.base_url
                    and row.get("vendor") == agent.catalog_vendor
                ]
            if len(matches) != 1:
                all_models_matched = False
                miss_reason = "ambiguous" if matches else "missing"
                logger.warning(
                    "vendor catalog projection miss",
                    extra={
                        "agent_id": agent.name,
                        "model": model,
                        "reason": miss_reason,
                        "match_count": len(matches),
                    },
                )
                await self._audit_event(
                    "vendor_registry",
                    "vendor_catalog_projection_miss",
                    agent.name,
                    {"model": model, "reason": miss_reason, "match_count": len(matches)},
                    success=False,
                )
                misses.append(
                    {
                        "catalog_vendor": agent.catalog_vendor or "",
                        "model": model,
                        "endpoint_kind": agent.endpoint_kind or "",
                        "base_url": agent.base_url,
                        "reason": miss_reason,
                    }
                )
                continue
            row = matches[0]
            projections.append(
                {
                    "catalog_vendor": str(row.get("vendor") or ""),
                    "model": model,
                    "endpoint_kind": str(row.get("endpoint_kind") or ""),
                    "base_url": row.get("base_url"),
                    "prompt_usd_per_mtok": row.get("prompt_usd_per_mtok"),
                    "completion_usd_per_mtok": row.get("completion_usd_per_mtok"),
                    "refreshed_at": row.get("refreshed_at"),
                    "available": bool(row.get("available", True)) and model not in model_limits,
                    "stale": bool(row.get("stale", False)),
                }
            )
        known = all_models_matched and bool(projections) and all(
            row["prompt_usd_per_mtok"] is not None
            and row["completion_usd_per_mtok"] is not None
            and not row["stale"]
            for row in projections
        )
        return {"source": "model_catalog", "known": known, "models": projections, "misses": misses}

    def _agent_models(self, agent: AgentEntry) -> list[str]:
        if agent.endpoint_kind == "vendor-sdk":
            if agent.sdk is None:
                return []
            return sorted({agent.sdk.model, *agent.sdk.model_fallbacks})
        models: set[str] = set()
        if agent.cli is not None:
            models.update(model for model in [agent.cli.model, *agent.cli.model_fallbacks] if model)
        if agent.sdk is not None and agent.endpoint_kind != "vendor-cli":
            models.update([agent.sdk.model, *agent.sdk.model_fallbacks])
        raw_map = self._provider_model_map
        if raw_map is None:
            raw_map = get_provider_model_map()
        providers = raw_map.get("providers", raw_map) if isinstance(raw_map, Mapping) else {}
        provider = providers.get(agent.type, {}) if isinstance(providers, Mapping) else {}
        if isinstance(provider, Mapping) and agent.endpoint_kind != "vendor-sdk":
            for value in provider.values():
                if isinstance(value, str):
                    models.add(value)
                elif isinstance(value, Mapping) and isinstance(value.get("model"), str):
                    models.add(str(value["model"]))
        return sorted(models)

    @staticmethod
    def quote_cost(
        model: Mapping[str, Any],
        *,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> Decimal | None:
        if model.get("stale"):
            return None
        try:
            prompt_price = Decimal(str(model["prompt_usd_per_mtok"]))
            completion_price = Decimal(str(model["completion_usd_per_mtok"]))
        except (InvalidOperation, KeyError, TypeError):
            return None
        if prompt_price < 0 or completion_price < 0:
            return None
        quote = (
            Decimal(prompt_tokens) * prompt_price + Decimal(completion_tokens) * completion_price
        ) / Decimal(1_000_000)
        # Contract choice: exact half-microdollar values round up, never by the
        # ambient Decimal context (which defaults to bankers/half-even rounding).
        return quote.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    async def persist_probe(
        self,
        agent_id: str,
        *,
        observation_id: str,
        status: str,
        source_agent_id: str,
        stale_after: str | datetime,
        observed_at: str | datetime | None = None,
        reason: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        self._agent(agent_id)
        if status not in {"available", "unavailable", "unknown"}:
            raise ValueError("invalid probe status")
        observed = _utc_datetime(observed_at or self._now_fn())
        result = await self.db.rpc(
            "upsert_vendor_probe_state",
            {
                "p_agent_id": agent_id,
                "p_observation_id": observation_id,
                "p_status": status,
                "p_source_agent_id": source_agent_id,
                "p_reason": reason,
                "p_observed_at": _iso(observed),
                "p_stale_after": _iso(_utc_datetime(stale_after)),
                "p_metadata": dict(metadata or {}),
            },
        )
        row = result[0] if isinstance(result, list) and result else result
        await self._audit_event(
            source_agent_id,
            "vendor_probe_persisted",
            agent_id,
            {"status": status, "observation_id": observation_id},
        )
        return row if isinstance(row, dict) else None

    async def audit_probe_persistence_failure(
        self,
        agent_id: str,
        *,
        source_agent_id: str,
        reason: str,
    ) -> None:
        """Durably record a watchdog snapshot persistence failure."""
        await self._audit_event(
            source_agent_id,
            "vendor_probe_persistence_failed",
            agent_id,
            {"status": "failed", "reason": reason},
            success=False,
        )

    async def record_rate_limit(
        self,
        agent_id: str,
        *,
        observation_id: str,
        reason: str,
        source_agent_id: str,
        reset_at: str | datetime | None = None,
        retry_after_seconds: int | None = None,
        scope: str = "lane",
        model: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        received_at: str | datetime | None = None,
    ) -> dict[str, str]:
        async def reject(rejection_reason: str, message: str) -> None:
            await self._audit_event(
                source_agent_id,
                "vendor_rate_limit_observed",
                agent_id,
                {
                    "status": "rejected",
                    "observation_id": observation_id,
                    "reason": rejection_reason,
                },
                success=False,
            )
            raise ValueError(message)
        self._agent(agent_id)
        received = _utc_datetime(received_at or self._now_fn())
        if reset_at is not None and retry_after_seconds is not None:
            await reject(
                "conflicting_reset_fields", "exactly one reset form may be supplied"
            )
        if not observation_id.strip() or not reason.strip():
            await reject(
                "missing_required_fields", "observation_id and reason are required"
            )
        if scope not in {"lane", "model"}:
            await reject("invalid_scope", "scope must be lane or model")
        if scope == "model" and not (model and model.strip()):
            await reject("missing_model", "model scope requires a concrete model")
        if retry_after_seconds is not None:
            if retry_after_seconds < 1:
                await reject("invalid_retry_after", "retry_after_seconds must be positive")
            normalized_reset = received + timedelta(seconds=retry_after_seconds)
            reset_marker: Any = {"retry_after_seconds": retry_after_seconds}
        elif reset_at is not None:
            normalized_reset = _utc_datetime(reset_at)
            reset_marker = {"reset_at": _iso(normalized_reset)}
        else:
            normalized_reset = received + self._unknown_limit_ttl
            reset_marker = {"default_ttl": True}
        if normalized_reset <= received:
            await reject("reset_not_future", "reset_at must be in the future")
        if normalized_reset - received > self._max_limit_ttl:
            await reject("reset_exceeds_maximum", "reset exceeds configured maximum")
        canonical = {
            "agent_id": agent_id,
            "source_agent_id": source_agent_id,
            "observation_id": observation_id,
            "scope": scope,
            "model": model,
            "reason": reason,
            "metadata": dict(metadata or {}),
            **reset_marker,
        }
        payload_hash = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        result = await self.db.rpc(
            "record_vendor_rate_limit",
            {
                "p_observation_id": observation_id,
                "p_agent_id": agent_id,
                "p_scope": scope,
                "p_model": model,
                "p_reason": reason,
                "p_source_agent_id": source_agent_id,
                "p_observed_at": _iso(received),
                "p_reset_at": _iso(normalized_reset),
                "p_payload_hash": payload_hash,
                "p_metadata": dict(metadata or {}),
            },
        )
        row = result[0] if isinstance(result, list) and result else result
        write_status = str(row.get("write_status") if isinstance(row, dict) else "")
        response_reset = (
            row.get("normalized_reset_at") if isinstance(row, dict) else _iso(normalized_reset)
        ) or _iso(normalized_reset)
        await self._audit_event(
            source_agent_id,
            "vendor_rate_limit_observed",
            agent_id,
            {
                "status": write_status,
                "observation_id": observation_id,
                "scope": scope,
                "reason": reason,
            },
        )
        if write_status == "conflict":
            raise ObservationConflictError(observation_id)
        if write_status not in {"accepted", "duplicate"}:
            write_status = "accepted"
        return {
            "observation_id": observation_id,
            "status": write_status,
            "reset_at": str(response_reset),
        }

    async def compact_rate_limits(self) -> int:
        cutoff = _utc_datetime(self._now_fn()) - self._audit_retention
        result = await self.db.rpc(
            "compact_vendor_rate_limits",
            {"p_cutoff": _iso(cutoff)},
        )
        if isinstance(result, int):
            deleted = result
        elif isinstance(result, list) and result:
            value = result[0]
            raw_deleted = (
                value.get("compact_vendor_rate_limits", value.get("deleted_count", 0))
                if isinstance(value, dict)
                else value
            )
            deleted = int(cast(int | float | str, raw_deleted or 0))
        elif isinstance(result, dict):
            raw_deleted = result.get(
                "compact_vendor_rate_limits", result.get("deleted_count", 0)
            )
            deleted = int(cast(int | float | str, raw_deleted or 0))
        else:
            deleted = 0
        await self._audit_event(
            "watchdog",
            "vendor_rate_limits_compacted",
            "vendor_rate_limits",
            {
                "status": "compacted",
                "reason": "audit_retention_elapsed",
                "deleted_count": deleted,
            },
        )
        return deleted

    async def _audit_event(
        self,
        source_agent_id: str,
        operation: str,
        agent_id: str,
        result: dict[str, Any],
        *,
        success: bool = True,
    ) -> None:
        logger.info(
            operation,
            extra={"agent_id": agent_id, "source_agent_id": source_agent_id, **result},
        )
        if self._audit is not None:
            await self._audit.log_operation(
                agent_id=source_agent_id,
                operation=operation,
                parameters={"target_agent_id": agent_id},
                result=result,
                success=success,
            )

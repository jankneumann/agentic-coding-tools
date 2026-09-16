"""Registration and health probing for local OpenAI-compatible endpoints."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import httpx

from .catalog import CatalogEntry, CatalogService


@dataclass(frozen=True)
class ProbeResult:
    vendor: str
    model: str
    available: bool
    latency_ms: float | None
    error: str | None = None


class LocalEndpointService:
    def __init__(
        self,
        catalog: CatalogService,
        *,
        client: httpx.AsyncClient | None = None,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._catalog = catalog
        self._client = client
        self._time_fn = time_fn or time.perf_counter

    async def register(self, config: dict[str, Any]) -> dict[str, Any]:
        base_url = str(config.get("base_url") or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("local endpoint base_url is required")
        model = str(config.get("model") or "").strip()
        if not model:
            raise ValueError("local endpoint model is required")
        return await self._catalog.upsert(
            CatalogEntry(
                vendor=str(config.get("vendor") or "local"),
                model=model,
                endpoint_kind="local",
                base_url=base_url,
                prompt_usd_per_mtok=0.0,
                completion_usd_per_mtok=0.0,
                context_window=config.get("context_window"),
                benchmark_priors=dict(config.get("benchmark_priors") or {}),
            )
        )

    async def register_many(self, configs: Iterable[dict[str, Any]]) -> int:
        count = 0
        for config in configs:
            if config.get("endpoint_kind", "local") != "local":
                continue
            await self.register(config)
            count += 1
        return count

    async def sync_from_agents_config(self) -> int:
        """Register future endpoint fields from AgentEntry without owning its schema."""
        from ..agents_config import get_agents_config

        configs: list[dict[str, Any]] = []
        for agent in get_agents_config():
            if getattr(agent, "endpoint_kind", None) != "local":
                continue
            model = getattr(agent, "model", None)
            if model is None and agent.sdk is not None:
                model = agent.sdk.model
            configs.append(
                {
                    "vendor": agent.type,
                    "model": model or agent.name,
                    "endpoint_kind": "local",
                    "base_url": getattr(agent, "base_url", None),
                    "benchmark_priors": getattr(agent, "benchmark_priors", {}),
                }
            )
        return await self.register_many(configs)

    async def probe_all(self) -> list[ProbeResult]:
        rows = await self._catalog.list_entries(endpoint_kind="local")
        return [await self._probe(row) for row in rows]

    async def _probe(self, row: dict[str, Any]) -> ProbeResult:
        vendor = str(row["vendor"])
        model = str(row["model"])
        base_url = str(row.get("base_url") or "").rstrip("/")
        started = self._time_fn()
        try:
            if not base_url:
                raise ValueError("missing base_url")
            if self._client is None:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"{base_url}/models")
            else:
                response = await self._client.get(f"{base_url}/models")
            response.raise_for_status()
            latency_ms = (self._time_fn() - started) * 1000.0
            await self._catalog.set_availability(
                vendor,
                model,
                "local",
                available=True,
                p50_latency_ms=latency_ms,
            )
            return ProbeResult(vendor, model, True, latency_ms)
        except Exception as exc:
            await self._catalog.set_availability(
                vendor,
                model,
                "local",
                available=False,
                p50_latency_ms=None,
            )
            return ProbeResult(vendor, model, False, None, str(exc))

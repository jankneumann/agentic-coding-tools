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

        existing_rows = await self._catalog.list_entries(endpoint_kind="local")
        known_endpoints = (
            {
                (
                    str(row.get("vendor") or "local"),
                    str(row.get("base_url") or "").strip().rstrip("/"),
                )
                for row in existing_rows
                if isinstance(row, dict)
            }
            if isinstance(existing_rows, list)
            else set()
        )
        configs: list[dict[str, Any]] = []
        for agent in get_agents_config():
            if getattr(agent, "endpoint_kind", None) != "local":
                continue
            vendor = str(agent.type or "local")
            base_url = str(getattr(agent, "base_url", None) or "").strip().rstrip("/")
            model = agent.sdk.model if agent.sdk is not None else None
            if model is None and (vendor, base_url) in known_endpoints:
                continue
            configs.append(
                {
                    "vendor": vendor,
                    "model": model or agent.name,
                    "endpoint_kind": "local",
                    "base_url": base_url,
                    "benchmark_priors": getattr(agent, "benchmark_priors", {}),
                }
            )
        return await self.register_many(configs)

    async def probe_all(self) -> list[ProbeResult]:
        rows = await self._catalog.list_entries(endpoint_kind="local")
        results: list[ProbeResult] = []
        for row in rows:
            try:
                results.append(await self._probe(row))
            except Exception as exc:
                results.append(
                    ProbeResult(
                        str(row.get("vendor") or ""),
                        str(row.get("model") or ""),
                        False,
                        None,
                        str(exc),
                    )
                )
        return results

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
            reported_model = _single_reported_model(response)
            if reported_model is not None and reported_model != model:
                raw_priors = row.get("benchmark_priors")
                benchmark_priors = (
                    {
                        str(key): float(value)
                        for key, value in raw_priors.items()
                        if isinstance(value, int | float) and not isinstance(value, bool)
                    }
                    if isinstance(raw_priors, dict)
                    else {}
                )
                await self._catalog.upsert(
                    CatalogEntry(
                        vendor=vendor,
                        model=reported_model,
                        endpoint_kind="local",
                        base_url=base_url,
                        prompt_usd_per_mtok=row.get("prompt_usd_per_mtok", 0.0),
                        completion_usd_per_mtok=row.get("completion_usd_per_mtok", 0.0),
                        context_window=row.get("context_window"),
                        benchmark_priors=benchmark_priors,
                        p50_latency_ms=latency_ms,
                        available=True,
                    )
                )
                await self._catalog.delete_entry(vendor, model, "local")
                model = reported_model
            else:
                await self._catalog.set_availability(
                    vendor,
                    model,
                    "local",
                    available=True,
                    p50_latency_ms=latency_ms,
                )
            return ProbeResult(vendor, model, True, latency_ms)
        except Exception as exc:
            error = str(exc)
            try:
                await self._catalog.set_availability(
                    vendor,
                    model,
                    "local",
                    available=False,
                    p50_latency_ms=None,
                )
            except Exception as update_exc:
                error = f"{error}; availability update failed: {update_exc}"
            return ProbeResult(vendor, model, False, None, error)


def _single_reported_model(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return None
    model_ids = {
        str(item["id"]).strip()
        for item in payload["data"]
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    return next(iter(model_ids)) if len(model_ids) == 1 else None

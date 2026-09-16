"""Scheduled OpenRouter REST catalog refresh."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from .catalog import CatalogEntry, CatalogService

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


@dataclass(frozen=True)
class RefreshResult:
    updated: int
    refreshed_at: datetime


class OpenRouterRefresher:
    def __init__(
        self,
        catalog: CatalogService,
        *,
        api_key: str,
        client: httpx.AsyncClient | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalog = catalog
        self._api_key = api_key
        self._client = client
        self._now_fn = now_fn or (lambda: datetime.now(UTC))

    async def refresh(self) -> RefreshResult:
        if not self._api_key:
            raise ValueError("OPENROUTER_API_KEY is required for catalog refresh")
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if self._client is None:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(OPENROUTER_MODELS_URL, headers=headers)
        else:
            response = await self._client.get(OPENROUTER_MODELS_URL, headers=headers)
        response.raise_for_status()
        payload = response.json()
        raw_models = payload.get("data", [])
        if not isinstance(raw_models, list):
            raise ValueError("OpenRouter models response has no data list")

        refreshed_at = self._now_fn()
        entries = [self._entry(item, refreshed_at) for item in raw_models]
        for entry in entries:
            await self._catalog.upsert(entry)
        return RefreshResult(updated=len(entries), refreshed_at=refreshed_at)

    @staticmethod
    def _entry(item: dict[str, Any], refreshed_at: datetime) -> CatalogEntry:
        model_id = str(item["id"])
        vendor = model_id.split("/", 1)[0] if "/" in model_id else "openrouter"
        pricing = item.get("pricing") or {}
        priors = item.get("benchmark_priors") or item.get("benchmarks") or {}
        return CatalogEntry(
            vendor=vendor,
            model=model_id,
            endpoint_kind="openrouter",
            base_url="https://openrouter.ai/api/v1",
            prompt_usd_per_mtok=_per_million(pricing.get("prompt")),
            completion_usd_per_mtok=_per_million(pricing.get("completion")),
            context_window=_optional_int(item.get("context_length")),
            benchmark_priors=priors if isinstance(priors, dict) else {},
            available=True,
            refreshed_at=refreshed_at,
            stale=False,
        )


def _per_million(value: Any) -> float | None:
    return None if value is None else float(value) * 1_000_000


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)

"""Scheduled OpenRouter REST catalog refresh."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from .catalog import CatalogService

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
        entries = [
            entry for item in raw_models if (entry := self._entry(item, refreshed_at)) is not None
        ]
        for entry in entries:
            await self._catalog.upsert(entry)
        return RefreshResult(updated=len(entries), refreshed_at=refreshed_at)

    @staticmethod
    def _entry(item: Any, refreshed_at: datetime) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        raw_model_id = item.get("id")
        if not isinstance(raw_model_id, str) or not raw_model_id.strip():
            return None
        model_id = raw_model_id.strip()
        vendor = model_id.split("/", 1)[0] if "/" in model_id else "openrouter"
        entry: dict[str, Any] = {
            "vendor": vendor,
            "model": model_id,
            "endpoint_kind": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "available": True,
            "refreshed_at": refreshed_at.isoformat(),
            "stale": False,
        }
        pricing = item.get("pricing")
        if isinstance(pricing, dict):
            if "prompt" in pricing:
                entry["prompt_usd_per_mtok"] = _per_million(pricing.get("prompt"))
            if "completion" in pricing:
                entry["completion_usd_per_mtok"] = _per_million(pricing.get("completion"))
        context_window = _optional_int(item.get("context_length"))
        if context_window is not None:
            entry["context_window"] = context_window
        priors = item.get("benchmark_priors") or item.get("benchmarks")
        if isinstance(priors, dict):
            entry["benchmark_priors"] = priors
        return entry


def _per_million(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price * 1_000_000 if math.isfinite(price) and price >= 0 else None


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None

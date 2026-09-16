"""Tests for the OpenRouter catalog refresher."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from src.model_routing.refresher import OpenRouterRefresher


def _response(payload: dict, status: int = 200) -> httpx.Response:
    request = httpx.Request("GET", "https://openrouter.ai/api/v1/models")
    return httpx.Response(status, request=request, json=payload)


@pytest.mark.asyncio
async def test_refresh_updates_per_token_prices_as_per_mtok() -> None:
    catalog = AsyncMock()
    client = AsyncMock()
    client.get.return_value = _response(
        {
            "data": [
                {
                    "id": "vendor/model",
                    "context_length": 128000,
                    "pricing": {"prompt": "0.0000015", "completion": "0.000004"},
                }
            ]
        }
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)
    refresher = OpenRouterRefresher(catalog, api_key="secret", client=client, now_fn=lambda: now)

    result = await refresher.refresh()

    assert result.updated == 1
    entry = catalog.upsert.await_args.args[0]
    assert entry["prompt_usd_per_mtok"] == pytest.approx(1.5)
    assert entry["completion_usd_per_mtok"] == pytest.approx(4.0)
    assert entry["refreshed_at"] == now
    assert "p50_latency_ms" not in entry
    assert "quota_headroom_pct" not in entry
    assert "quota_reset_at" not in entry
    assert "quota_source" not in entry
    assert client.get.await_args.kwargs["headers"]["Authorization"] == "Bearer secret"


@pytest.mark.asyncio
async def test_refresh_skips_malformed_models_and_tolerates_dynamic_pricing() -> None:
    catalog = AsyncMock()
    client = AsyncMock()
    client.get.return_value = _response(
        {
            "data": [
                {"id": "vendor/fixed", "pricing": {"prompt": "0.000001"}},
                {"id": "vendor/dynamic", "pricing": {"prompt": "dynamic"}},
                {"pricing": {"prompt": "0.000002"}},
                "not-an-object",
            ]
        }
    )
    refresher = OpenRouterRefresher(catalog, api_key="secret", client=client)

    result = await refresher.refresh()

    assert result.updated == 2
    fixed, dynamic = [call.args[0] for call in catalog.upsert.await_args_list]
    assert fixed["model"] == "vendor/fixed"
    assert fixed["prompt_usd_per_mtok"] == pytest.approx(1.0)
    assert dynamic["model"] == "vendor/dynamic"
    assert dynamic["prompt_usd_per_mtok"] is None


@pytest.mark.asyncio
async def test_refresh_failure_keeps_existing_catalog_rows() -> None:
    catalog = AsyncMock()
    client = AsyncMock()
    client.get.side_effect = httpx.ConnectError("offline")
    refresher = OpenRouterRefresher(catalog, api_key="secret", client=client)

    with pytest.raises(httpx.ConnectError):
        await refresher.refresh()

    catalog.upsert.assert_not_awaited()
    catalog.set_availability.assert_not_awaited()

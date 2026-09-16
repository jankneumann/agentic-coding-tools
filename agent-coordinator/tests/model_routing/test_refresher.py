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
    assert entry.prompt_usd_per_mtok == pytest.approx(1.5)
    assert entry.completion_usd_per_mtok == pytest.approx(4.0)
    assert entry.refreshed_at == now
    assert client.get.await_args.kwargs["headers"]["Authorization"] == "Bearer secret"


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

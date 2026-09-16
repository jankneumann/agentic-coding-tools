"""Tests for local OpenAI-compatible endpoint registration and probing."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from src.model_routing.local_endpoints import LocalEndpointService


def _response(status: int = 200) -> httpx.Response:
    request = httpx.Request("GET", "http://localhost:11434/v1/models")
    return httpx.Response(status, request=request, json={"data": []})


@pytest.mark.asyncio
async def test_register_local_endpoint_seeds_zero_price_and_quality_priors() -> None:
    catalog = AsyncMock()
    service = LocalEndpointService(catalog)

    await service.register(
        {
            "vendor": "local",
            "model": "qwen",
            "base_url": "http://localhost:11434/v1",
            "benchmark_priors": {"implementer/high": 0.72},
        }
    )

    entry = catalog.upsert.await_args.args[0]
    assert entry.endpoint_kind == "local"
    assert entry.prompt_usd_per_mtok == 0.0
    assert entry.completion_usd_per_mtok == 0.0
    assert entry.benchmark_priors == {"implementer/high": 0.72}


@pytest.mark.asyncio
async def test_failed_probe_marks_local_endpoint_unavailable() -> None:
    catalog = AsyncMock()
    catalog.list_entries.return_value = [
        {
            "vendor": "local",
            "model": "qwen",
            "endpoint_kind": "local",
            "base_url": "http://localhost:11434/v1",
        }
    ]
    client = AsyncMock()
    client.get.side_effect = httpx.ConnectError("down")
    service = LocalEndpointService(catalog, client=client)

    results = await service.probe_all()

    assert results[0].available is False
    catalog.set_availability.assert_awaited_once_with(
        "local", "qwen", "local", available=False, p50_latency_ms=None
    )


@pytest.mark.asyncio
async def test_successful_probe_marks_available_and_captures_latency() -> None:
    catalog = AsyncMock()
    catalog.list_entries.return_value = [
        {
            "vendor": "local",
            "model": "qwen",
            "endpoint_kind": "local",
            "base_url": "http://localhost:11434/v1",
        }
    ]
    client = AsyncMock()
    client.get.return_value = _response()
    ticks = iter([10.0, 10.125])
    service = LocalEndpointService(catalog, client=client, time_fn=lambda: next(ticks))

    results = await service.probe_all()

    assert results[0].available is True
    assert results[0].latency_ms == pytest.approx(125.0)
    catalog.set_availability.assert_awaited_once_with(
        "local", "qwen", "local", available=True, p50_latency_ms=125.0
    )

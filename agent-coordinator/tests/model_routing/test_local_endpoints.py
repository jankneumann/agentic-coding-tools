"""Tests for local OpenAI-compatible endpoint registration and probing."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from src.model_routing.local_endpoints import LocalEndpointService


def _response(status: int = 200, *, models: list[str] | None = None) -> httpx.Response:
    request = httpx.Request("GET", "http://localhost:11434/v1/models")
    return httpx.Response(
        status,
        request=request,
        json={"data": [{"id": model} for model in models or []]},
    )


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


@pytest.mark.asyncio
async def test_agents_registry_local_endpoint_is_registered_for_probing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = SimpleNamespace(
        endpoint_kind="local",
        type="local",
        name="ollama-local",
        base_url="http://localhost:11434/v1",
        sdk=None,
    )
    monkeypatch.setattr("src.agents_config.get_agents_config", lambda: [agent])
    catalog = AsyncMock()
    service = LocalEndpointService(catalog)

    count = await service.sync_from_agents_config()

    assert count == 1
    entry = catalog.upsert.await_args.args[0]
    assert entry.vendor == "local"
    assert entry.model == "ollama-local"
    assert entry.endpoint_kind == "local"
    assert entry.base_url == "http://localhost:11434/v1"


@pytest.mark.asyncio
async def test_probe_failure_for_one_row_does_not_block_later_rows() -> None:
    catalog = AsyncMock()
    catalog.list_entries.return_value = [
        {
            "vendor": "local",
            "model": "broken",
            "endpoint_kind": "local",
            "base_url": "http://broken.test/v1",
        },
        {
            "vendor": "local",
            "model": "healthy",
            "endpoint_kind": "local",
            "base_url": "http://healthy.test/v1",
        },
    ]

    async def set_availability(_vendor, model, _kind, **_fields):
        if model == "broken":
            raise RuntimeError("catalog write failed")
        return {"model": model}

    catalog.set_availability.side_effect = set_availability
    client = AsyncMock()
    client.get.return_value = _response()
    service = LocalEndpointService(catalog, client=client)

    results = await service.probe_all()

    assert [result.model for result in results] == ["broken", "healthy"]
    assert results[0].available is False
    assert "catalog write failed" in (results[0].error or "")
    assert results[1].available is True
    assert client.get.await_count == 2


@pytest.mark.asyncio
async def test_probe_replaces_endpoint_placeholder_with_single_reported_model() -> None:
    catalog = AsyncMock()
    catalog.list_entries.return_value = [
        {
            "vendor": "local",
            "model": "ollama-local",
            "endpoint_kind": "local",
            "base_url": "http://localhost:11434/v1",
            "prompt_usd_per_mtok": 0.0,
            "completion_usd_per_mtok": 0.0,
            "benchmark_priors": {},
        }
    ]
    client = AsyncMock()
    client.get.return_value = _response(models=["qwen3-coder:30b"])
    service = LocalEndpointService(catalog, client=client)

    [result] = await service.probe_all()

    discovered = catalog.upsert.await_args.args[0]
    assert discovered.model == "qwen3-coder:30b"
    assert discovered.base_url == "http://localhost:11434/v1"
    catalog.set_availability.assert_awaited_once_with(
        "local",
        "ollama-local",
        "local",
        available=False,
        p50_latency_ms=None,
    )
    catalog.delete_entry.assert_not_awaited()
    assert result.model == "qwen3-coder:30b"
    assert result.available is True


@pytest.mark.asyncio
async def test_config_sync_keeps_discovered_model_for_known_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = SimpleNamespace(
        endpoint_kind="local",
        type="local",
        name="ollama-local",
        base_url="http://localhost:11434/v1",
        sdk=None,
    )
    monkeypatch.setattr("src.agents_config.get_agents_config", lambda: [agent])
    catalog = AsyncMock()
    catalog.list_entries.return_value = [
        {
            "vendor": "local",
            "model": "qwen3-coder:30b",
            "endpoint_kind": "local",
            "base_url": "http://localhost:11434/v1",
        }
    ]

    count = await LocalEndpointService(catalog).sync_from_agents_config()

    assert count == 0
    catalog.upsert.assert_not_awaited()

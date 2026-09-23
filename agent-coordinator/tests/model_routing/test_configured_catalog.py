"""Configured catalog bootstrap tests for exact DG-04 identities."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agents_config import AgentEntry, CliConfig, ModeConfig
from src.model_routing.configured_catalog import ConfiguredCatalogSync


@pytest.mark.asyncio
async def test_sync_inserts_only_missing_explicit_catalog_identity() -> None:
    agent = AgentEntry(
        name="codex-local",
        type="codex",
        profile="codex_local",
        trust_level=3,
        transport="mcp",
        capabilities=["queue"],
        description="test",
        catalog_vendor="codex",
        endpoint_kind="vendor-cli",
        location="local",
        cli=CliConfig(
            command="codex",
            dispatch_modes={"quick": ModeConfig(args=[])},
            model_flag="-m",
        ),
    )
    catalog = AsyncMock()
    catalog.list_entries.return_value = []

    result = await ConfiguredCatalogSync(
        catalog=catalog,
        agents=[agent],
        provider_model_map={"providers": {"codex": {"standard": "gpt-5.6-terra"}}},
    ).sync()

    assert result.inserted == 1
    catalog.upsert.assert_awaited_once()
    payload = catalog.upsert.await_args.args[0]
    assert payload.vendor == "codex"
    assert payload.model == "gpt-5.6-terra"
    assert payload.endpoint_kind == "vendor-cli"
    assert payload.base_url is None


@pytest.mark.asyncio
async def test_sync_never_overwrites_an_existing_exact_identity() -> None:
    agent = AgentEntry(
        name="codex-local",
        type="codex",
        profile="codex_local",
        trust_level=3,
        transport="mcp",
        capabilities=["queue"],
        description="test",
        catalog_vendor="codex",
        endpoint_kind="vendor-cli",
        cli=CliConfig(
            command="codex",
            dispatch_modes={"quick": ModeConfig(args=[])},
            model_flag="-m",
        ),
    )
    catalog = AsyncMock()
    catalog.list_entries.return_value = [
        {
            "vendor": "codex",
            "model": "gpt-5.6-terra",
            "endpoint_kind": "vendor-cli",
            "base_url": None,
            "prompt_usd_per_mtok": 99,
            "available": False,
        }
    ]

    result = await ConfiguredCatalogSync(
        catalog=catalog,
        agents=[agent],
        provider_model_map={"providers": {"codex": {"standard": "gpt-5.6-terra"}}},
    ).sync()

    assert result.inserted == 0
    assert result.existing == 1
    catalog.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_never_overwrites_same_triple_with_different_base_url() -> None:
    agent = AgentEntry(
        name="codex-local",
        type="codex",
        profile="codex_local",
        trust_level=3,
        transport="mcp",
        capabilities=["queue"],
        description="test",
        catalog_vendor="codex",
        endpoint_kind="vendor-cli",
        base_url="https://configured.example/v1",
        cli=CliConfig(
            command="codex",
            dispatch_modes={"quick": ModeConfig(args=[])},
            model_flag="-m",
        ),
    )
    catalog = AsyncMock()
    catalog.list_entries.return_value = [
        {
            "vendor": "codex",
            "model": "gpt-5.6-terra",
            "endpoint_kind": "vendor-cli",
            "base_url": "https://existing.example/v1",
            "prompt_usd_per_mtok": 99,
        }
    ]

    result = await ConfiguredCatalogSync(
        catalog=catalog,
        agents=[agent],
        provider_model_map={"providers": {"codex": {"standard": "gpt-5.6-terra"}}},
    ).sync()

    assert result.inserted == 0
    assert result.skipped == 1
    catalog.upsert.assert_not_awaited()

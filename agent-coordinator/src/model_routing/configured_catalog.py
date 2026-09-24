"""Materialize missing catalog identities from explicit configured lanes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..agents_config import AgentEntry, get_agents_config, get_provider_model_map
from .catalog import CatalogEntry, CatalogService, get_catalog_service


@dataclass(frozen=True, slots=True)
class ConfiguredCatalogSyncResult:
    inserted: int
    existing: int
    skipped: int


class ConfiguredCatalogSync:
    def __init__(
        self,
        *,
        catalog: CatalogService | None = None,
        agents: Sequence[AgentEntry] | None = None,
        provider_model_map: Mapping[str, Any] | None = None,
    ) -> None:
        self._catalog = catalog or get_catalog_service()
        self._agents = list(agents) if agents is not None else list(get_agents_config())
        self._provider_model_map = provider_model_map or get_provider_model_map()

    async def sync(self) -> ConfiguredCatalogSyncResult:
        existing_rows = await self._catalog.list_entries()
        existing_keys = {
            (
                str(row.get("vendor") or ""),
                str(row.get("model") or ""),
                str(row.get("endpoint_kind") or ""),
                row.get("base_url"),
            )
            for row in existing_rows
        }
        occupied_triples = {key[:3] for key in existing_keys}
        inserted = 0
        existing = 0
        skipped = 0
        for agent in self._agents:
            if agent.endpoint_kind not in {"vendor-cli", "vendor-sdk"} or not agent.catalog_vendor:
                skipped += 1
                continue
            models = self._models(agent)
            if not models:
                skipped += 1
                continue
            for model in models:
                key = (agent.catalog_vendor, model, agent.endpoint_kind, agent.base_url)
                if key in existing_keys:
                    existing += 1
                    continue
                if key[:3] in occupied_triples:
                    skipped += 1
                    continue
                await self._catalog.upsert(
                    CatalogEntry(
                        vendor=agent.catalog_vendor,
                        model=model,
                        endpoint_kind=agent.endpoint_kind,
                        base_url=agent.base_url,
                        available=True,
                        stale=False,
                    )
                )
                existing_keys.add(key)
                occupied_triples.add(key[:3])
                inserted += 1
        return ConfiguredCatalogSyncResult(inserted, existing, skipped)

    def _models(self, agent: AgentEntry) -> list[str]:
        if agent.endpoint_kind == "vendor-sdk":
            if agent.sdk is None:
                return []
            return sorted({agent.sdk.model, *agent.sdk.model_fallbacks})
        providers = self._provider_model_map.get("providers", self._provider_model_map)
        if not isinstance(providers, Mapping):
            return []
        provider = providers.get(agent.type)
        if not isinstance(provider, Mapping):
            return []
        models: set[str] = set()
        for value in provider.values():
            if isinstance(value, str):
                models.add(value)
            elif isinstance(value, Mapping) and isinstance(value.get("model"), str):
                models.add(str(value["model"]))
        return sorted(models)

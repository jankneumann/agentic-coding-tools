"""Tests for the storage-only model catalog service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.model_routing.catalog import CatalogEntry, CatalogService


def _db(rows: list[dict] | None = None) -> AsyncMock:
    db = AsyncMock()
    db.query = AsyncMock(return_value=rows or [])
    db.insert = AsyncMock(side_effect=lambda _table, data: {"id": 1, **data})
    db.update = AsyncMock(side_effect=lambda _table, _match, data: [{"id": 1, **data}])
    db.delete = AsyncMock(return_value=None)
    return db


@pytest.mark.asyncio
async def test_catalog_read_uses_storage_only_and_derives_staleness() -> None:
    refreshed = datetime(2026, 1, 1, tzinfo=UTC)
    db = _db(
        [
            {
                "id": 1,
                "vendor": "openrouter",
                "model": "m",
                "endpoint_kind": "openrouter",
                "refreshed_at": refreshed.isoformat(),
                "available": True,
            }
        ]
    )
    external_client = AsyncMock()
    service = CatalogService(
        db,
        stale_after=timedelta(hours=6),
        now_fn=lambda: refreshed + timedelta(hours=7),
    )

    rows = await service.list_entries()

    assert rows[0]["stale"] is True
    db.query.assert_awaited_once_with("model_catalog", "order=vendor.asc")
    external_client.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_catalog_upsert_updates_existing_row() -> None:
    db = _db([{"id": 7, "vendor": "openrouter", "model": "m", "endpoint_kind": "openrouter"}])
    service = CatalogService(db)
    entry = CatalogEntry(
        vendor="openrouter",
        model="m",
        endpoint_kind="openrouter",
        prompt_usd_per_mtok=1.25,
    )

    row = await service.upsert(entry)

    db.insert.assert_not_awaited()
    db.update.assert_awaited_once()
    assert row["prompt_usd_per_mtok"] == 1.25


@pytest.mark.asyncio
async def test_list_candidates_maps_catalog_and_task_posterior() -> None:
    catalog_row = {
        "id": 11,
        "vendor": "openrouter",
        "model": "m",
        "endpoint_kind": "openrouter",
        "available": True,
        "benchmark_priors": {"implementer/high": 0.8},
        "prompt_usd_per_mtok": 1.0,
        "completion_usd_per_mtok": 2.0,
    }
    posterior_rows = [
        {"metric": "quality", "value": 0.9, "sample_size": 8},
        {"metric": "success_rate", "value": 0.75, "sample_size": 8},
        {"metric": "cost_usd", "value": 0.4, "sample_size": 8},
    ]
    db = _db()
    db.query = AsyncMock(side_effect=[[catalog_row], posterior_rows])

    candidates = await CatalogService(db).list_candidates("implementer/high")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.benchmark_prior == 0.8
    assert candidate.posterior.quality == 0.9
    assert candidate.posterior.cost_per_task_usd == 0.4
    assert candidate.posterior.sample_size == 8
    assert candidate.available is True


@pytest.mark.asyncio
async def test_decision_round_trip_uses_routing_decisions_storage() -> None:
    db = _db()
    db.insert = AsyncMock(side_effect=lambda _table, data: {"decision_id": "d-1", **data})
    service = CatalogService(db)

    decision = {
        "request": {"task_type": "implementer/high"},
        "selected": {"model": "m"},
        "alternatives": [],
        "excluded": [],
        "exploration": False,
        "fallback": False,
        "policy_version": "v1",
        "budget_state": {},
    }
    created = await service.record_decision(decision)
    db.query.return_value = [created]

    loaded = await service.get_decision("d-1")

    assert loaded == created
    db.insert.assert_awaited_once_with(
        "routing_decisions",
        decision,
    )


@pytest.mark.asyncio
async def test_catalog_upsert_inserts_missing_row() -> None:
    db = _db()
    service = CatalogService(db)
    entry = CatalogEntry(
        vendor="local",
        model="qwen3-coder",
        endpoint_kind="local",
        base_url="http://localhost:11434/v1",
    )

    row = await service.upsert(entry)

    db.insert.assert_awaited_once()
    table, payload = db.insert.await_args.args
    assert table == "model_catalog"
    assert payload["vendor"] == "local"
    assert payload["model"] == "qwen3-coder"
    assert payload["endpoint_kind"] == "local"
    db.update.assert_not_awaited()
    assert row["model"] == "qwen3-coder"


@pytest.mark.asyncio
async def test_catalog_delete_removes_existing_row() -> None:
    db = _db(
        [
            {
                "id": 9,
                "vendor": "local",
                "model": "qwen3-coder",
                "endpoint_kind": "local",
            }
        ]
    )
    service = CatalogService(db)

    await service.delete_entry("local", "qwen3-coder", "local")

    db.delete.assert_awaited_once_with("model_catalog", {"id": 9})

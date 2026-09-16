"""Tests for actual and counterfactual routing spend accounting."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.model_routing.ledger import LedgerService, UsageRecord


def _db(rows: list[dict] | None = None) -> AsyncMock:
    db = AsyncMock()
    db.query = AsyncMock(return_value=rows or [])
    db.insert = AsyncMock(side_effect=lambda _table, data: {"id": 1, **data})
    db.update = AsyncMock(return_value=[])
    return db


@pytest.mark.asyncio
async def test_record_computes_actual_and_metered_counterfactual() -> None:
    db = _db()
    ledger = LedgerService(db)
    record = UsageRecord(
        vendor="claude",
        model="sonnet",
        endpoint_kind="vendor-cli",
        prompt_tokens=1_000_000,
        completion_tokens=500_000,
        actual_prompt_usd_per_mtok=0.0,
        actual_completion_usd_per_mtok=0.0,
        baseline_prompt_usd_per_mtok=3.0,
        baseline_completion_usd_per_mtok=15.0,
    )

    row = await ledger.record(record)

    assert row["actual_usd"] == pytest.approx(0.0)
    assert row["counterfactual_usd"] == pytest.approx(10.5)
    assert row["tokens_estimated"] is False


@pytest.mark.asyncio
async def test_usage_summary_can_exclude_estimated_entries() -> None:
    db = _db(
        [
            {
                "actual_usd": 1.0,
                "counterfactual_usd": 4.0,
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "tokens_estimated": False,
            },
            {
                "actual_usd": 2.0,
                "counterfactual_usd": 6.0,
                "prompt_tokens": 20,
                "completion_tokens": 8,
                "tokens_estimated": True,
            },
        ]
    )
    ledger = LedgerService(db)

    exact = await ledger.usage_summary(include_estimated=False)
    all_entries = await ledger.usage_summary(include_estimated=True)

    assert exact["actual_usd"] == pytest.approx(1.0)
    assert exact["savings_usd"] == pytest.approx(3.0)
    assert all_entries["actual_usd"] == pytest.approx(3.0)
    assert all_entries["savings_usd"] == pytest.approx(7.0)
    assert all_entries["verified_savings_usd"] == pytest.approx(3.0)
    assert all_entries["estimated_entries"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("window", "expected_start", "expected_end"),
    [
        (
            "day",
            "2026-09-16T00:00:00+00:00",
            "2026-09-16T23:59:59.999999+00:00",
        ),
        (
            "week",
            "2026-09-14T00:00:00+00:00",
            "2026-09-20T23:59:59.999999+00:00",
        ),
        (
            "month",
            "2026-09-01T00:00:00+00:00",
            "2026-09-30T23:59:59.999999+00:00",
        ),
    ],
)
async def test_usage_summary_queries_requested_calendar_window(
    window: str, expected_start: str, expected_end: str
) -> None:
    db = _db()
    ledger = LedgerService(
        db,
        now_fn=lambda: datetime(2026, 9, 16, 14, 30, tzinfo=UTC),
    )

    summary = await ledger.usage_summary(window=window)

    assert summary["window"] == window
    db.query.assert_awaited_once_with(
        "routing_spend_ledger",
        f"occurred_at=gte.{expected_start}&occurred_at=lte.{expected_end}",
    )


@pytest.mark.asyncio
async def test_reconcile_generation_replaces_estimated_openrouter_cost() -> None:
    db = _db()
    db.update.return_value = [{"id": 1, "actual_usd": 0.42, "tokens_estimated": False}]

    rows = await LedgerService(db).reconcile_generation("gen-1", actual_usd=0.42)

    assert rows[0]["actual_usd"] == pytest.approx(0.42)
    db.update.assert_awaited_once_with(
        "routing_spend_ledger",
        {"generation_id": "gen-1"},
        {"actual_usd": 0.42, "tokens_estimated": False},
    )

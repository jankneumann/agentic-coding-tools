"""Actual and metered-counterfactual spend accounting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ..db import DatabaseClient, get_db


@dataclass(frozen=True)
class UsageRecord:
    vendor: str
    model: str
    endpoint_kind: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    tokens_estimated: bool = False
    actual_usd: float | None = None
    counterfactual_usd: float | None = None
    actual_prompt_usd_per_mtok: float | None = None
    actual_completion_usd_per_mtok: float | None = None
    baseline_prompt_usd_per_mtok: float | None = None
    baseline_completion_usd_per_mtok: float | None = None
    decision_id: str | None = None
    exploration: bool = False
    generation_id: str | None = None
    work_unit_ref: str | None = None
    occurred_at: str | datetime | None = None


class LedgerService:
    def __init__(self, db: DatabaseClient | None = None) -> None:
        self._db = db

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def record(self, record: UsageRecord | dict[str, Any]) -> dict[str, Any]:
        values = asdict(record) if isinstance(record, UsageRecord) else dict(record)
        prompt_tokens = int(values.get("prompt_tokens") or 0)
        completion_tokens = int(values.get("completion_tokens") or 0)
        actual = values.get("actual_usd")
        if actual is None:
            actual = _token_cost(
                prompt_tokens,
                completion_tokens,
                values.get("actual_prompt_usd_per_mtok"),
                values.get("actual_completion_usd_per_mtok"),
            )
        counterfactual = values.get("counterfactual_usd")
        if counterfactual is None:
            counterfactual = _token_cost(
                prompt_tokens,
                completion_tokens,
                values.get("baseline_prompt_usd_per_mtok"),
                values.get("baseline_completion_usd_per_mtok"),
            )
        rate_fields = {
            "actual_prompt_usd_per_mtok",
            "actual_completion_usd_per_mtok",
            "baseline_prompt_usd_per_mtok",
            "baseline_completion_usd_per_mtok",
        }
        row = {
            key: value
            for key, value in values.items()
            if key not in rate_fields and value is not None
        }
        row["actual_usd"] = round(float(actual), 6)
        row["counterfactual_usd"] = round(float(counterfactual), 6)
        if isinstance(row.get("occurred_at"), datetime):
            row["occurred_at"] = row["occurred_at"].isoformat()
        return await self.db.insert("routing_spend_ledger", row)

    async def usage_summary(
        self,
        *,
        include_estimated: bool = True,
        month: date | None = None,
    ) -> dict[str, Any]:
        month = month or datetime.now(UTC).date().replace(day=1)
        start = datetime(month.year, month.month, 1, tzinfo=UTC)
        if month.month == 12:
            end = datetime(month.year + 1, 1, 1, tzinfo=UTC)
        else:
            end = datetime(month.year, month.month + 1, 1, tzinfo=UTC)
        inclusive_end = end - timedelta(microseconds=1)
        rows = await self.db.query(
            "routing_spend_ledger",
            f"occurred_at=gte.{start.isoformat()}&occurred_at=lte.{inclusive_end.isoformat()}",
        )
        selected = (
            rows if include_estimated else [row for row in rows if not row.get("tokens_estimated")]
        )
        actual = sum(float(row.get("actual_usd") or 0.0) for row in selected)
        counterfactual = sum(float(row.get("counterfactual_usd") or 0.0) for row in selected)
        return {
            "month": start.date().isoformat(),
            "actual_usd": actual,
            "counterfactual_usd": counterfactual,
            "savings_usd": counterfactual - actual,
            "prompt_tokens": sum(int(row.get("prompt_tokens") or 0) for row in selected),
            "completion_tokens": sum(int(row.get("completion_tokens") or 0) for row in selected),
            "entries": len(selected),
            "estimated_entries": sum(bool(row.get("tokens_estimated")) for row in selected),
            "includes_estimates": include_estimated,
        }

    async def rollup_current_month(self) -> dict[str, Any]:
        return await self.usage_summary()

    async def reconcile_generation(
        self, generation_id: str, *, actual_usd: float
    ) -> list[dict[str, Any]]:
        return await self.db.update(
            "routing_spend_ledger",
            {"generation_id": generation_id},
            {"actual_usd": actual_usd, "tokens_estimated": False},
        )


def _token_cost(
    prompt_tokens: int,
    completion_tokens: int,
    prompt_rate: Any,
    completion_rate: Any,
) -> float:
    return (
        prompt_tokens * float(prompt_rate or 0.0)
        + completion_tokens * float(completion_rate or 0.0)
    ) / 1_000_000


_routing_ledger: LedgerService | None = None


def get_routing_ledger(db: DatabaseClient | None = None) -> LedgerService:
    global _routing_ledger
    if db is not None:
        return LedgerService(db)
    if _routing_ledger is None:
        _routing_ledger = LedgerService()
    return _routing_ledger


def reset_routing_ledger() -> None:
    global _routing_ledger
    _routing_ledger = None

"""Database-backed model catalog and routing decision store.

Catalog reads deliberately use only :class:`DatabaseClient`; network refreshes
live in ``refresher.py`` and local health probes in ``local_endpoints.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ..db import DatabaseClient, get_db
from .resolver import CandidateInput, Posterior

DEFAULT_STALE_AFTER = timedelta(hours=12)


def encode_filter_value(value: Any) -> str:
    """Escape delimiters before interpolating a value into a DB filter string."""
    return (
        str(value).replace("%", "%25").replace("&", "%26").replace("#", "%23").replace("+", "%2B")
    )


@dataclass(frozen=True)
class CatalogEntry:
    vendor: str
    model: str
    endpoint_kind: str
    base_url: str | None = None
    prompt_usd_per_mtok: float | None = None
    completion_usd_per_mtok: float | None = None
    context_window: int | None = None
    benchmark_priors: dict[str, float] = field(default_factory=dict)
    p50_latency_ms: float | None = None
    available: bool = True
    quota_headroom_pct: float | None = None
    quota_reset_at: str | datetime | None = None
    quota_source: str | None = None
    refreshed_at: str | datetime | None = None
    stale: bool = False

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        if row["refreshed_at"] is None:
            row["refreshed_at"] = datetime.now(UTC).isoformat()
        elif isinstance(row["refreshed_at"], datetime):
            row["refreshed_at"] = row["refreshed_at"].isoformat()
        if isinstance(row["quota_reset_at"], datetime):
            row["quota_reset_at"] = row["quota_reset_at"].isoformat()
        return row


class CatalogService:
    """Storage-only access to catalog, posterior, and decision rows."""

    def __init__(
        self,
        db: DatabaseClient | None = None,
        *,
        stale_after: timedelta = DEFAULT_STALE_AFTER,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._db = db
        self._stale_after = stale_after
        self._now_fn = now_fn or (lambda: datetime.now(UTC))

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def list_entries(
        self,
        endpoint_kind: str | None = None,
        include_unavailable: bool = True,
    ) -> list[dict[str, Any]]:
        filters: list[str] = []
        if endpoint_kind:
            filters.append(f"endpoint_kind=eq.{encode_filter_value(endpoint_kind)}")
        if not include_unavailable:
            filters.append("available=eq.true")
        filters.append("order=vendor.asc")
        rows = await self.db.query("model_catalog", "&".join(filters))
        return [self._with_derived_staleness(row) for row in rows]

    async def get_entry(self, vendor: str, model: str, endpoint_kind: str) -> dict[str, Any] | None:
        rows = await self.db.query(
            "model_catalog",
            f"vendor=eq.{encode_filter_value(vendor)}"
            f"&model=eq.{encode_filter_value(model)}"
            f"&endpoint_kind=eq.{encode_filter_value(endpoint_kind)}&limit=1",
        )
        return self._with_derived_staleness(rows[0]) if rows else None

    async def upsert(self, entry: CatalogEntry | Mapping[str, Any]) -> dict[str, Any]:
        data = entry.to_row() if isinstance(entry, CatalogEntry) else dict(entry)
        key = {
            "vendor": data["vendor"],
            "model": data["model"],
            "endpoint_kind": data["endpoint_kind"],
        }
        existing = await self.get_entry(**key)
        if existing is None:
            return await self.db.insert("model_catalog", data)
        updated = await self.db.update("model_catalog", {"id": existing["id"]}, data)
        return updated[0] if updated else {**existing, **data}

    async def delete_entry(self, vendor: str, model: str, endpoint_kind: str) -> None:
        existing = await self.get_entry(vendor, model, endpoint_kind)
        if existing:
            await self.db.delete("model_catalog", {"id": existing["id"]})

    async def set_availability(
        self,
        vendor: str,
        model: str,
        endpoint_kind: str,
        *,
        available: bool,
        p50_latency_ms: float | None = None,
    ) -> dict[str, Any] | None:
        existing = await self.get_entry(vendor, model, endpoint_kind)
        if existing is None:
            return None
        data: dict[str, Any] = {
            "available": available,
            "refreshed_at": self._now_fn().isoformat(),
            "stale": False,
        }
        if p50_latency_ms is not None:
            data["p50_latency_ms"] = p50_latency_ms
        rows = await self.db.update("model_catalog", {"id": existing["id"]}, data)
        return rows[0] if rows else {**existing, **data}

    async def list_candidates(self, task_type: str) -> list[CandidateInput]:
        candidates: list[CandidateInput] = []
        for row in await self.list_entries(include_unavailable=False):
            post_rows = await self.db.query(
                "model_posteriors",
                f"catalog_id=eq.{encode_filter_value(row['id'])}"
                f"&task_type=eq.{encode_filter_value(task_type)}",
            )
            metrics = {str(item["metric"]): item for item in post_rows}
            sample_size = max(
                (float(item.get("sample_size") or 0.0) for item in post_rows),
                default=0.0,
            )
            priors = row.get("benchmark_priors") or {}
            if isinstance(priors, str):
                priors = {}
            cost = metrics.get("cost_per_task_usd") or metrics.get("cost_usd")
            latency = metrics.get("latency_seconds") or metrics.get("latency_s")
            candidates.append(
                CandidateInput(
                    vendor=str(row["vendor"]),
                    model=str(row["model"]),
                    endpoint_kind=str(row["endpoint_kind"]),
                    benchmark_prior=float(priors.get(task_type, priors.get("default", 0.0))),
                    prompt_usd_per_mtok=_optional_float(row.get("prompt_usd_per_mtok")),
                    completion_usd_per_mtok=_optional_float(row.get("completion_usd_per_mtok")),
                    p50_latency_ms=_optional_float(row.get("p50_latency_ms")),
                    quota_headroom_pct=_optional_float(row.get("quota_headroom_pct")),
                    # Stale rows remain routable when refresh is unavailable;
                    # callers retain the catalog row's stale provenance.
                    available=bool(row.get("available", True)),
                    stale_catalog=bool(row.get("stale", False)),
                    posterior=Posterior(
                        quality=_metric_value(metrics, "quality"),
                        cost_per_task_usd=_optional_float(cost.get("value")) if cost else None,
                        success_rate=_metric_value(metrics, "success_rate"),
                        latency_seconds=_optional_float(latency.get("value")) if latency else None,
                        sample_size=sample_size,
                    ),
                )
            )
        return candidates

    async def record_decision(
        self,
        decision: dict[str, Any] | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        data = dict(decision or fields)
        return await self.db.insert("routing_decisions", data)

    async def get_decision(self, decision_id: str) -> dict[str, Any] | None:
        rows = await self.db.query(
            "routing_decisions",
            f"decision_id=eq.{encode_filter_value(decision_id)}&limit=1",
        )
        return rows[0] if rows else None

    def _with_derived_staleness(self, row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        refreshed = _as_datetime(result.get("refreshed_at"))
        age_stale = refreshed is None or self._now_fn() - refreshed > self._stale_after
        result["stale"] = bool(result.get("stale")) or age_stale
        return result


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _metric_value(metrics: dict[str, dict[str, Any]], name: str) -> float | None:
    item = metrics.get(name)
    return _optional_float(item.get("value")) if item else None


_catalog_service: CatalogService | None = None


def get_catalog_service(db: DatabaseClient | None = None) -> CatalogService:
    global _catalog_service
    if db is not None:
        return CatalogService(db)
    if _catalog_service is None:
        _catalog_service = CatalogService()
    return _catalog_service


def reset_catalog_service() -> None:
    global _catalog_service
    _catalog_service = None

"""Contract tests for ``POST /routing/spend`` (openrouter-review-lane, task 4.1).

The route writes one ``routing_spend_ledger`` row per metered review through
``LedgerService.record``; ``generation_id`` is the idempotency key.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from src.config import reset_config
from src.coordination_api import create_coordination_api
from src.model_routing.api import RoutingService
from src.model_routing.ledger import LedgerService

_TEST_KEY = "spend-route-test-key"


class _MemoryDb:
    """In-memory ``routing_spend_ledger`` honouring the ``generation_id=eq.`` filter."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def query(
        self, table: str, query_params: str | None = None, select: str = "*"
    ) -> list[dict[str, Any]]:
        assert table == "routing_spend_ledger"
        rows = list(self.rows)
        for clause in (query_params or "").split("&"):
            key, _, expr = clause.partition("=")
            if key == "generation_id" and expr.startswith("eq."):
                wanted = unquote(expr[3:])
                rows = [row for row in rows if row.get("generation_id") == wanted]
        return rows

    async def insert(
        self, table: str, data: dict[str, Any], return_data: bool = True
    ) -> dict[str, Any]:
        assert table == "routing_spend_ledger"
        row = {"id": len(self.rows) + 1, **data}
        row.setdefault("occurred_at", datetime.now(UTC).isoformat())
        self.rows.append(row)
        return row


@pytest.fixture()
def memory_db() -> _MemoryDb:
    return _MemoryDb()


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, memory_db: _MemoryDb) -> Iterator[TestClient]:
    reset_config()
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("COORDINATION_API_KEYS", _TEST_KEY)
    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")
    monkeypatch.setenv("ROUTING_MONTHLY_CEILING_USD", "10")
    reset_config()
    service = RoutingService(catalog=AsyncMock(), ledger=LedgerService(memory_db))
    with patch("src.model_routing.api.get_routing_service", return_value=service):
        yield TestClient(create_coordination_api())
    reset_config()


def _headers() -> dict[str, str]:
    return {"X-API-Key": _TEST_KEY}


def _body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "vendor": "openrouter",
        "model": "openai/gpt-5",
        "endpoint_kind": "openrouter",
        "generation_id": "gen-abc",
        "prompt_tokens": 1200,
        "completion_tokens": 300,
        "actual_usd": 0.0042,
        "tokens_estimated": False,
        "work_unit_ref": "openrouter-review-lane:VAL_REVIEW:round-2",
    }
    body.update(overrides)
    return body


def test_spend_route_is_registered(client: TestClient) -> None:
    paths = {
        (method, route.path)
        for route in client.app.routes
        if hasattr(route, "methods")
        for method in route.methods
    }
    assert ("POST", "/routing/spend") in paths


def test_insert_returns_201_and_writes_one_row(
    client: TestClient, memory_db: _MemoryDb
) -> None:
    response = client.post("/routing/spend", headers=_headers(), json=_body())

    assert response.status_code == 201
    payload = response.json()
    assert payload["generation_id"] == "gen-abc"
    assert payload["actual_usd"] == pytest.approx(0.0042)
    assert len(memory_db.rows) == 1
    row = memory_db.rows[0]
    assert row["vendor"] == "openrouter"
    assert row["endpoint_kind"] == "openrouter"
    assert row["tokens_estimated"] is False
    assert row["work_unit_ref"] == "openrouter-review-lane:VAL_REVIEW:round-2"


def test_duplicate_generation_id_returns_200_without_second_row(
    client: TestClient, memory_db: _MemoryDb
) -> None:
    first = client.post("/routing/spend", headers=_headers(), json=_body())
    second = client.post("/routing/spend", headers=_headers(), json=_body())

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert [row["generation_id"] for row in memory_db.rows] == ["gen-abc"]


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-API-Key": "wrong-key"}],
    ids=["missing", "invalid"],
)
def test_unauthenticated_write_is_rejected(
    client: TestClient, memory_db: _MemoryDb, headers: dict[str, str]
) -> None:
    response = client.post("/routing/spend", headers=headers, json=_body())

    assert response.status_code == 401
    assert memory_db.rows == []


@pytest.mark.parametrize(
    "body",
    [
        _body(actual_usd=-1),
        _body(api_key="sk-should-never-be-accepted"),
        _body(prompt_tokens=-5),
        {key: value for key, value in _body().items() if key != "generation_id"},
    ],
    ids=["negative-actual-usd", "unknown-field", "negative-tokens", "missing-generation-id"],
)
def test_invalid_spend_is_rejected_with_422(
    client: TestClient, memory_db: _MemoryDb, body: dict[str, Any]
) -> None:
    response = client.post("/routing/spend", headers=_headers(), json=body)

    assert response.status_code == 422
    assert memory_db.rows == []


def test_usage_reflects_recorded_review_row(client: TestClient) -> None:
    before = client.get("/routing/usage?window=month", headers=_headers())
    assert before.status_code == 200
    used_before = before.json()["metered_usd_used"]

    posted = client.post("/routing/spend", headers=_headers(), json=_body())
    assert posted.status_code == 201

    after = client.get("/routing/usage?window=month", headers=_headers())
    assert after.status_code == 200
    assert after.json()["metered_usd_used"] == pytest.approx(used_before + 0.0042)


@pytest.mark.asyncio
async def test_find_by_generation_id_returns_row_or_none(memory_db: _MemoryDb) -> None:
    ledger = LedgerService(memory_db)
    assert await ledger.find_by_generation_id("gen-x&y") is None

    await ledger.record(
        {
            "vendor": "openrouter",
            "model": "openai/gpt-5",
            "endpoint_kind": "openrouter",
            "generation_id": "gen-x&y",
            "actual_usd": 0.01,
        }
    )

    found = await ledger.find_by_generation_id("gen-x&y")
    assert found is not None
    assert found["generation_id"] == "gen-x&y"
    assert await ledger.find_by_generation_id("gen-other") is None

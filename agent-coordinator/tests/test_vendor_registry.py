"""Focused tests for configured vendor-registry aggregation and state writes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.agents_config import AgentEntry, CliConfig, ModeConfig
from src.vendor_registry import ObservationConflictError, VendorRegistryService

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def _agent(
    name: str = "codex-local",
    *,
    location: str = "local",
    endpoint_kind: str = "vendor-cli",
    model: str = "gpt-5.6",
) -> AgentEntry:
    return AgentEntry(
        name=name,
        type="codex",
        profile=name.replace("-", "_"),
        trust_level=3,
        transport="mcp",
        capabilities=["queue", "vendor_limit_reporter"],
        description="test",
        location=location,
        policy_vendor="codex",
        catalog_vendor=None,
        endpoint_kind=endpoint_kind,
        cli=CliConfig(
            command="codex",
            dispatch_modes={"review": ModeConfig(args=[])},
            model_flag="-m",
            model=model,
        ),
    )


def _db(rows: dict[str, list[dict]] | None = None) -> AsyncMock:
    db = AsyncMock()

    async def query(table: str, *_args, **_kwargs):
        return list((rows or {}).get(table, []))

    db.query = AsyncMock(side_effect=query)
    db.rpc = AsyncMock(return_value=[])
    return db


def test_agent_entry_exposes_typed_lane_identity() -> None:
    agent = _agent()

    assert agent.location == "local"
    assert agent.policy_vendor == "codex"
    assert agent.catalog_vendor is None


@pytest.mark.asyncio
async def test_list_vendors_batches_sources_and_applies_conjunctive_filters() -> None:
    db = _db(
        {
            "vendor_probe_state": [
                {
                    "agent_id": "codex-local",
                    "status": "available",
                    "source_agent_id": "watchdog",
                    "reason": None,
                    "observed_at": (NOW - timedelta(seconds=10)).isoformat(),
                    "stale_after": (NOW + timedelta(seconds=10)).isoformat(),
                }
            ],
            "vendor_rate_limits": [],
            "model_catalog": [
                {
                    "vendor": "codex",
                    "model": "gpt-5.6",
                    "endpoint_kind": "vendor-cli",
                    "base_url": None,
                    "prompt_usd_per_mtok": 2.0,
                    "completion_usd_per_mtok": 8.0,
                    "refreshed_at": NOW.isoformat(),
                    "available": True,
                    "stale": False,
                }
            ],
        }
    )
    service = VendorRegistryService(
        db,
        agents=[_agent(), _agent("codex-cloud", location="cloud")],
        now_fn=lambda: NOW,
    )

    lanes = await service.list_vendors(
        capability="queue",
        archetype=None,
        dispatch_mode="review",
        location="local",
        available_only=True,
    )

    assert [lane["agent_id"] for lane in lanes] == ["codex-local"]
    assert lanes[0]["availability"]["status"] == "available"
    assert lanes[0]["cost"]["known"] is True
    assert len(db.query.await_args_list) == 3


@pytest.mark.asyncio
async def test_lane_limit_precedes_probe_and_expires_at_exact_reset() -> None:
    probe = {
        "agent_id": "codex-local",
        "status": "available",
        "source_agent_id": "watchdog",
        "reason": None,
        "observed_at": (NOW - timedelta(seconds=10)).isoformat(),
        "stale_after": (NOW + timedelta(seconds=10)).isoformat(),
    }
    limit = {
        "observation_id": "limit-1",
        "agent_id": "codex-local",
        "scope": "lane",
        "model": None,
        "reason": "capacity",
        "source_agent_id": "autopilot",
        "observed_at": (NOW - timedelta(seconds=5)).isoformat(),
        "reset_at": (NOW + timedelta(seconds=1)).isoformat(),
    }
    service = VendorRegistryService(
        _db({"vendor_probe_state": [probe], "vendor_rate_limits": [limit]}),
        agents=[_agent()],
        now_fn=lambda: NOW,
    )
    assert (await service.get_availability("codex-local"))["status"] == "limited"

    limit["reset_at"] = NOW.isoformat()
    service = VendorRegistryService(
        _db({"vendor_probe_state": [probe], "vendor_rate_limits": [limit]}),
        agents=[_agent()],
        now_fn=lambda: NOW,
    )
    assert (await service.get_availability("codex-local"))["status"] == "available"


@pytest.mark.asyncio
async def test_stale_probe_is_unknown_and_model_limit_does_not_limit_lane() -> None:
    probe = {
        "agent_id": "codex-local",
        "status": "available",
        "source_agent_id": "watchdog",
        "reason": None,
        "observed_at": (NOW - timedelta(minutes=2)).isoformat(),
        "stale_after": NOW.isoformat(),
    }
    model_limit = {
        "observation_id": "limit-1",
        "agent_id": "codex-local",
        "scope": "model",
        "model": "gpt-5.6",
        "reason": "capacity",
        "source_agent_id": "autopilot",
        "observed_at": (NOW - timedelta(seconds=5)).isoformat(),
        "reset_at": (NOW + timedelta(minutes=5)).isoformat(),
    }
    service = VendorRegistryService(
        _db({"vendor_probe_state": [probe], "vendor_rate_limits": [model_limit]}),
        agents=[_agent()],
        now_fn=lambda: NOW,
    )

    availability = await service.get_availability("codex-local")

    assert availability["status"] == "unknown"
    assert availability["rate_limits"][0]["scope"] == "model"


@pytest.mark.asyncio
async def test_local_catalog_gate_fails_closed_despite_successful_probe() -> None:
    probe = {
        "agent_id": "local-model",
        "status": "available",
        "source_agent_id": "watchdog",
        "reason": None,
        "observed_at": (NOW - timedelta(seconds=5)).isoformat(),
        "stale_after": (NOW + timedelta(minutes=1)).isoformat(),
    }
    agent = _agent("local-model", endpoint_kind="local", model="qwen3-coder")
    service = VendorRegistryService(
        _db(
            {
                "vendor_probe_state": [probe],
                "model_catalog": [
                    {
                        "vendor": "local",
                        "model": "qwen3-coder",
                        "endpoint_kind": "local",
                        "base_url": None,
                        "available": False,
                        "stale": False,
                        "refreshed_at": NOW.isoformat(),
                    }
                ],
            }
        ),
        agents=[agent],
        now_fn=lambda: NOW,
    )

    lane = (await service.list_vendors())[0]

    assert lane["availability"]["status"] == "unavailable"
    assert lane["availability"]["reason"] == "catalog_unavailable"


def test_quote_cost_rounds_an_exact_half_up_at_six_decimal_places() -> None:
    quote = VendorRegistryService.quote_cost(
        {
            "prompt_usd_per_mtok": 1.25,
            "completion_usd_per_mtok": 5.5,
        },
        prompt_tokens=1234,
        completion_tokens=432,
    )

    assert quote == Decimal("0.003919")


@pytest.mark.asyncio
async def test_record_rate_limit_normalizes_reset_and_preserves_replay_marker() -> None:
    db = _db()
    db.rpc.return_value = [
        {
            "write_status": "accepted",
            "normalized_reset_at": (NOW + timedelta(seconds=30)).isoformat(),
        }
    ]
    service = VendorRegistryService(db, agents=[_agent()], now_fn=lambda: NOW)

    result = await service.record_rate_limit(
        "codex-local",
        observation_id="obs-1",
        reason="capacity",
        source_agent_id="autopilot",
        retry_after_seconds=30,
    )

    assert result["status"] == "accepted"
    params = db.rpc.await_args.args[1]
    assert params["p_reset_at"] == (NOW + timedelta(seconds=30)).isoformat()
    assert params["p_payload_hash"]
    assert result["reset_at"] == params["p_reset_at"]


@pytest.mark.asyncio
async def test_record_rate_limit_rejects_invalid_resets_and_rpc_conflict() -> None:
    db = _db()
    service = VendorRegistryService(db, agents=[_agent()], now_fn=lambda: NOW)

    with pytest.raises(ValueError, match="exactly one"):
        await service.record_rate_limit(
            "codex-local",
            observation_id="obs-1",
            reason="capacity",
            source_agent_id="autopilot",
            reset_at=NOW + timedelta(minutes=1),
            retry_after_seconds=30,
        )
    db.rpc.return_value = [
        {
            "write_status": "conflict",
            "normalized_reset_at": (NOW + timedelta(minutes=1)).isoformat(),
        }
    ]
    with pytest.raises(ObservationConflictError):
        await service.record_rate_limit(
            "codex-local",
            observation_id="obs-1",
            reason="capacity",
            source_agent_id="autopilot",
        )


@pytest.mark.asyncio
async def test_probe_and_compaction_use_atomic_rpcs() -> None:
    db = _db()
    db.rpc.side_effect = [[{"agent_id": "codex-local"}], 2]
    service = VendorRegistryService(db, agents=[_agent()], now_fn=lambda: NOW)

    await service.persist_probe(
        "codex-local",
        observation_id="probe-1",
        status="available",
        source_agent_id="watchdog",
        stale_after=NOW + timedelta(minutes=2),
    )
    deleted = await service.compact_rate_limits()

    assert deleted == 2
    assert [call.args[0] for call in db.rpc.await_args_list] == [
        "upsert_vendor_probe_state",
        "compact_vendor_rate_limits",
    ]

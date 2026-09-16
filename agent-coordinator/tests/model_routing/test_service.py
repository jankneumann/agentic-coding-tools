"""Service-level coverage for catalog-to-resolver routing orchestration."""

import random
from unittest.mock import AsyncMock

import pytest

from src.model_routing.api import RoutingService, SelectModelRequest
from src.model_routing.resolver import CandidateInput


@pytest.mark.asyncio
async def test_service_scores_catalog_candidates_and_records_decision() -> None:
    catalog = AsyncMock()
    catalog.list_candidates.return_value = [
        CandidateInput(
            vendor="local",
            model="qwen",
            endpoint_kind="local",
            benchmark_prior=0.8,
            prompt_usd_per_mtok=0.0,
            completion_usd_per_mtok=0.0,
        ),
        CandidateInput(
            vendor="openrouter",
            model="premium",
            endpoint_kind="openrouter",
            benchmark_prior=0.5,
            prompt_usd_per_mtok=5.0,
            completion_usd_per_mtok=10.0,
        ),
    ]
    catalog.record_decision.return_value = {}
    ledger = AsyncMock()
    ledger.usage_summary.return_value = {}
    service = RoutingService(catalog=catalog, ledger=ledger)

    result = await service.select_model(
        SelectModelRequest(
            task_signals={"archetype": "runner", "complexity": "low"},
            objective_profile="balanced",
            allow_exploration=False,
        )
    )

    assert result["selected"]["model"] == "qwen"
    assert result["fallback"] is False
    ledger.usage_summary.assert_not_awaited()
    catalog.list_candidates.assert_awaited_once_with("runner/low-complexity")
    decision = catalog.record_decision.await_args.args[0]
    assert decision["decision_id"] == result["decision_id"]
    assert decision["request"]["task_signals"]["archetype"] == "runner"
    assert decision["budget_state"] == {
        "status": "not-requested",
        "exploration_pct_used": None,
        "exploration_usd_used": None,
        "metered_usd_used": None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("env_name", "env_value", "summary"),
    [
        (
            "ROUTING_EXPLORATION_PCT",
            "0.10",
            {"entries": 10, "exploration_entries": 1},
        ),
        (
            "ROUTING_EXPLORATION_MONTHLY_USD",
            "2.50",
            {"entries": 10, "exploration_entries": 0, "exploration_usd_used": 2.5},
        ),
    ],
)
async def test_service_applies_current_month_exploration_budget_and_records_state(
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_value: str,
    summary: dict[str, float | int],
) -> None:
    monkeypatch.setenv(env_name, env_value)
    catalog = AsyncMock()
    catalog.list_candidates.return_value = [
        CandidateInput(
            vendor="local",
            model="top",
            endpoint_kind="local",
            benchmark_prior=0.9,
        ),
        CandidateInput(
            vendor="openrouter",
            model="alternative",
            endpoint_kind="openrouter",
            benchmark_prior=0.5,
        ),
    ]
    ledger = AsyncMock()
    ledger.usage_summary.return_value = {
        "actual_usd": 4.0,
        "exploration_usd_used": 0.0,
        **summary,
    }
    service = RoutingService(catalog=catalog, ledger=ledger, rng=random.Random(31))

    result = await service.select_model(SelectModelRequest(task_signals={"archetype": "runner"}))

    assert result["selected"]["model"] == "top"
    assert result["exploration"] is False
    ledger.usage_summary.assert_awaited_once_with(window="month", include_estimated=True)
    entries = float(summary.get("entries", 0))
    decision = catalog.record_decision.await_args.args[0]
    assert decision["budget_state"] == {
        "status": "available",
        "exploration_pct_used": pytest.approx(
            float(summary.get("exploration_entries", 0)) / entries
        ),
        "exploration_usd_used": pytest.approx(float(summary.get("exploration_usd_used", 0.0))),
        "metered_usd_used": pytest.approx(4.0),
    }


@pytest.mark.asyncio
async def test_service_ledger_failure_fails_closed_to_exploitation_and_records_degraded_state() -> (
    None
):
    catalog = AsyncMock()
    catalog.list_candidates.return_value = [
        CandidateInput(
            vendor="local",
            model="top",
            endpoint_kind="local",
            benchmark_prior=0.9,
        ),
        CandidateInput(
            vendor="openrouter",
            model="alternative",
            endpoint_kind="openrouter",
            benchmark_prior=0.5,
        ),
    ]
    ledger = AsyncMock()
    ledger.usage_summary.side_effect = RuntimeError("ledger unavailable")
    service = RoutingService(catalog=catalog, ledger=ledger, rng=random.Random(31))

    result = await service.select_model(SelectModelRequest(task_signals={"archetype": "runner"}))

    assert result["selected"]["model"] == "top"
    assert result["exploration"] is False
    assert catalog.record_decision.await_args.args[0]["budget_state"] == {
        "status": "unavailable",
        "exploration_pct_used": None,
        "exploration_usd_used": None,
        "metered_usd_used": None,
        "degraded_reason": "ledger-read-failed",
    }


@pytest.mark.asyncio
async def test_service_propagates_stale_catalog_to_response_and_decision() -> None:
    catalog = AsyncMock()
    catalog.list_candidates.return_value = [
        CandidateInput(
            vendor="local",
            model="qwen",
            endpoint_kind="local",
            benchmark_prior=0.8,
            stale_catalog=True,
        )
    ]
    ledger = AsyncMock()
    ledger.usage_summary.return_value = {}
    service = RoutingService(catalog=catalog, ledger=ledger)

    result = await service.select_model(
        SelectModelRequest(task_signals={"archetype": "runner"}, allow_exploration=False)
    )

    assert result["selected"]["stale_catalog"] is True
    assert catalog.record_decision.await_args.args[0]["selected"]["stale_catalog"] is True

"""Service-level coverage for catalog-to-resolver routing orchestration."""

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
    service = RoutingService(catalog=catalog, ledger=AsyncMock())

    result = await service.select_model(
        SelectModelRequest(
            task_signals={"archetype": "runner", "complexity": "low"},
            objective_profile="balanced",
            allow_exploration=False,
        )
    )

    assert result["selected"]["model"] == "qwen"
    assert result["fallback"] is False
    catalog.list_candidates.assert_awaited_once_with("runner/low-complexity")
    decision = catalog.record_decision.await_args.args[0]
    assert decision["decision_id"] == result["decision_id"]
    assert decision["request"]["task_signals"]["archetype"] == "runner"

"""RI-18 cost ladder behavior at the actual routing service boundary."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.model_routing.api import RoutingService, SelectModelRequest
from src.model_routing.resolver import CandidateInput
from src.model_routing.routing_policy import load_routing_policy


def _lane(agent: str, location: str, kind: str, *, available: bool = True) -> dict:
    return {
        "agent_id": agent,
        "vendor_type": agent,
        "policy_vendor": agent,
        "location": location,
        "isolation": "worktree",
        "archetypes": ["implementer"],
        "dispatch_modes": ["quick"],
        "dispatchable": True,
        "availability": {"available": available},
        "cost": {
            "models": [
                {
                    "catalog_vendor": agent,
                    "model": "shared-model",
                    "endpoint_kind": kind,
                    "base_url": None,
                    "available": available,
                }
            ]
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("local_available", "cloud_available", "expected_tier", "expected_agent", "metered_incumbent"),
    [
        (True, True, "subscription-local", "local-sub", False),
        (True, True, "subscription-local", "local-sub", True),
        (False, True, "subscription-cloud", "cloud-sub", False),
        (False, False, "metered-api", "metered", False),
    ],
)
async def test_router_uses_first_available_cost_tier(
    local_available: bool,
    cloud_available: bool,
    expected_tier: str,
    expected_agent: str,
    metered_incumbent: bool,
) -> None:
    policy = load_routing_policy()
    lanes = [
        _lane("local-sub", "local", "vendor-cli", available=local_available),
        _lane("cloud-sub", "cloud", "vendor-sdk", available=cloud_available),
        _lane("metered", "local", "openrouter"),
    ]
    registry = AsyncMock()
    registry.list_vendors.return_value = lanes
    catalog = AsyncMock()
    # Metered has the best quality, so selecting a subscription proves the
    # policy is a hard preference and not merely a score adjustment.
    catalog.list_candidates.return_value = [
        CandidateInput(
            vendor=lane["agent_id"],
            model="shared-model",
            endpoint_kind=lane["cost"]["models"][0]["endpoint_kind"],
            benchmark_prior=quality,
        )
        for lane, quality in zip(lanes, (0.2, 0.5, 1.0), strict=True)
    ]
    service = RoutingService(catalog=catalog, ledger=AsyncMock(), registry=registry, policy=policy)

    decision = await service.select_model(
        SelectModelRequest(
            task_signals={"archetype": "implementer"},
            routing_profile={"scope": "bounded-write"},
            allow_exploration=False,
            incumbent={"vendor": "metered", "model": "shared-model"} if metered_incumbent else None,
        )
    )

    assert decision["assignment"]["agent_id"] == expected_agent
    assert decision["provenance"]["cost_tier"] == expected_tier
    durable = catalog.record_decision_and_audit.await_args.args[0]
    assert durable["provenance"]["cost_tier"] == expected_tier
    assert durable["selected"]["provenance"]["cost_tier"] == expected_tier
    if expected_tier != "metered-api":
        assert any(
            item["agent_id"] == "metered" and item["reason"] == "cost-policy:lower-priority-tier"
            for item in decision["excluded"]
        )


def test_cost_policy_schema_and_loader_reject_invalid_ladder(tmp_path) -> None:
    import json

    import yaml
    from jsonschema import Draft202012Validator, ValidationError
    from openspec_paths import change_dir, repo_root_from

    schema_path = (
        change_dir(repo_root_from(__file__, 3), "declare-the-routing-cost-policy-the-router-obeys")
        / "contracts/config/routing-cost-policy.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    Draft202012Validator.check_schema(schema)
    source = repo_root_from(__file__, 3) / "agent-coordinator/routing.yaml"
    raw = yaml.safe_load(source.read_text())
    Draft202012Validator(schema).validate(raw["cost_policy"])

    raw["cost_policy"]["tiers"][0]["id"] = "metered-api"
    policy_path = tmp_path / "routing.yaml"
    policy_path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="cost tiers must follow"):
        load_routing_policy(policy_path)
    raw["cost_policy"]["tiers"][0]["id"] = "unknown"
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(raw["cost_policy"])

"""Atomic and sanitized DG-04 routing persistence tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.model_routing.catalog import CatalogService


@pytest.mark.asyncio
async def test_atomic_rpc_receives_decision_and_link_only_audit() -> None:
    db = AsyncMock()
    db.rpc.return_value = [{"decision_id": "3f1b7c1e-9a3d-4f9d-8b1a-2c6e5d4a9b0c"}]
    service = CatalogService(db)
    decision = {
        "decision_id": "3f1b7c1e-9a3d-4f9d-8b1a-2c6e5d4a9b0c",
        "request": {"task_signals": {"archetype": "implementer"}},
        "selected": {
            "model": "gpt-5.6-terra",
            "assignment": {"agent_id": "codex-local"},
            "provenance": {
                "source": "coordinator",
                "policy_version": "dg04-v1",
                "policy_checksum": "a" * 64,
            },
        },
        "alternatives": [],
        "excluded": [],
        "exploration": False,
        "fallback": False,
        "policy_version": "linear-utility-v1",
        "budget_state": {},
    }

    await service.record_decision_and_audit(decision)

    db.rpc.assert_awaited_once_with(
        "record_routing_decision_with_audit",
        {
            "p_decision": decision,
            "p_audit_link": {
                "decision_id": decision["decision_id"],
                "selected_agent_id": "codex-local",
                "selected_model": "gpt-5.6-terra",
                "routing_policy_version": "dg04-v1",
                "routing_policy_checksum": "a" * 64,
                "source": "coordinator",
                "success": True,
            },
        },
    )


@pytest.mark.asyncio
async def test_atomic_rpc_links_a_catalogless_retention_without_an_agent() -> None:
    db = AsyncMock()
    db.rpc.return_value = [{"decision_id": "3f1b7c1e-9a3d-4f9d-8b1a-2c6e5d4a9b0c"}]
    service = CatalogService(db)
    provenance = {
        "source": "coordinator",
        "policy_version": "dg04-v1",
        "policy_checksum": "a" * 64,
    }
    decision = {
        "decision_id": "3f1b7c1e-9a3d-4f9d-8b1a-2c6e5d4a9b0c",
        "request": {"task_signals": {"archetype": "architect"}},
        "selected": None,
        "assignment": None,
        "provenance": provenance,
        "retention": {"retained": True, "reason": "incumbent-unresolved", "margin": 0.05},
        "alternatives": [],
        "excluded": [],
        "exploration": False,
        "fallback": False,
        "policy_version": "linear-utility-v1",
        "budget_state": {},
    }

    await service.record_decision_and_audit(decision)

    link = db.rpc.await_args.args[1]["p_audit_link"]
    assert link == {
        "decision_id": decision["decision_id"],
        "selected_agent_id": None,
        "selected_model": None,
        "routing_policy_version": "dg04-v1",
        "routing_policy_checksum": "a" * 64,
        "source": "coordinator",
        "success": True,
    }

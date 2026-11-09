"""Live PostgreSQL proof for atomic routing-decision and audit persistence."""

from __future__ import annotations

from uuid import uuid4

import asyncpg
import pytest

pytestmark = pytest.mark.integration


def _decision(decision_id: str) -> dict:
    return {
        "decision_id": decision_id,
        "request": {
            "task_signals": {"archetype": "implementer"},
            "allow_exploration": False,
        },
        "selected": {
            "vendor": "codex",
            "model": "gpt-5.6-terra",
            "endpoint_kind": "vendor-cli",
            "score": 0.8,
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


def _audit_link(decision_id: str) -> dict:
    return {
        "decision_id": decision_id,
        "selected_agent_id": "codex-local",
        "selected_model": "gpt-5.6-terra",
        "routing_policy_version": "dg04-v1",
        "routing_policy_checksum": "a" * 64,
        "source": "coordinator",
        "success": True,
    }


async def test_atomic_rpc_commits_both_records_or_rolls_both_back(postgres_db) -> None:
    rolled_back_id = str(uuid4())
    invalid_link = {**_audit_link(rolled_back_id), "source": "local-static"}

    with pytest.raises(asyncpg.InvalidParameterValueError):
        await postgres_db.rpc(
            "record_routing_decision_with_audit",
            {"p_decision": _decision(rolled_back_id), "p_audit_link": invalid_link},
        )

    assert await postgres_db.query(
        "routing_decisions", f"decision_id=eq.{rolled_back_id}"
    ) == []

    committed_id = str(uuid4())
    await postgres_db.rpc(
        "record_routing_decision_with_audit",
        {
            "p_decision": _decision(committed_id),
            "p_audit_link": _audit_link(committed_id),
        },
    )

    decisions = await postgres_db.query(
        "routing_decisions", f"decision_id=eq.{committed_id}"
    )
    audit_rows = await postgres_db.query(
        "audit_log", "operation=eq.routing_decision&order=created_at.desc&limit=20"
    )
    linked = [row for row in audit_rows if row.get("result", {}).get("decision_id") == committed_id]
    assert decisions[0]["selected"]["assignment"]["agent_id"] == "codex-local"
    assert linked[0]["result"] == _audit_link(committed_id)

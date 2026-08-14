"""Tests for the registry → agent_profiles projection (sync_profiles).

Covers the agent-identity spec's "Registry Profile Sync" requirement:
insert missing, update drifted, disable orphans (with the ``evaluator``
carve-out), idempotent re-run, and the ``PROFILE_SYNC_ENABLED`` rollback
lever. Also pins the capability→operations mapping against the grants the
hand-written migrations gave ``claude_code_local`` (task 2.5).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agents_config import (
    CAPABILITY_OPERATIONS,
    PROFILE_SYNC_OPERATION,
    UNMANAGED_PROFILES,
    VALID_CAPABILITIES,
    AgentEntry,
    ProfileSyncError,
    derive_allowed_operations,
    sync_profiles,
)
from src.config import reset_config

CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "openspec"
    / "changes"
    / "derive-agent-identity-from-registry"
    / "contracts"
    / "events"
    / "profile-sync-audit.schema.json"
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeDb:
    """In-memory stand-in for the narrow DatabaseClient surface sync uses."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows: list[dict[str, Any]] = [dict(r) for r in (rows or [])]
        self.inserts: list[dict[str, Any]] = []
        self.updates: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.fail_query = False
        self.fail_insert = False
        self.fail_update = False

    async def query(
        self,
        table: str,
        query_params: str | None = None,
        select: str = "*",
    ) -> list[dict[str, Any]]:
        assert table == "agent_profiles"
        if self.fail_query:
            raise RuntimeError("db down")
        return [dict(r) for r in self.rows]

    async def insert(
        self,
        table: str,
        data: dict[str, Any],
        return_data: bool = True,
    ) -> dict[str, Any]:
        assert table == "agent_profiles"
        if self.fail_insert:
            raise RuntimeError("duplicate key value violates unique constraint")
        self.inserts.append(dict(data))
        self.rows.append(dict(data))
        return dict(data)

    async def update(
        self,
        table: str,
        match: dict[str, Any],
        data: dict[str, Any],
        return_data: bool = True,
    ) -> list[dict[str, Any]]:
        assert table == "agent_profiles"
        if self.fail_update:
            raise RuntimeError("db down")
        self.updates.append((dict(match), dict(data)))
        updated: list[dict[str, Any]] = []
        for row in self.rows:
            if all(row.get(k) == v for k, v in match.items()):
                row.update(data)
                updated.append(dict(row))
        return updated


class FakeAudit:
    """Captures log_operation calls."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def log_operation(self, **kwargs: Any) -> None:
        self.events.append(kwargs)

    def payloads(self, operation: str = PROFILE_SYNC_OPERATION) -> list[dict[str, Any]]:
        return [
            e["parameters"] for e in self.events if e.get("operation") == operation
        ]


def _agent(
    name: str,
    *,
    profile: str,
    agent_type: str = "claude_code",
    trust_level: int = 3,
    capabilities: list[str] | None = None,
) -> AgentEntry:
    return AgentEntry(
        name=name,
        type=agent_type,
        profile=profile,
        trust_level=trust_level,
        transport="mcp",
        capabilities=capabilities if capabilities is not None else ["lock"],
        description="test agent",
    )


def _row(
    name: str,
    *,
    agent_type: str = "claude_code",
    trust_level: int = 3,
    allowed_operations: list[str] | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    return {
        "name": name,
        "agent_type": agent_type,
        "trust_level": trust_level,
        "allowed_operations": allowed_operations if allowed_operations is not None else [],
        "enabled": enabled,
    }


@pytest.fixture(autouse=True)
def _sync_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROFILE_SYNC_ENABLED", raising=False)
    reset_config()


# ---------------------------------------------------------------------------
# derive_allowed_operations
# ---------------------------------------------------------------------------


class TestDeriveAllowedOperations:
    def test_every_valid_capability_is_mapped(self) -> None:
        """A capability the schema accepts but the map lacks = silent grant loss."""
        assert set(CAPABILITY_OPERATIONS) == VALID_CAPABILITIES

    def test_universal_operation_always_granted(self) -> None:
        ops = derive_allowed_operations([], trust_level=0)
        assert ops == ["get_my_profile"]

    def test_capability_derived(self) -> None:
        ops = derive_allowed_operations(["lock", "memory"], trust_level=2)
        assert set(ops) == {
            "acquire_lock",
            "release_lock",
            "check_locks",
            "remember",
            "recall",
            "get_my_profile",
        }

    def test_trust_derived_merge_queue_operations(self) -> None:
        """Migration 022 grants merge-queue ops by trust >= 3, not by capability."""
        low = derive_allowed_operations(["lock"], trust_level=2)
        high = derive_allowed_operations(["lock"], trust_level=3)
        merge_ops = {
            "enqueue_merge",
            "run_pre_merge_checks",
            "mark_merged",
            "remove_from_merge_queue",
        }
        assert merge_ops.isdisjoint(low)
        assert merge_ops.issubset(high)

    def test_output_is_sorted_and_deduplicated(self) -> None:
        # feature_registry and trust>=3 both grant register_feature.
        ops = derive_allowed_operations(["feature_registry"], trust_level=3)
        assert ops == sorted(ops)
        assert len(ops) == len(set(ops))

    def test_unknown_capability_raises(self) -> None:
        with pytest.raises(ValueError, match="no operation mapping"):
            derive_allowed_operations(["teleport"], trust_level=3)


class TestClaudeCodeLocalRegression:
    """Task 2.5 — the derived grants must reproduce migrations 007/019/022.

    ``claude_code_cli`` was seeded by 007, renamed to ``claude_code_local`` by
    019, and topped up by 022. The union below is what a live deployment's row
    holds today; the projection must not silently drop any of it.
    """

    MIGRATION_GRANTS = {
        # 007 seed for claude_code_cli
        "acquire_lock",
        "release_lock",
        "check_locks",
        "get_work",
        "get_task",
        "complete_work",
        "submit_work",
        "write_handoff",
        "read_handoff",
        "register_session",
        "discover_agents",
        "heartbeat",
        "remember",
        "recall",
        "check_guardrails",
        "get_my_profile",
        "query_audit",
        "register_feature",
        "deregister_feature",
        "enqueue_merge",
        "run_pre_merge_checks",
        "mark_merged",
        "remove_from_merge_queue",
    }

    def test_derived_operations_match_migrations(self) -> None:
        from src.agents_config import load_agents_config

        agents = load_agents_config()
        claude_local = next(a for a in agents if a.profile == "claude_code_local")
        derived = set(
            derive_allowed_operations(
                claude_local.capabilities, claude_local.trust_level
            )
        )
        assert derived == self.MIGRATION_GRANTS


# ---------------------------------------------------------------------------
# sync_profiles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSyncProfiles:
    async def test_inserts_missing_profile(self) -> None:
        db = FakeDb()
        audit = FakeAudit()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        result = await sync_profiles(agents, db=db, audit=audit)

        assert result.inserted == ["grok_local"]
        assert db.inserts[0]["name"] == "grok_local"
        assert db.inserts[0]["trust_level"] == 3
        assert db.inserts[0]["enabled"] is True
        assert db.inserts[0]["allowed_operations"] == derive_allowed_operations(
            ["lock"], 3
        )
        payloads = audit.payloads()
        assert payloads == [
            {
                "action": "insert",
                "profile_name": "grok_local",
                "agent_type": "grok",
                "source": "agents.yaml",
                "trust_level": 3,
            }
        ]

    async def test_updates_drifted_trust_level(self) -> None:
        db = FakeDb(
            [
                _row(
                    "grok_local",
                    agent_type="grok",
                    trust_level=2,
                    allowed_operations=derive_allowed_operations(["lock"], 3),
                )
            ]
        )
        audit = FakeAudit()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        result = await sync_profiles(agents, db=db, audit=audit)

        assert result.updated == ["grok_local"]
        assert db.updates[0][0] == {"name": "grok_local"}
        assert db.updates[0][1]["trust_level"] == 3
        payload = audit.payloads()[0]
        assert payload["action"] == "update"
        assert payload["changed_fields"] == {
            "trust_level": {"from": 2, "to": 3},
        }

    async def test_reenables_disabled_registry_profile(self) -> None:
        db = FakeDb(
            [
                _row(
                    "grok_local",
                    agent_type="grok",
                    allowed_operations=derive_allowed_operations(["lock"], 3),
                    enabled=False,
                )
            ]
        )
        audit = FakeAudit()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        result = await sync_profiles(agents, db=db, audit=audit)

        assert result.updated == ["grok_local"]
        assert audit.payloads()[0]["changed_fields"] == {
            "enabled": {"from": False, "to": True},
        }

    async def test_unchanged_row_emits_nothing(self) -> None:
        db = FakeDb(
            [
                _row(
                    "grok_local",
                    agent_type="grok",
                    allowed_operations=derive_allowed_operations(["lock"], 3),
                )
            ]
        )
        audit = FakeAudit()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        result = await sync_profiles(agents, db=db, audit=audit)

        assert result.unchanged == ["grok_local"]
        assert result.mutations == 0
        assert db.updates == []
        assert audit.events == []

    async def test_allowed_operations_order_is_not_drift(self) -> None:
        """A row storing the same grants in another order must not churn."""
        stored = list(reversed(derive_allowed_operations(["lock"], 3)))
        db = FakeDb([_row("grok_local", agent_type="grok", allowed_operations=stored)])
        audit = FakeAudit()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        result = await sync_profiles(agents, db=db, audit=audit)

        assert result.unchanged == ["grok_local"]

    async def test_disables_orphan_with_audit_event(self) -> None:
        db = FakeDb([_row("gemini_local", agent_type="gemini")])
        audit = FakeAudit()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        result = await sync_profiles(agents, db=db, audit=audit)

        assert result.disabled == ["gemini_local"]
        orphan = next(r for r in db.rows if r["name"] == "gemini_local")
        assert orphan["enabled"] is False
        assert orphan in db.rows  # retained, never deleted
        disable_payload = next(
            p for p in audit.payloads() if p["action"] == "disable"
        )
        assert disable_payload == {
            "action": "disable",
            "profile_name": "gemini_local",
            "agent_type": "gemini",
            "source": "agents.yaml",
        }

    async def test_already_disabled_orphan_is_not_touched(self) -> None:
        db = FakeDb([_row("gemini_local", agent_type="gemini", enabled=False)])
        audit = FakeAudit()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        result = await sync_profiles(agents, db=db, audit=audit)

        assert result.disabled == []
        assert audit.payloads() == [p for p in audit.payloads() if p["action"] != "disable"]

    async def test_unmanaged_role_profile_survives(self) -> None:
        """D2 amendment: `evaluator` is a role, not a harness identity."""
        assert "evaluator" in UNMANAGED_PROFILES
        db = FakeDb(
            [
                _row("evaluator", agent_type="evaluator", trust_level=2,
                     allowed_operations=["read", "review", "evaluate"]),
                _row("strands_local", agent_type="strands"),
            ]
        )
        audit = FakeAudit()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        result = await sync_profiles(agents, db=db, audit=audit)

        assert result.disabled == ["strands_local"]
        evaluator = next(r for r in db.rows if r["name"] == "evaluator")
        assert evaluator["enabled"] is True
        assert evaluator["allowed_operations"] == ["read", "review", "evaluate"]
        assert all(
            p["profile_name"] != "evaluator" for p in audit.payloads()
        )

    async def test_idempotent_rerun(self) -> None:
        db = FakeDb([_row("gemini_local", agent_type="gemini")])
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        first = await sync_profiles(agents, db=db, audit=FakeAudit())
        assert first.mutations == 2  # insert grok_local, disable gemini_local

        audit = FakeAudit()
        second = await sync_profiles(agents, db=db, audit=audit)

        assert second.mutations == 0
        assert second.unchanged == ["grok_local"]
        assert audit.events == []

    async def test_disabled_by_flag_performs_no_writes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROFILE_SYNC_ENABLED", "false")
        reset_config()
        db = FakeDb([_row("gemini_local", agent_type="gemini")])
        audit = FakeAudit()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        result = await sync_profiles(agents, db=db, audit=audit)

        assert result.skipped_reason == "disabled"
        assert db.inserts == []
        assert db.updates == []
        assert audit.events == []

    async def test_empty_registry_disables_nothing(self) -> None:
        """Orphan disabling against an empty roster would nuke the table."""
        db = FakeDb([_row("gemini_local", agent_type="gemini")])
        audit = FakeAudit()

        result = await sync_profiles([], db=db, audit=audit)

        assert result.skipped_reason == "no_registry"
        assert db.updates == []

    async def test_read_failure_raises(self) -> None:
        db = FakeDb()
        db.fail_query = True
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        with pytest.raises(ProfileSyncError, match="Could not read agent_profiles"):
            await sync_profiles(agents, db=db, audit=FakeAudit())

    async def test_write_failure_raises(self) -> None:
        db = FakeDb()
        db.fail_insert = True
        db.fail_update = True
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        with pytest.raises(ProfileSyncError, match="Could not project agent"):
            await sync_profiles(agents, db=db, audit=FakeAudit())

    async def test_concurrent_insert_converges_via_update(self) -> None:
        """A racing worker wins the INSERT; the loser reconciles instead of dying."""
        db = FakeDb()
        db.fail_insert = True  # simulate UNIQUE(name) violation
        audit = FakeAudit()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        result = await sync_profiles(agents, db=db, audit=audit)

        assert result.updated == ["grok_local"]
        assert db.updates[0][0] == {"name": "grok_local"}

    async def test_unmappable_capability_fails_sync(self) -> None:
        db = FakeDb()
        agents = [
            _agent(
                "broken",
                profile="broken_profile",
                capabilities=["not_a_capability"],
            )
        ]

        with pytest.raises(ProfileSyncError, match="cannot be projected"):
            await sync_profiles(agents, db=db, audit=FakeAudit())

    async def test_full_registry_projects_cleanly(self) -> None:
        """Every agent in the real agents.yaml materializes a profile row."""
        from src.agents_config import load_agents_config

        agents = load_agents_config()
        db = FakeDb()
        result = await sync_profiles(agents, db=db, audit=FakeAudit())

        assert sorted(result.inserted) == sorted({a.profile for a in agents})


# ---------------------------------------------------------------------------
# Audit contract conformance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAuditContract:
    async def test_events_validate_against_contract(self) -> None:
        from jsonschema import validate

        schema = json.loads(CONTRACT_PATH.read_text())
        db = FakeDb(
            [
                _row("gemini_local", agent_type="gemini"),
                _row("grok_local", agent_type="grok", trust_level=1),
            ]
        )
        audit = FakeAudit()
        agents = [
            _agent("grok-local", profile="grok_local", agent_type="grok"),
            _agent("pi-local", profile="pi_local", agent_type="pi"),
        ]

        await sync_profiles(agents, db=db, audit=audit)

        payloads = audit.payloads()
        assert {p["action"] for p in payloads} == {"insert", "update", "disable"}
        for payload in payloads:
            validate(instance=payload, schema=schema)

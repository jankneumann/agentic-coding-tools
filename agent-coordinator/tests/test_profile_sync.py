"""Tests for the registry → agent_profiles projection (sync_profiles).

Covers the agent-identity spec's "Registry Profile Sync" requirement:
insert missing, update drifted, disable orphans (with the ``evaluator``
carve-out), idempotent re-run, and the ``PROFILE_SYNC_ENABLED`` rollback
lever. Also pins the capability→operations mapping against the grants the
hand-written migrations gave ``claude_code_local`` (task 2.5).
"""

from __future__ import annotations

import itertools
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from src.agents_config import (
    ASSIGNMENT_ASSIGNED_BY,
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


PROFILES_TABLE = "agent_profiles"
ASSIGNMENTS_TABLE = "agent_profile_assignments"

#: Synthetic ``created_at`` values, handed out in creation order so the fake
#: reproduces the ``ORDER BY created_at ASC`` tiebreak ``get_agent_profile()``
#: uses when an agent has no assignment. Lexicographic order == creation order.
_CREATED_AT_SEQUENCE = itertools.count()


def _next_created_at() -> str:
    stamp = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(
        seconds=next(_CREATED_AT_SEQUENCE)
    )
    return stamp.isoformat()


def _profile_id(name: str) -> str:
    """Deterministic opaque id for a profile row, standing in for the UUID PK."""
    return str(uuid.uuid5(uuid.NAMESPACE_OID, f"agent_profiles:{name}"))


class FakeDb:
    """In-memory stand-in for the narrow DatabaseClient surface sync uses.

    Models both tables the projection writes:

    * ``agent_profiles`` — ``UNIQUE (name)``, ``id`` and ``created_at`` filled
      in by the database on insert (the projection never supplies them);
    * ``agent_profile_assignments`` — ``UNIQUE (agent_id)``, enforced here so a
      duplicate insert raises the way Postgres would, which is what makes the
      concurrent-boot convergence test mean anything.
    """

    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        assignments: list[dict[str, Any]] | None = None,
    ) -> None:
        self.rows: list[dict[str, Any]] = [dict(r) for r in (rows or [])]
        for row in self.rows:
            row.setdefault("id", _profile_id(str(row.get("name"))))
            row.setdefault("created_at", _next_created_at())
        self.assignments: list[dict[str, Any]] = [dict(a) for a in (assignments or [])]
        self.inserts: list[dict[str, Any]] = []
        self.updates: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.assignment_inserts: list[dict[str, Any]] = []
        self.assignment_updates: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.deletes: list[tuple[str, dict[str, Any]]] = []
        self.fail_query = False
        self.fail_insert = False
        self.fail_update = False
        self.fail_delete = False
        #: Assignment rows a *concurrent* worker commits between our read of
        #: ``agent_profile_assignments`` and our write. Injected right after the
        #: first read of that table, so the projection's INSERT hits
        #: ``UNIQUE (agent_id)`` exactly as it would in a real two-worker boot.
        self.race_assignments: list[dict[str, Any]] = []
        #: A NON-uniqueness insert failure — RLS denial, FK violation, CHECK
        #: failure. Unlike ``fail_insert`` no row is left behind, so a
        #: fallback UPDATE would match zero rows and (with
        #: ``return_data=False``) raise nothing.
        self.profile_insert_error: BaseException | None = None
        self.assignment_insert_error: BaseException | None = None
        #: Exception ``fail_insert`` raises. Defaults to the PostgREST backend's
        #: message text; override to exercise a driver that signals uniqueness
        #: some other way (asyncpg raises ``UniqueViolationError`` and carries
        #: SQLSTATE 23505 without the message text).
        self.fail_insert_error: BaseException | None = None

    def _table(self, table: str) -> list[dict[str, Any]]:
        if table == PROFILES_TABLE:
            return self.rows
        if table == ASSIGNMENTS_TABLE:
            return self.assignments
        raise AssertionError(f"unexpected table {table!r}")

    async def query(
        self,
        table: str,
        query_params: str | None = None,
        select: str = "*",
    ) -> list[dict[str, Any]]:
        if self.fail_query:
            raise RuntimeError("db down")
        snapshot = [dict(r) for r in self._table(table)]
        if table == ASSIGNMENTS_TABLE and self.race_assignments:
            self.assignments.extend(dict(a) for a in self.race_assignments)
            self.race_assignments = []
        return snapshot

    async def insert(
        self,
        table: str,
        data: dict[str, Any],
        return_data: bool = True,
    ) -> dict[str, Any]:
        if table == ASSIGNMENTS_TABLE:
            if self.assignment_insert_error is not None:
                raise self.assignment_insert_error
            agent_id = data.get("agent_id")
            if any(a.get("agent_id") == agent_id for a in self.assignments):
                raise RuntimeError(
                    "duplicate key value violates unique constraint "
                    '"agent_profile_assignments_agent_id_key"'
                )
            row = {"id": str(uuid.uuid4()), **data}
            self.assignment_inserts.append(dict(data))
            self.assignments.append(row)
            return dict(row)

        assert table == PROFILES_TABLE
        if self.profile_insert_error is not None:
            raise self.profile_insert_error
        row = {
            "id": _profile_id(str(data.get("name"))),
            "created_at": _next_created_at(),
            **data,
        }
        if self.fail_insert:
            # A racing worker won the UNIQUE (name) insert: the row exists in
            # the table even though *our* insert raised.
            if not any(r.get("name") == data.get("name") for r in self.rows):
                self.rows.append(row)
            raise self.fail_insert_error or RuntimeError(
                "duplicate key value violates unique constraint"
            )
        self.inserts.append(dict(data))
        self.rows.append(row)
        return dict(row)

    async def update(
        self,
        table: str,
        match: dict[str, Any],
        data: dict[str, Any],
        return_data: bool = True,
    ) -> list[dict[str, Any]]:
        if self.fail_update:
            raise RuntimeError("db down")
        if table == ASSIGNMENTS_TABLE:
            self.assignment_updates.append((dict(match), dict(data)))
        else:
            assert table == PROFILES_TABLE
            self.updates.append((dict(match), dict(data)))
        updated: list[dict[str, Any]] = []
        for row in self._table(table):
            if all(row.get(k) == v for k, v in match.items()):
                row.update(data)
                updated.append(dict(row))
        return updated

    async def delete(self, table: str, match: dict[str, Any]) -> None:
        if self.fail_delete:
            raise RuntimeError("db down")
        rows = self._table(table)
        self.deletes.append((table, dict(match)))
        for row in [r for r in rows if all(r.get(k) == v for k, v in match.items())]:
            rows.remove(row)


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
    created_at: str | None = None,
) -> dict[str, Any]:
    return {
        "id": _profile_id(name),
        "name": name,
        "agent_type": agent_type,
        "trust_level": trust_level,
        "allowed_operations": allowed_operations if allowed_operations is not None else [],
        "enabled": enabled,
        # Creation order decides the type-based fallback in get_agent_profile();
        # rows built earlier are therefore "older".
        "created_at": created_at if created_at is not None else _next_created_at(),
    }


def _assignment(
    agent_id: str,
    profile_name: str,
    *,
    assigned_by: str | None = None,
) -> dict[str, Any]:
    """An ``agent_profile_assignments`` row pointing at *profile_name*."""
    return {
        "id": str(uuid.uuid4()),
        "agent_id": agent_id,
        "profile_id": _profile_id(profile_name),
        "assigned_by": assigned_by,
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
        assert payloads[0] == {
            "action": "insert",
            "profile_name": "grok_local",
            "agent_type": "grok",
            "source": "agents.yaml",
            "trust_level": 3,
        }
        # The profile row alone does not decide resolution — the assignment does.
        assert payloads[1] == {
            "action": "assign",
            "profile_name": "grok_local",
            "agent_type": "grok",
            "source": "agents.yaml",
            "trust_level": 3,
            "agent_id": "grok-local",
        }
        assert len(payloads) == 2

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
            ],
            assignments=[
                _assignment(
                    "grok-local", "grok_local", assigned_by=ASSIGNMENT_ASSIGNED_BY
                )
            ],
        )
        audit = FakeAudit()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        result = await sync_profiles(agents, db=db, audit=audit)

        assert result.unchanged == ["grok_local"]
        assert result.assignments_unchanged == ["grok-local"]
        assert result.mutations == 0
        assert db.updates == []
        assert db.assignment_inserts == []
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
        # insert grok_local, disable gemini_local, assign grok-local
        assert first.mutations == 3

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
# agent_profile_assignments projection (design D11)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSyncAssignments:
    """The assignment table is what ``get_agent_profile()`` reads first.

    Migration 018 wrote these rows by hand for the roster of its day and for
    nobody added afterwards; projecting them from the registry removes the
    second hand-maintained roster.
    """

    async def test_assigns_every_registry_agent_to_its_declared_profile(self) -> None:
        db = FakeDb()
        audit = FakeAudit()
        agents = [
            _agent("grok-local", profile="grok_local", agent_type="grok"),
            _agent("pi-local", profile="pi_local", agent_type="pi"),
        ]

        result = await sync_profiles(agents, db=db, audit=audit)

        assert result.assigned == ["grok-local", "pi-local"]
        by_agent = {a["agent_id"]: a for a in db.assignments}
        assert by_agent["grok-local"]["profile_id"] == _profile_id("grok_local")
        assert by_agent["pi-local"]["profile_id"] == _profile_id("pi_local")
        # `assigned_by` distinguishes projected rows from hand-written ones.
        assert {a["assigned_by"] for a in db.assignments} == {ASSIGNMENT_ASSIGNED_BY}

    async def test_reassigns_pointer_at_the_wrong_profile(self) -> None:
        db = FakeDb(
            [
                _row("gemini_local", agent_type="gemini"),
                _row(
                    "grok_local",
                    agent_type="grok",
                    allowed_operations=derive_allowed_operations(["lock"], 3),
                ),
            ],
            assignments=[_assignment("grok-local", "gemini_local")],
        )
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        result = await sync_profiles(agents, db=db, audit=FakeAudit())

        assert result.reassigned == ["grok-local"]
        assert db.assignment_updates[0][0] == {"agent_id": "grok-local"}
        assert db.assignments[0]["profile_id"] == _profile_id("grok_local")
        assert db.assignments[0]["assigned_by"] == ASSIGNMENT_ASSIGNED_BY

    async def test_stale_assignment_is_deleted_and_its_profile_retained(self) -> None:
        """A pointer is not authorization state — deleting it loses nothing."""
        db = FakeDb(
            [_row("gemini_local", agent_type="gemini")],
            assignments=[_assignment("gemini-local", "gemini_local")],
        )
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        result = await sync_profiles(agents, db=db, audit=FakeAudit())

        assert result.unassigned == ["gemini-local"]
        assert [a["agent_id"] for a in db.assignments] == ["grok-local"]
        assert db.deletes == [
            (ASSIGNMENTS_TABLE, {"agent_id": "gemini-local"}),
        ]
        # The profile it pointed at survives, disabled — D2 still holds there.
        gemini = next(r for r in db.rows if r["name"] == "gemini_local")
        assert gemini["enabled"] is False

    async def test_idempotent_rerun_writes_no_assignments(self) -> None:
        db = FakeDb()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        await sync_profiles(agents, db=db, audit=FakeAudit())
        db.assignment_inserts.clear()
        db.assignment_updates.clear()
        audit = FakeAudit()

        second = await sync_profiles(agents, db=db, audit=audit)

        assert second.assignments_unchanged == ["grok-local"]
        assert second.mutations == 0
        assert db.assignment_inserts == []
        assert db.assignment_updates == []
        assert audit.events == []

    async def test_concurrent_assignment_insert_converges_via_update(self) -> None:
        """The loser of the UNIQUE (agent_id) race reconciles instead of dying."""
        db = FakeDb()
        # Committed by a racing worker after we snapshot the assignment table.
        db.race_assignments = [_assignment("grok-local", "gemini_local")]
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        result = await sync_profiles(agents, db=db, audit=FakeAudit())

        assert result.assigned == ["grok-local"]
        assert db.assignment_updates[0][0] == {"agent_id": "grok-local"}
        assert len(db.assignments) == 1
        assert db.assignments[0]["profile_id"] == _profile_id("grok_local")

    async def test_assignment_write_failure_raises(self) -> None:
        db = FakeDb()
        db.race_assignments = [_assignment("grok-local", "gemini_local")]
        db.fail_update = True
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        with pytest.raises(ProfileSyncError, match="Could not assign agent"):
            await sync_profiles(agents, db=db, audit=FakeAudit())

    async def test_stale_assignment_delete_failure_raises(self) -> None:
        db = FakeDb(
            [_row("gemini_local", agent_type="gemini")],
            assignments=[_assignment("gemini-local", "gemini_local")],
        )
        db.fail_delete = True
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        with pytest.raises(ProfileSyncError, match="stale assignment"):
            await sync_profiles(agents, db=db, audit=FakeAudit())

    async def test_disabled_by_flag_writes_no_assignments(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rule 4: the projection has one knob, PROFILE_SYNC_ENABLED."""
        monkeypatch.setenv("PROFILE_SYNC_ENABLED", "false")
        reset_config()
        db = FakeDb()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        result = await sync_profiles(agents, db=db, audit=FakeAudit())

        assert result.skipped_reason == "disabled"
        assert db.assignments == []
        assert db.assignment_inserts == []

    async def test_full_registry_assigns_every_agent(self) -> None:
        from src.agents_config import load_agents_config

        agents = load_agents_config()
        db = FakeDb()

        result = await sync_profiles(agents, db=db, audit=FakeAudit())

        assert sorted(result.assigned) == sorted(a.name for a in agents)


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
            ],
            assignments=[
                # An agent the registry no longer declares → unassign.
                _assignment("gemini-local", "gemini_local"),
                # A hand-written assignment pointing at the wrong row → reassign.
                _assignment("grok-local", "gemini_local"),
                # pi-local has no assignment at all → assign.
            ],
        )
        audit = FakeAudit()
        agents = [
            _agent("grok-local", profile="grok_local", agent_type="grok"),
            _agent("pi-local", profile="pi_local", agent_type="pi"),
        ]

        await sync_profiles(agents, db=db, audit=audit)

        payloads = audit.payloads()
        assert {p["action"] for p in payloads} == {
            "insert", "update", "disable", "assign", "reassign", "unassign",
        }
        for payload in payloads:
            validate(instance=payload, schema=schema)

    async def test_assignment_actions_carry_reconstructible_detail(self) -> None:
        """reassign/unassign must record which profile the pointer left behind."""
        db = FakeDb(
            [
                _row("gemini_local", agent_type="gemini"),
                _row(
                    "grok_local",
                    agent_type="grok",
                    allowed_operations=derive_allowed_operations(["lock"], 3),
                ),
            ],
            assignments=[
                _assignment("gemini-local", "gemini_local"),
                _assignment("grok-local", "gemini_local"),
            ],
        )
        audit = FakeAudit()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        result = await sync_profiles(agents, db=db, audit=audit)

        assert result.reassigned == ["grok-local"]
        assert result.unassigned == ["gemini-local"]
        payloads = audit.payloads()
        assert next(p for p in payloads if p["action"] == "reassign") == {
            "action": "reassign",
            "profile_name": "grok_local",
            "agent_type": "grok",
            "source": "agents.yaml",
            "trust_level": 3,
            "agent_id": "grok-local",
            "previous_profile_name": "gemini_local",
        }
        assert next(p for p in payloads if p["action"] == "unassign") == {
            "action": "unassign",
            # The profile the removed pointer referenced — retained and disabled
            # by the profile phase, so the removal is reconstructible.
            "profile_name": "gemini_local",
            "agent_type": "gemini",
            "source": "agents.yaml",
            "agent_id": "gemini-local",
        }


# ---------------------------------------------------------------------------
# Insert-failure fallback (must not report zero-row writes as success)
# ---------------------------------------------------------------------------


class _RlsDeniedError(RuntimeError):
    """Stand-in for a non-uniqueness write failure (RLS / FK / CHECK).

    Deliberately carries no ``sqlstate`` and no "duplicate key value violates
    unique constraint" text, because that is exactly what distinguishes it from
    the lost-INSERT race the fallback exists for.
    """


class _AsyncpgUniqueViolationError(RuntimeError):
    """Shape of asyncpg's UniqueViolationError: class name plus SQLSTATE.

    asyncpg does not put the PostgreSQL message text in ``str(exc)`` the way
    the PostgREST backend does, so the narrowed fallback has to recognize the
    driver's own signal too, or a real two-worker boot race would start failing
    boots on the postgres backend.
    """

    sqlstate = "23505"


_AsyncpgUniqueViolationError.__name__ = "UniqueViolationError"


@pytest.mark.asyncio
class TestInsertFailureFallbackIsNarrow:
    """Only a lost UNIQUE race may be retried as an UPDATE.

    ``db.update(..., return_data=False)`` never inspects rowcount, so a
    zero-row UPDATE raises nothing. Retrying *any* failed insert as an update
    therefore recorded an RLS denial or FK violation as a successful
    projection: ``result.inserted``/``assigned`` grew and an audit event was
    emitted for a row that does not exist.
    """

    async def test_non_unique_profile_insert_failure_raises(self) -> None:
        db = FakeDb()
        db.profile_insert_error = _RlsDeniedError("new row violates row-level security")
        audit = FakeAudit()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        with pytest.raises(ProfileSyncError, match="Could not project agent"):
            await sync_profiles(agents, db=db, audit=audit)

        # No phantom write, and no audit event claiming one happened.
        assert db.updates == []
        assert audit.payloads() == []
        assert db.rows == []

    async def test_non_unique_assignment_insert_failure_raises(self) -> None:
        db = FakeDb()
        db.assignment_insert_error = _RlsDeniedError("insert or update violates foreign key")
        audit = FakeAudit()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        with pytest.raises(ProfileSyncError, match="Could not assign agent"):
            await sync_profiles(agents, db=db, audit=audit)

        assert db.assignment_updates == []
        assert db.assignments == []
        assert [p["action"] for p in audit.payloads()] == ["insert"]

    async def test_unique_violation_still_converges_via_update(self) -> None:
        """The genuine race the fallback exists for keeps working."""
        db = FakeDb()
        db.fail_insert = True  # message text carries the UNIQUE signal
        audit = FakeAudit()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        result = await sync_profiles(agents, db=db, audit=audit)

        assert result.updated == ["grok_local"]

    async def test_asyncpg_unique_violation_recognized(self) -> None:
        """The driver's own signal counts, not just the message text.

        asyncpg's ``UniqueViolationError`` does not carry PostgreSQL's message
        text in ``str(exc)``. Matching on text alone would turn every real
        two-worker boot race into a failed boot on ``DB_BACKEND=postgres``.
        """
        db = FakeDb()
        db.fail_insert = True
        db.fail_insert_error = _AsyncpgUniqueViolationError(
            "<class 'asyncpg.exceptions.UniqueViolationError'>"
        )
        audit = FakeAudit()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        result = await sync_profiles(agents, db=db, audit=audit)

        assert result.updated == ["grok_local"]


# ---------------------------------------------------------------------------
# synced_from_registry_at bookkeeping (migration 031)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSyncedFromRegistryAt:
    """Migration 031's column has to actually be written.

    Its COMMENT tells operators the column distinguishes registry-projected
    rows from hand-maintained ones. Nothing wrote it, so it was permanently
    NULL and the comment was false.
    """

    @staticmethod
    def _assert_recent_iso(value: Any) -> None:
        assert isinstance(value, str), f"expected an ISO timestamp, got {value!r}"
        stamped = datetime.fromisoformat(value)
        assert stamped.tzinfo is not None, "timestamp must be timezone-aware"
        assert abs((datetime.now(UTC) - stamped).total_seconds()) < 60

    async def test_insert_stamps_the_column(self) -> None:
        db = FakeDb()
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        await sync_profiles(agents, db=db, audit=FakeAudit())

        self._assert_recent_iso(db.inserts[0].get("synced_from_registry_at"))

    async def test_drift_update_stamps_the_column(self) -> None:
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
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        await sync_profiles(agents, db=db, audit=FakeAudit())

        self._assert_recent_iso(db.updates[0][1].get("synced_from_registry_at"))

    async def test_orphan_disable_does_not_restamp(self) -> None:
        """Disabling an orphan is not a projection *of* that row.

        Leaving its stamp at the last successful projection is what makes
        "registry-projected, then orphaned" reconstructible.
        """
        db = FakeDb([_row("gemini_local", agent_type="gemini")])
        agents = [_agent("grok-local", profile="grok_local", agent_type="grok")]

        await sync_profiles(agents, db=db, audit=FakeAudit())

        disable = next(u for u in db.updates if u[0] == {"name": "gemini_local"})
        assert disable[1] == {"enabled": False}

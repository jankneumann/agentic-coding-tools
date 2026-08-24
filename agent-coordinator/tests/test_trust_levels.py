"""Tests for the unified trust scale (design D4 of derive-agent-identity-from-registry).

The trust scale is not new: `openspec/specs/agent-coordinator/spec.md` already documents
it as a table (0 Untrusted / 1 Limited / 2 Standard / 3 Elevated / 4 Admin).
`src/trust_levels.py` is the single *programmatic* rendering of that documented table.

These tests assert the three consumers agree with the module:

1. the documented spec table,
2. the policy engine's read/write/admin action-tier thresholds,
3. the `agent_profiles` CHECK constraint shipped by the migration.

The DB is not available here, so the migration is asserted on its **SQL text**
(same approach as `tests/test_phase_archetype_migration.py`).
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from src import policy_engine
from src.policy_engine import ADMIN_ACTIONS, READ_ACTIONS, WRITE_ACTIONS, NativePolicyEngine
from src.trust_levels import (
    MAX_TRUST,
    MIN_ADMIN_TRUST,
    MIN_READ_TRUST,
    MIN_TRUST,
    MIN_WRITE_TRUST,
    TrustLevel,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COORDINATOR_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = COORDINATOR_ROOT / "database" / "migrations"
SPEC_PATH = REPO_ROOT / "openspec" / "specs" / "agent-coordinator" / "spec.md"

# The documented table, transcribed. Kept here so a silent edit to either the
# spec or the module is a test failure rather than a drift.
DOCUMENTED_SCALE = {
    0: "Untrusted",
    1: "Limited",
    2: "Standard",
    3: "Elevated",
    4: "Admin",
}


# ---------------------------------------------------------------------------
# Enum shape
# ---------------------------------------------------------------------------


def test_trust_level_is_int_enum() -> None:
    """TrustLevel members compare as plain ints so DB/JSON values drop in."""
    assert TrustLevel.STANDARD == 2
    assert int(TrustLevel.ELEVATED) == 3
    assert TrustLevel.LIMITED < TrustLevel.ADMIN


@pytest.mark.parametrize(("value", "name"), sorted(DOCUMENTED_SCALE.items()))
def test_each_documented_level_has_a_member(value: int, name: str) -> None:
    """Every row of the documented table maps to exactly one enum member."""
    member = TrustLevel(value)
    assert member.name == name.upper(), (
        f"Trust level {value} is documented as {name!r}; enum has {member.name!r}"
    )


def test_no_extra_members_beyond_documented_table() -> None:
    """The module MUST NOT invent levels the spec does not document."""
    assert {int(m): m.name for m in TrustLevel} == {
        v: n.upper() for v, n in DOCUMENTED_SCALE.items()
    }


def test_spec_table_matches_module() -> None:
    """Parse the `Profile Trust Levels` table out of the spec and compare."""
    text = SPEC_PATH.read_text(encoding="utf-8")
    section = text.split("#### Profile Trust Levels", 1)
    assert len(section) == 2, f"{SPEC_PATH} no longer documents 'Profile Trust Levels'"
    # Table ends at the first blank-line-separated non-table block.
    rows = re.findall(r"^\|\s*(\d+)\s*\|\s*([A-Za-z]+)\s*\|", section[1], flags=re.MULTILINE)
    assert rows, "Could not parse any rows from the Profile Trust Levels table"
    parsed = {int(level): name for level, name in rows}
    assert parsed == DOCUMENTED_SCALE, (
        "The spec's Profile Trust Levels table drifted from the transcribed table; "
        "update DOCUMENTED_SCALE and src/trust_levels.py together."
    )


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------


def test_bounds_exported() -> None:
    assert MIN_TRUST == 0
    assert MAX_TRUST == 4


def test_bounds_derive_from_enum() -> None:
    """MIN_TRUST/MAX_TRUST MUST be the enum's extremes, not hand-typed literals."""
    assert MIN_TRUST == int(min(TrustLevel))
    assert MAX_TRUST == int(max(TrustLevel))
    assert MIN_TRUST == TrustLevel.UNTRUSTED
    assert MAX_TRUST == TrustLevel.ADMIN


def test_scale_is_contiguous() -> None:
    """No gaps — a range check on the bounds is equivalent to enum membership."""
    assert sorted(int(m) for m in TrustLevel) == list(range(MIN_TRUST, MAX_TRUST + 1))


# ---------------------------------------------------------------------------
# Action-tier thresholds
# ---------------------------------------------------------------------------


def test_action_tier_thresholds_are_named_levels() -> None:
    """The read/write/admin tiers reference enum members, not bare ints."""
    assert MIN_READ_TRUST is TrustLevel.LIMITED
    assert MIN_WRITE_TRUST is TrustLevel.STANDARD
    assert MIN_ADMIN_TRUST is TrustLevel.ELEVATED


def test_action_tiers_are_monotonic() -> None:
    assert MIN_TRUST < MIN_READ_TRUST < MIN_WRITE_TRUST < MIN_ADMIN_TRUST <= MAX_TRUST


def test_policy_engine_has_no_bare_trust_literals() -> None:
    """The policy engine MUST derive tiers from the module (spec: 'rather than
    integer literals')."""
    source = inspect.getsource(policy_engine)
    offenders = re.findall(r"trust_level\s*(?:>=|<=|==|<|>)\s*\d", source)
    assert not offenders, (
        f"policy_engine still compares trust_level against integer literals: {offenders}"
    )


def test_policy_engine_imports_trust_scale() -> None:
    assert policy_engine.TrustLevel is TrustLevel


def test_action_frozensets_unchanged() -> None:
    """The refactor is readability-only: tier membership MUST NOT move."""
    assert READ_ACTIONS.isdisjoint(WRITE_ACTIONS)
    assert READ_ACTIONS.isdisjoint(ADMIN_ACTIONS)
    assert WRITE_ACTIONS.isdisjoint(ADMIN_ACTIONS)
    assert "check_locks" in READ_ACTIONS
    assert "acquire_lock" in WRITE_ACTIONS
    assert "force_push" in ADMIN_ACTIONS


# ---------------------------------------------------------------------------
# Policy engine behaviour at the tier boundaries (unchanged by the refactor)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_boundary_matches_min_write_trust(mock_supabase, db_client) -> None:  # type: ignore[no-untyped-def]
    engine = NativePolicyEngine(db_client)

    denied = await engine.check_operation(
        agent_id="test-agent",
        agent_type="claude_code",
        operation="acquire_lock",
        context={"trust_level": int(MIN_WRITE_TRUST) - 1},
    )
    assert denied.allowed is False
    assert f"< {int(MIN_WRITE_TRUST)}" in denied.reason

    allowed = await engine.check_operation(
        agent_id="test-agent",
        agent_type="claude_code",
        operation="acquire_lock",
        context={"trust_level": int(MIN_WRITE_TRUST)},
    )
    assert allowed.allowed is True


@pytest.mark.asyncio
async def test_admin_boundary_matches_min_admin_trust(mock_supabase, db_client) -> None:  # type: ignore[no-untyped-def]
    engine = NativePolicyEngine(db_client)

    denied = await engine.check_operation(
        agent_id="test-agent",
        agent_type="claude_code",
        operation="force_push",
        context={"trust_level": int(MIN_ADMIN_TRUST) - 1},
    )
    assert denied.allowed is False
    assert f"< {int(MIN_ADMIN_TRUST)}" in denied.reason

    allowed = await engine.check_operation(
        agent_id="test-agent",
        agent_type="claude_code",
        operation="force_push",
        context={"trust_level": int(MIN_ADMIN_TRUST)},
    )
    assert allowed.allowed is True


@pytest.mark.asyncio
async def test_untrusted_is_denied_everything(mock_supabase, db_client) -> None:  # type: ignore[no-untyped-def]
    engine = NativePolicyEngine(db_client)

    result = await engine.check_operation(
        agent_id="test-agent",
        agent_type="claude_code",
        operation="check_locks",
        context={"trust_level": int(TrustLevel.UNTRUSTED)},
    )
    assert result.allowed is False
    assert "agent_suspended" in result.reason


# ---------------------------------------------------------------------------
# Migration — asserted on SQL text (no DB in this environment)
# ---------------------------------------------------------------------------


CONSTRAINT_NAME = "agent_profiles_trust_level_check"


def _find_trust_scale_migration() -> Path:
    candidates = sorted(MIGRATIONS_DIR.glob("*_unified_trust_scale.sql"))
    assert candidates, (
        "Expected a migration matching '*_unified_trust_scale.sql' under "
        f"{MIGRATIONS_DIR} (task 1.3)."
    )
    assert len(candidates) == 1, f"Multiple trust-scale migrations found: {candidates}"
    return candidates[0]


def _sequence_number(name: str) -> int:
    match = re.match(r"^(\d+)_", name)
    assert match, f"Migration filename {name!r} does not start with NNN_"
    return int(match.group(1))


def test_migration_exists() -> None:
    assert _find_trust_scale_migration().is_file()


def test_migration_sequence_number_is_unique() -> None:
    target = _find_trust_scale_migration()
    others = [
        _sequence_number(p.name) for p in MIGRATIONS_DIR.glob("*.sql") if p != target
    ]
    assert _sequence_number(target.name) not in others, (
        "Trust-scale migration sequence number collides with another migration"
    )


def test_migration_check_bounds_equal_module_bounds() -> None:
    """The contracted assertion: DB constraint bounds == module bounds."""
    sql = _find_trust_scale_migration().read_text(encoding="utf-8")
    match = re.search(
        r"CHECK\s*\(\s*trust_level\s*>=\s*(-?\d+)\s+AND\s+trust_level\s*<=\s*(-?\d+)\s*\)",
        sql,
        flags=re.IGNORECASE,
    )
    assert match, (
        "Migration MUST contain `CHECK (trust_level >= <min> AND trust_level <= <max>)`"
    )
    low, high = int(match.group(1)), int(match.group(2))
    assert (low, high) == (MIN_TRUST, MAX_TRUST), (
        f"Migration CHECK bounds ({low}, {high}) diverge from src/trust_levels.py "
        f"({MIN_TRUST}, {MAX_TRUST})"
    )


def test_migration_uses_stable_constraint_name() -> None:
    sql = _find_trust_scale_migration().read_text(encoding="utf-8")
    assert re.search(
        rf"ADD\s+CONSTRAINT\s+{CONSTRAINT_NAME}\b", sql, flags=re.IGNORECASE
    ), f"Migration MUST add the constraint under the stable name {CONSTRAINT_NAME!r}"
    assert re.search(
        rf"DROP\s+CONSTRAINT\s+IF\s+EXISTS\s+{CONSTRAINT_NAME}\b", sql, flags=re.IGNORECASE
    ), "Migration MUST drop the prior constraint first so re-statement is idempotent"


def test_migration_adds_registry_sync_column() -> None:
    sql = _find_trust_scale_migration().read_text(encoding="utf-8")
    assert re.search(
        r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+synced_from_registry_at\s+TIMESTAMPTZ",
        sql,
        flags=re.IGNORECASE,
    ), "Migration MUST add `synced_from_registry_at TIMESTAMPTZ` (DB contract)"


def test_migration_ships_paired_down_migration() -> None:
    """Design D8: rollback levers ship with the change."""
    sql = _find_trust_scale_migration().read_text(encoding="utf-8")
    tail = sql[sql.lower().rfind("-- down migration") :]
    assert tail, "Migration MUST end with a commented-out `-- Down migration` block"
    assert re.search(
        r"^--\s*ALTER\s+TABLE\s+agent_profiles\s+DROP\s+COLUMN\s+IF\s+EXISTS\s+"
        r"synced_from_registry_at",
        tail,
        flags=re.IGNORECASE | re.MULTILINE,
    ), "Down migration MUST include the commented DROP COLUMN for synced_from_registry_at"


def test_migration_does_not_narrow_existing_rows() -> None:
    """007's constraint is already 0..4; the migration MUST NOT delete/update rows."""
    sql = _find_trust_scale_migration().read_text(encoding="utf-8")
    statements = [
        line.strip()
        for line in sql.splitlines()
        if line.strip() and not line.strip().startswith("--")
    ]
    body = " ".join(statements).upper()
    assert "DELETE FROM" not in body
    assert "UPDATE AGENT_PROFILES" not in body

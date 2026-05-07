"""Tests for the phase_archetype migration in agent-coordinator/database/migrations/.

This change-set is `wire-autopilot-phase-subagents` (closes deferred D-1).

The migration adds three things to `agent_sessions`:
1. A new `phase_archetype TEXT` column with a CHECK constraint enforcing the
   archetype enum (`architect | reviewer | implementer | analyst | runner`)
   and a 64-character upper bound aligned with the API ``max_length=64``.
2. ``CREATE OR REPLACE FUNCTION discover_agents`` that surfaces the new
   column in the JSONB response (the existing function builds its agent
   dicts by hand, so a column addition would otherwise be invisible).
3. ``CREATE OR REPLACE FUNCTION agent_heartbeat`` that accepts an optional
   ``p_phase_archetype`` parameter and persists it via
   ``COALESCE(p_phase_archetype, phase_archetype)``, so older callers that
   don't pass the value never overwrite an existing one with NULL.

These tests assert the migration file landed correctly (static analysis)
without requiring a running Postgres container — the sibling
``tests/integration/`` tests cover live database behaviour.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS_DIR = (
    Path(__file__).resolve().parent.parent / "database" / "migrations"
)


def _find_phase_archetype_migration() -> Path:
    """Locate the wire-autopilot migration in the canonical directory."""
    candidates = sorted(MIGRATIONS_DIR.glob("*_add_phase_archetype.sql"))
    assert candidates, (
        "Expected a migration file matching '*_add_phase_archetype.sql' under "
        f"{MIGRATIONS_DIR}. The implementer of wp-coordinator-status-discovery "
        "must commit the migration with the next available sequence number "
        "(max+1) per the wire-autopilot-phase-subagents proposal."
    )
    assert len(candidates) == 1, (
        f"Multiple add_phase_archetype migrations found: {candidates}. "
        "There should be exactly one — pick the next sequence and remove duplicates."
    )
    return candidates[0]


def _parse_sequence_number(name: str) -> int:
    match = re.match(r"^(\d+)_", name)
    assert match, f"Migration filename {name!r} does not start with NNN_"
    return int(match.group(1))


# ---------------------------------------------------------------------------
# Filename and sequencing
# ---------------------------------------------------------------------------


def test_migration_file_exists_with_expected_naming() -> None:
    """The migration MUST exist with a phase_archetype-related filename."""
    path = _find_phase_archetype_migration()
    assert path.is_file(), f"{path} should be a regular file"


def test_migration_uses_next_available_sequence_number() -> None:
    """Migration sequence number MUST be max(existing) + 1.

    Per Phase 3.2 of the wire-autopilot-phase-subagents tasks: ``apply the
    migration into agent-coordinator/database/migrations/ with the next
    available sequence number``.
    """
    target = _find_phase_archetype_migration()
    other_seqs = [
        _parse_sequence_number(p.name)
        for p in MIGRATIONS_DIR.glob("*.sql")
        if p != target
    ]
    target_seq = _parse_sequence_number(target.name)
    assert target_seq == max(other_seqs) + 1, (
        f"Expected sequence {max(other_seqs) + 1}, got {target_seq}. "
        "If a parallel PR landed a migration first, rebase and renumber."
    )


# ---------------------------------------------------------------------------
# Step 1 — ALTER TABLE adding the column with CHECK constraint
# ---------------------------------------------------------------------------


def test_migration_adds_phase_archetype_column() -> None:
    sql = _find_phase_archetype_migration().read_text()
    # Use a tolerant pattern: ALTER TABLE agent_sessions ADD COLUMN [IF NOT EXISTS] phase_archetype TEXT
    pattern = re.compile(
        r"ALTER\s+TABLE\s+agent_sessions\s+"
        r"ADD\s+COLUMN(?:\s+IF\s+NOT\s+EXISTS)?\s+"
        r"phase_archetype\s+TEXT",
        re.IGNORECASE,
    )
    assert pattern.search(sql), (
        "Migration MUST contain `ALTER TABLE agent_sessions ADD COLUMN "
        "phase_archetype TEXT`"
    )


def test_migration_check_constraint_enforces_enum() -> None:
    sql = _find_phase_archetype_migration().read_text()
    # All five archetype values MUST be referenced in a CHECK clause.
    archetypes = ("architect", "reviewer", "implementer", "analyst", "runner")
    # Locate the CHECK clause (case-insensitive)
    check_match = re.search(
        r"CHECK\s*\([^)]*?phase_archetype.*?\)",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert check_match, "Migration MUST contain a CHECK clause referencing phase_archetype"
    check_body = check_match.group(0)
    for archetype in archetypes:
        assert f"'{archetype}'" in check_body, (
            f"CHECK constraint MUST allow archetype {archetype!r}; got:\n{check_body}"
        )


def test_migration_allows_null_phase_archetype() -> None:
    """Existing rows MUST keep their pre-migration NULL state — no backfill."""
    sql = _find_phase_archetype_migration().read_text()
    # CHECK clause MUST permit NULL (either explicitly or via the standard
    # ``phase_archetype IS NULL OR ...`` idiom).
    pattern = re.compile(
        r"phase_archetype\s+IS\s+NULL\s+OR",
        flags=re.IGNORECASE,
    )
    assert pattern.search(sql), (
        "CHECK constraint MUST explicitly allow NULL via `phase_archetype IS NULL OR ...`"
    )


def test_migration_does_not_backfill_existing_rows() -> None:
    """The migration MUST NOT contain a top-level (non-function) UPDATE that
    sets ``phase_archetype`` against existing rows.

    UPDATE inside ``CREATE OR REPLACE FUNCTION agent_heartbeat`` is fine — that
    runs at heartbeat time, not migration time. We only fail on UPDATEs at
    the migration's top level (between BEGIN and COMMIT, outside any function
    definition).

    Per spec: existing rows have ``phase_archetype = NULL`` post-migration.
    """
    sql = _find_phase_archetype_migration().read_text()
    # Strip every CREATE OR REPLACE FUNCTION ... $$ LANGUAGE block so we can
    # inspect only top-level statements.
    sql_no_funcs = re.sub(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION.*?\$\$\s+LANGUAGE\s+\w+\s*;",
        "",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    update_pattern = re.compile(
        r"UPDATE\s+agent_sessions\s+SET\s+.*?phase_archetype",
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert not update_pattern.search(sql_no_funcs), (
        "Migration MUST NOT UPDATE agent_sessions.phase_archetype at the top "
        "level (no backfill required — function-internal UPDATEs are fine)"
    )


# ---------------------------------------------------------------------------
# Step 2 — discover_agents() RPC update
# ---------------------------------------------------------------------------


def test_migration_updates_discover_agents_rpc_to_include_phase_archetype() -> None:
    sql = _find_phase_archetype_migration().read_text()
    # The CREATE OR REPLACE FUNCTION block for discover_agents MUST
    # include 'phase_archetype' in its jsonb_build_object output.
    func_match = re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+discover_agents.*?\$\$\s+LANGUAGE",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert func_match, (
        "Migration MUST include `CREATE OR REPLACE FUNCTION discover_agents` "
        "(the existing function builds its JSONB payload by hand, so a column "
        "addition is otherwise invisible to /discovery/agents consumers — "
        "see codex review R1-004)"
    )
    body = func_match.group(0)
    assert "'phase_archetype'" in body, (
        "discover_agents JSONB output MUST include 'phase_archetype' key"
    )
    # And the value should reference the column on the agent_sessions row.
    assert re.search(r"phase_archetype['\"]?\s*,\s*[a-z]+\.phase_archetype", body), (
        "discover_agents JSONB value MUST reference the new column via "
        "`<alias>.phase_archetype`"
    )


# ---------------------------------------------------------------------------
# Step 3 — agent_heartbeat() RPC update
# ---------------------------------------------------------------------------


def test_migration_updates_agent_heartbeat_rpc_to_accept_phase_archetype() -> None:
    sql = _find_phase_archetype_migration().read_text()
    func_match = re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+agent_heartbeat.*?\$\$\s+LANGUAGE",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert func_match, "Migration MUST include `CREATE OR REPLACE FUNCTION agent_heartbeat`"
    body = func_match.group(0)
    # Signature MUST include p_phase_archetype with a default of NULL so older
    # callers that pass only (p_session_id, p_agent_id) continue to work.
    assert re.search(
        r"p_phase_archetype\s+TEXT\s+DEFAULT\s+NULL",
        body,
        flags=re.IGNORECASE,
    ), (
        "agent_heartbeat MUST add `p_phase_archetype TEXT DEFAULT NULL` to its "
        "signature so existing callers without the parameter remain compatible"
    )


def test_migration_agent_heartbeat_uses_coalesce_to_preserve_value() -> None:
    """COALESCE prevents heartbeats with NULL p_phase_archetype from clearing the column."""
    sql = _find_phase_archetype_migration().read_text()
    func_match = re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+agent_heartbeat.*?\$\$\s+LANGUAGE",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert func_match
    body = func_match.group(0)
    assert re.search(
        r"COALESCE\s*\(\s*p_phase_archetype\s*,\s*phase_archetype\s*\)",
        body,
        flags=re.IGNORECASE,
    ), (
        "agent_heartbeat MUST use `COALESCE(p_phase_archetype, phase_archetype)` "
        "so a heartbeat that doesn't pass the value preserves the existing one"
    )


def test_migration_agent_heartbeat_validates_enum_or_check_constraint_blocks() -> None:
    """Either the function validates the enum OR the CHECK constraint will reject.

    Defense-in-depth: the migration's authoritative contract relies on the
    CHECK constraint, but the contract file also adds an inline validation
    block in agent_heartbeat. We assert one path or the other exists.
    """
    sql = _find_phase_archetype_migration().read_text()
    func_match = re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+agent_heartbeat.*?\$\$\s+LANGUAGE",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert func_match
    body = func_match.group(0)
    enum_in_function = (
        "'architect'" in body
        and "'reviewer'" in body
        and "'implementer'" in body
    )
    # CHECK constraint already validated above — both gates is the contract,
    # but if only the CHECK exists the heartbeat will fail at COMMIT time.
    # We require at least the CHECK constraint (asserted in earlier test);
    # this test additionally documents that the function's enum validation is
    # present.
    assert enum_in_function, (
        "agent_heartbeat MUST validate phase_archetype against the archetype enum "
        "before UPDATE, returning a structured `invalid_phase_archetype` error "
        "instead of letting the CHECK constraint raise at COMMIT time"
    )


# ---------------------------------------------------------------------------
# RPC alignment — runtime call sites match the new signature
# ---------------------------------------------------------------------------


def test_discover_agents_rpc_remains_resolvable_via_alignment_check() -> None:
    """The migration's discover_agents function MUST still satisfy the
    test_rpc_migration_alignment.py contract that runtime ``.rpc("discover_agents")``
    calls find a matching CREATE FUNCTION.
    """
    # We don't re-run the alignment test here; we only assert the function
    # name is unchanged so that test still passes after our migration lands.
    sql = _find_phase_archetype_migration().read_text()
    assert "FUNCTION discover_agents" in sql.replace(
        "CREATE OR REPLACE FUNCTION ", "FUNCTION "
    )


# ---------------------------------------------------------------------------
# Bracketing parameterized tests for archetype enum membership
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "archetype",
    ["architect", "reviewer", "implementer", "analyst", "runner"],
)
def test_each_archetype_value_appears_in_check_constraint(archetype: str) -> None:
    sql = _find_phase_archetype_migration().read_text()
    assert f"'{archetype}'" in sql, (
        f"Archetype {archetype!r} MUST appear in the migration's CHECK constraint"
    )


@pytest.mark.parametrize(
    "rejected_value",
    ["unknown", "ADMIN", "wizard", "", " architect "],
)
def test_check_constraint_does_not_accidentally_allow_other_values(
    rejected_value: str,
) -> None:
    """The CHECK should be a closed enum, not a regex/pattern match."""
    sql = _find_phase_archetype_migration().read_text()
    # We cannot run the SQL here, but we can assert the constraint uses
    # `IN (...)` — a closed-set check — rather than `LIKE` or a regex.
    check_match = re.search(
        r"CHECK\s*\([^)]*phase_archetype.*?\)",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert check_match
    body = check_match.group(0)
    # `IN (...)` proves it's a closed set; reject patterns based on LIKE/~/SIMILAR TO.
    assert re.search(
        r"phase_archetype\s+IN\s*\(",
        body,
        flags=re.IGNORECASE,
    ), "CHECK MUST use closed-set IN (...) — open patterns reject defense-in-depth"
    assert "LIKE" not in body.upper().replace("ALIKE", ""), (
        "CHECK MUST NOT use LIKE (would accept partial matches)"
    )
    assert "SIMILAR TO" not in body.upper(), "CHECK MUST NOT use SIMILAR TO regex"
    # Sanity: the rejected value isn't smuggled into the constraint.
    assert f"'{rejected_value}'" not in body, (
        f"Rejected value {rejected_value!r} appears in the CHECK constraint"
    )

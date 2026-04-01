"""Tests for seed data validity.

Validates seed.sql without requiring a running database by parsing the SQL
text for structural correctness, table coverage, idempotency, and minimum
row counts per table.

Spec reference: LST.4 (Seed Data)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEED_SQL_PATH = (
    Path(__file__).resolve().parents[4]
    / "agent-coordinator"
    / "supabase"
    / "seed.sql"
)

# The 7 cleanable tables that must be seeded (from conftest.py _TABLES).
REQUIRED_TABLES = {
    "agent_sessions",
    "file_locks",
    "work_queue",
    "memory_episodic",
    "memory_working",
    "memory_procedural",
    "handoff_documents",
}

# Minimum number of INSERT value-groups per table (from spec LST.4).
MIN_ROWS: dict[str, int] = {
    "agent_sessions": 2,
    "file_locks": 1,
    "work_queue": 2,
    "memory_episodic": 1,
    "memory_working": 1,
    "memory_procedural": 1,
    "handoff_documents": 1,
}

# ParadeDB-only types that must NOT appear in seed data.
PARADEDB_TYPES = {"bm25", "paradedb", "pg_search"}


def _read_seed_sql() -> str:
    """Return the full text of seed.sql."""
    assert SEED_SQL_PATH.exists(), f"seed.sql not found at {SEED_SQL_PATH}"
    return SEED_SQL_PATH.read_text()


def _extract_insert_statements(sql: str) -> list[tuple[str, str]]:
    """Return (table_name, full_statement) pairs for every INSERT in *sql*."""
    # Match INSERT INTO <table> ... up to the next semicolon.
    pattern = re.compile(
        r"INSERT\s+INTO\s+(\w+)\s*\(.*?\)\s*VALUES\s*(.+?);",
        re.IGNORECASE | re.DOTALL,
    )
    return [(m.group(1).lower(), m.group(0)) for m in pattern.finditer(sql)]


def _count_value_groups(values_clause: str) -> int:
    """Count the number of ``(...)`` value groups in a VALUES clause.

    Each top-level ``(...)`` group corresponds to one row.  Nested parens
    (e.g. inside function calls or sub-expressions) are handled by tracking
    depth.
    """
    # Extract the VALUES portion from the full INSERT statement.
    values_match = re.search(r"VALUES\s*(.+)", values_clause, re.IGNORECASE | re.DOTALL)
    if not values_match:
        return 0

    text = values_match.group(1)
    count = 0
    depth = 0
    in_string = False
    escape_next = False

    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == "'":
            in_string = not in_string
            continue
        if in_string:
            if ch == "\\":
                escape_next = True
            continue
        if ch == "(":
            if depth == 0:
                count += 1
            depth += 1
        elif ch == ")":
            depth -= 1

    return count


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSeedCoversAllTables:
    """LST.4: seed.sql must contain INSERT statements for all 7 tables."""

    def test_seed_covers_all_tables(self) -> None:
        sql = _read_seed_sql()
        inserts = _extract_insert_statements(sql)
        tables_present = {table for table, _ in inserts}
        missing = REQUIRED_TABLES - tables_present
        assert not missing, f"Missing INSERT for tables: {missing}"


class TestSeedIsIdempotent:
    """LST.4: every INSERT must use ON CONFLICT DO NOTHING."""

    def test_seed_is_idempotent(self) -> None:
        sql = _read_seed_sql()
        inserts = _extract_insert_statements(sql)
        assert inserts, "No INSERT statements found in seed.sql"

        for table, stmt in inserts:
            assert re.search(
                r"ON\s+CONFLICT\s+.*?DO\s+NOTHING", stmt, re.IGNORECASE | re.DOTALL
            ), f"INSERT into '{table}' is missing ON CONFLICT DO NOTHING"


class TestSeedMinimumRows:
    """LST.4: each table must have the specified minimum row count."""

    @pytest.mark.parametrize("table,min_count", list(MIN_ROWS.items()))
    def test_seed_minimum_rows(self, table: str, min_count: int) -> None:
        sql = _read_seed_sql()
        inserts = _extract_insert_statements(sql)
        stmts_for_table = [stmt for t, stmt in inserts if t == table]
        total_rows = sum(_count_value_groups(s) for s in stmts_for_table)
        assert total_rows >= min_count, (
            f"Table '{table}' has {total_rows} seed rows, expected >= {min_count}"
        )


class TestSeedSqlSyntax:
    """Basic SQL syntax validation (no DB required)."""

    def test_seed_sql_syntax(self) -> None:
        sql = _read_seed_sql()
        # Every statement should end with a semicolon (ignoring comments/blanks).
        # Strip SQL comments and blank lines, then check that non-empty
        # content consists of semicolon-terminated statements.
        stripped = re.sub(r"--[^\n]*", "", sql)  # remove line comments
        stripped = stripped.strip()
        assert stripped, "seed.sql is empty after stripping comments"
        # All INSERT statements should be terminated.
        inserts = _extract_insert_statements(sql)
        assert len(inserts) >= len(REQUIRED_TABLES), (
            f"Expected at least {len(REQUIRED_TABLES)} INSERT statements, "
            f"found {len(inserts)}"
        )

    def test_no_paradedb_specific_types(self) -> None:
        """seed.sql must not reference ParadeDB-only types."""
        sql = _read_seed_sql().lower()
        for t in PARADEDB_TYPES:
            assert t not in sql, f"seed.sql references ParadeDB-only type: {t}"

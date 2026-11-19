"""Text checks for the gate projection migration (047).

The table is a cache of what repositories report, so the checks pin the
properties that make it disposable: one row per project, the whole snapshot
in one column, and no column that could hold a decision.
"""

from __future__ import annotations

from pathlib import Path

MIGRATION = (
    Path(__file__).parents[1] / "database/migrations/047_gate_projection.sql"
)


def _sql() -> str:
    return MIGRATION.read_text()


def test_migration_creates_one_row_per_project() -> None:
    sql = _sql()
    assert "CREATE TABLE IF NOT EXISTS gate_projection_snapshots" in sql
    assert "project TEXT PRIMARY KEY" in sql


def test_migration_stores_the_snapshot_whole() -> None:
    sql = _sql()
    assert "payload JSONB NOT NULL" in sql
    assert "collected_at TIMESTAMPTZ NOT NULL" in sql
    assert "received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()" in sql
    assert "digest TEXT NOT NULL" in sql


def test_migration_holds_no_decision_columns() -> None:
    body = _sql().split("BEGIN;", 1)[1].lower()
    for column in ("decided_by", "decided_at", "decision", "status"):
        assert column not in body


def test_migration_is_transactional_and_repeatable() -> None:
    sql = _sql()
    assert "BEGIN;" in sql
    assert sql.rstrip().endswith("COMMIT;")
    assert "DROP TABLE" not in sql

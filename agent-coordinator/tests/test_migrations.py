"""Tests for the schema migration runner."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.migrations import (
    _checksum,
    _unwrap_explicit_transaction,
    discover_migrations,
    run_migrations,
)

_COORDINATOR_ROOT = Path(__file__).resolve().parents[1]
_REPOSITORY_ROOT = _COORDINATOR_ROOT.parent
_TRACKING_SCRIPT = _COORDINATOR_ROOT / "database/migrations/999_record_schema_migrations.sh"
_CI_WORKFLOW = _REPOSITORY_ROOT / ".github/workflows/ci.yml"

# ---------------------------------------------------------------------------
# discover_migrations
# ---------------------------------------------------------------------------


def test_discover_migrations_ordering(tmp_path: Path) -> None:
    """Migrations are discovered and sorted by sequence number."""
    (tmp_path / "002_second.sql").write_text("SELECT 2;")
    (tmp_path / "000_first.sql").write_text("SELECT 0;")
    (tmp_path / "001_middle.sql").write_text("SELECT 1;")
    # Non-migration files should be ignored
    (tmp_path / "README.md").write_text("not a migration")
    (tmp_path / "backup.sql.bak").write_text("not a migration")

    result = discover_migrations(tmp_path)
    assert len(result) == 3
    assert [r[0] for r in result] == [0, 1, 2]
    assert [r[1] for r in result] == ["000_first.sql", "001_middle.sql", "002_second.sql"]


def test_discover_migrations_empty_dir(tmp_path: Path) -> None:
    """Empty directory returns empty list."""
    assert discover_migrations(tmp_path) == []


def test_discover_migrations_missing_dir(tmp_path: Path) -> None:
    """Missing directory returns empty list with warning."""
    assert discover_migrations(tmp_path / "nonexistent") == []


def test_discover_migrations_ignores_directories(tmp_path: Path) -> None:
    """Subdirectories matching the pattern are ignored."""
    (tmp_path / "001_subdir.sql").mkdir()
    (tmp_path / "002_real.sql").write_text("SELECT 1;")
    result = discover_migrations(tmp_path)
    assert len(result) == 1
    assert result[0][1] == "002_real.sql"


def test_discover_migrations_ignores_shell_tracking_script(tmp_path: Path) -> None:
    """The Python runner discovers SQL migrations only, never entrypoint helpers."""
    (tmp_path / "001_schema.sql").write_text("SELECT 1;")
    (tmp_path / "999_record_schema_migrations.sh").write_text("#!/usr/bin/env bash\n")

    assert [item[1] for item in discover_migrations(tmp_path)] == ["001_schema.sql"]


def _render_tracking_sql(migrations_dir: Path, tmp_path: Path) -> str:
    fake_psql = tmp_path / "fake-psql"
    fake_psql.write_text("#!/usr/bin/env bash\ncat\n")
    fake_psql.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "COORDINATOR_MIGRATIONS_DIR": str(migrations_dir),
            "PSQL_BIN": str(fake_psql),
            "POSTGRES_USER": "postgres",
            "POSTGRES_DB": "postgres",
        }
    )
    result = subprocess.run(
        ["bash", str(_TRACKING_SCRIPT)],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    return result.stdout


def test_tracking_script_discovers_sql_hashes_and_is_idempotent(tmp_path: Path) -> None:
    """The final init script records every SQL file with Python-compatible hashes."""
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    first = migrations_dir / "001_first.sql"
    second = migrations_dir / "002_second.sql"
    first.write_text("SELECT 1;\n")
    second.write_text("SELECT 'two';\n")
    (migrations_dir / "999_ignored.sh").write_text("exit 1\n")

    rendered_once = _render_tracking_sql(migrations_dir, tmp_path)
    rendered_twice = _render_tracking_sql(migrations_dir, tmp_path)
    recorded = dict(
        re.findall(
            r"VALUES \('([^']+)', '([0-9a-f]{64})'\)",
            rendered_once,
        )
    )

    assert rendered_once == rendered_twice
    assert recorded == {
        first.name: _checksum(first.read_text()),
        second.name: _checksum(second.read_text()),
    }
    assert rendered_once.count("ON CONFLICT (filename) DO UPDATE") == 2
    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in rendered_once
    assert rendered_once.startswith("BEGIN;")
    assert rendered_once.rstrip().endswith("COMMIT;")


def test_tracking_script_runs_only_after_fail_fast_ci_sql_loop() -> None:
    """A failed SQL migration prevents CI from falsely recording later files."""
    workflow = _CI_WORKFLOW.read_text()
    step_start = workflow.index("      - name: Apply database migrations")
    step_end = workflow.index("      - name:", step_start + 10)
    step = workflow[step_start:step_end]

    assert "set -euo pipefail" in step
    assert "psql -v ON_ERROR_STOP=1" in step
    assert step.index("for f in") < step.index("psql -v ON_ERROR_STOP=1")
    assert step.index("psql -v ON_ERROR_STOP=1") < step.index("done")
    script_call = "bash agent-coordinator/database/migrations/999_record_schema_migrations.sh"
    assert step.index("done") < step.index(script_call)
    assert step.count(script_call) == 1
    assert _TRACKING_SCRIPT.name > max(
        path.name for path in _TRACKING_SCRIPT.parent.glob("*.sql")
    )
    assert os.access(_TRACKING_SCRIPT, os.X_OK)


# ---------------------------------------------------------------------------
# checksum
# ---------------------------------------------------------------------------


def test_checksum_deterministic() -> None:
    """Same content produces same checksum."""
    assert _checksum("SELECT 1;") == _checksum("SELECT 1;")


def test_checksum_differs() -> None:
    """Different content produces different checksums."""
    assert _checksum("SELECT 1;") != _checksum("SELECT 2;")


# ---------------------------------------------------------------------------
# explicit transaction normalization
# ---------------------------------------------------------------------------


def test_unwrap_explicit_transaction_for_runner_owned_atomicity() -> None:
    """Explicit psql boundaries are removed inside the asyncpg transaction."""
    sql = "-- migration\nBEGIN;\nLOCK TABLE work_queue;\nSELECT 1;\nCOMMIT;\n"

    assert _unwrap_explicit_transaction(sql) == (
        "-- migration\n\nLOCK TABLE work_queue;\nSELECT 1;\n\n"
    )


def test_unwrap_preserves_migrations_without_explicit_boundaries() -> None:
    """Legacy migrations continue to execute byte-for-byte."""
    sql = "CREATE TABLE example (id INTEGER);\n"

    assert _unwrap_explicit_transaction(sql) == sql


@pytest.mark.asyncio()
async def test_run_migrations_does_not_record_bootstrap_syntax_failure(tmp_path: Path) -> None:
    """A broken migration is never recorded merely because the DB was bootstrapped."""
    import asyncpg

    (tmp_path / "035_broken.sql").write_text("BROKEN SQL")
    mock_conn = _make_mock_conn()
    mock_conn.execute.side_effect = [None, asyncpg.PostgresSyntaxError("bad syntax")]

    with patch("asyncpg.connect", AsyncMock(return_value=mock_conn)):
        with pytest.raises(asyncpg.PostgresSyntaxError):
            await run_migrations("postgresql://test", migrations_dir=tmp_path)

    assert all(
        not call.args[0].startswith("INSERT INTO schema_migrations")
        for call in mock_conn.execute.await_args_list
    )


# ---------------------------------------------------------------------------
# run_migrations
# ---------------------------------------------------------------------------


class _FakeTransaction:
    """Minimal async context manager to stand in for asyncpg.Transaction."""

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        pass


def _make_mock_conn(applied: list[dict[str, str]] | None = None) -> AsyncMock:
    """Create a mock asyncpg connection with a working transaction() stub."""
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = applied or []
    # transaction() is a sync method that returns an async context manager
    mock_conn.transaction = MagicMock(return_value=_FakeTransaction())
    return mock_conn


@pytest.fixture()
def migration_dir(tmp_path: Path) -> Path:
    """Create a temporary migrations directory with test files."""
    (tmp_path / "000_bootstrap.sql").write_text("CREATE TABLE t1 (id INT);")
    (tmp_path / "001_second.sql").write_text("CREATE TABLE t2 (id INT);")
    (tmp_path / "002_third.sql").write_text("CREATE TABLE t3 (id INT);")
    return tmp_path


@pytest.mark.asyncio()
async def test_run_migrations_applies_all(migration_dir: Path) -> None:
    """All migrations are applied when none have been applied before."""
    mock_conn = _make_mock_conn()

    with patch("asyncpg.connect", AsyncMock(return_value=mock_conn)):
        result = await run_migrations("postgresql://test", migrations_dir=migration_dir)

    assert result == ["000_bootstrap.sql", "001_second.sql", "002_third.sql"]
    # bootstrap SQL + 3 migrations (each: execute content + insert record) + fetch
    assert mock_conn.execute.call_count >= 4  # bootstrap + 3 content executions
    assert mock_conn.close.await_count == 1


@pytest.mark.asyncio()
async def test_run_migrations_skips_applied(migration_dir: Path) -> None:
    """Already-applied migrations are skipped."""
    content_000 = (migration_dir / "000_bootstrap.sql").read_text()
    mock_conn = _make_mock_conn([
        {"filename": "000_bootstrap.sql", "checksum": _checksum(content_000)},
    ])

    with patch("asyncpg.connect", AsyncMock(return_value=mock_conn)):
        result = await run_migrations("postgresql://test", migrations_dir=migration_dir)

    assert result == ["001_second.sql", "002_third.sql"]


@pytest.mark.asyncio()
async def test_run_migrations_dry_run(migration_dir: Path) -> None:
    """Dry run reports migrations without executing them."""
    mock_conn = _make_mock_conn()

    with patch("asyncpg.connect", AsyncMock(return_value=mock_conn)):
        result = await run_migrations(
            "postgresql://test", migrations_dir=migration_dir, dry_run=True
        )

    assert result == ["000_bootstrap.sql", "001_second.sql", "002_third.sql"]
    # Only bootstrap SQL should be executed (tracking table), no migration content
    assert mock_conn.execute.call_count == 1  # Just the bootstrap


@pytest.mark.asyncio()
async def test_run_migrations_checksum_mismatch(migration_dir: Path) -> None:
    """Checksum mismatch logs warning and skips the migration."""
    mock_conn = _make_mock_conn([
        {"filename": "000_bootstrap.sql", "checksum": "stale-checksum"},
    ])

    with patch("asyncpg.connect", AsyncMock(return_value=mock_conn)):
        result = await run_migrations("postgresql://test", migrations_dir=migration_dir)

    # 000 is skipped (mismatch), 001 and 002 are applied
    assert result == ["001_second.sql", "002_third.sql"]


@pytest.mark.asyncio()
async def test_run_migrations_idempotent(migration_dir: Path) -> None:
    """Running twice with all migrations applied returns empty list."""
    all_files = sorted(migration_dir.glob("*.sql"))
    applied = [
        {"filename": f.name, "checksum": _checksum(f.read_text())}
        for f in all_files
    ]
    mock_conn = _make_mock_conn(applied)

    with patch("asyncpg.connect", AsyncMock(return_value=mock_conn)):
        result = await run_migrations("postgresql://test", migrations_dir=migration_dir)

    assert result == []


# ---------------------------------------------------------------------------
# ensure_schema (integration with config)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_ensure_schema_skips_supabase_backend() -> None:
    """ensure_schema returns empty list for supabase backend."""
    from src.migrations import ensure_schema

    mock_config = MagicMock()
    mock_config.database.backend = "supabase"

    with patch("src.config.get_config", return_value=mock_config):
        result = await ensure_schema()

    assert result == []


# ---------------------------------------------------------------------------
# Migration 036 static contract (terminal completion guard)
# ---------------------------------------------------------------------------


def test_migration_036_makes_cancellation_terminal_against_late_completions() -> None:
    """complete_task must never overwrite a non-active (e.g. cancelled) row.

    This is a static, DB-less check of the migration content — the
    PostgreSQL-backed behavioural coverage lives in
    tests/integration/postgres/test_work_queue_postgres.py
    (TestCompleteTaskTerminalCancellation), which is skipped in this
    environment without a live database.
    """
    sql = (
        _COORDINATOR_ROOT / "database/migrations/036_terminal_completion_guard.sql"
    ).read_text()

    assert "CREATE OR REPLACE FUNCTION complete_task(" in sql
    # The UPDATE that flips a task terminal must be scoped to active statuses
    # only, so a row already cancelled by projection reconciliation can never
    # be overwritten by a late worker call.
    assert "AND status IN ('claimed', 'running')" in sql
    # A refused completion must report *why*, distinguishing "already
    # terminal" from "not found / not claimed by this agent".
    assert "'task_not_active'" in sql
    assert "'task_not_found_or_not_claimed_by_agent'" in sql


@pytest.mark.asyncio()
async def test_ensure_schema_skips_missing_dsn() -> None:
    """ensure_schema returns empty list when DSN is not set."""
    from src.migrations import ensure_schema

    mock_config = MagicMock()
    mock_config.database.backend = "postgres"
    mock_config.database.postgres.dsn = ""

    with patch("src.config.get_config", return_value=mock_config):
        result = await ensure_schema()

    assert result == []

"""Tests for the schema migration runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.migrations import _checksum, discover_migrations, run_migrations

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

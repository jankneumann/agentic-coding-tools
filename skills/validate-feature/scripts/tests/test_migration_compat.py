"""Tests for migration compatibility on standard PostgreSQL.

Validates that migration files handle extensions gracefully so they work
on both ParadeDB and standard PostgreSQL.

Spec reference: LST.5 (Migration Compatibility)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[4]
    / "agent-coordinator"
    / "supabase"
    / "migrations"
)

SEED_SQL_PATH = (
    Path(__file__).resolve().parents[4]
    / "agent-coordinator"
    / "supabase"
    / "seed.sql"
)

# Extensions that require graceful degradation on standard PostgreSQL.
PARADEDB_EXTENSIONS = {"pg_search", "pg_analytics", "pg_lakehouse"}

# ParadeDB-only types/features that should not appear in seed data.
PARADEDB_TYPES = {"bm25", "paradedb\\."}


def _migration_files() -> list[Path]:
    """Return all .sql migration files sorted by name."""
    assert MIGRATIONS_DIR.exists(), f"Migrations dir not found: {MIGRATIONS_DIR}"
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    assert files, "No migration files found"
    return files


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMigrationsUseIfNotExistsForExtensions:
    """LST.5: CREATE EXTENSION must always use IF NOT EXISTS."""

    def test_migrations_use_if_not_exists_for_extensions(self) -> None:
        for path in _migration_files():
            sql = path.read_text()
            # Find all CREATE EXTENSION statements.
            creates = list(
                re.finditer(r"CREATE\s+EXTENSION\b", sql, re.IGNORECASE)
            )
            for match in creates:
                # The surrounding text should include IF NOT EXISTS.
                context = sql[match.start() : match.start() + 200]
                assert re.search(
                    r"IF\s+NOT\s+EXISTS", context, re.IGNORECASE
                ), (
                    f"{path.name}: CREATE EXTENSION without IF NOT EXISTS "
                    f"near position {match.start()}"
                )


class TestMigrationsHaveExceptionHandlersForExtensions:
    """LST.5: ParadeDB extensions must be wrapped in DO $$ ... EXCEPTION blocks."""

    def test_migrations_have_exception_handlers_for_paradedb_extensions(
        self,
    ) -> None:
        for path in _migration_files():
            sql = path.read_text()
            for ext in PARADEDB_EXTENSIONS:
                if ext not in sql.lower():
                    continue
                # If a ParadeDB extension is referenced, it must be inside a
                # DO $$ BEGIN ... EXCEPTION WHEN OTHERS THEN ... END $$ block.
                pattern = re.compile(
                    r"DO\s+\$\$\s*BEGIN\s*.*?"
                    + re.escape(ext)
                    + r".*?EXCEPTION\s+WHEN\s+OTHERS\s+THEN\s+.*?END\s*\$\$",
                    re.IGNORECASE | re.DOTALL,
                )
                assert pattern.search(sql), (
                    f"{path.name}: ParadeDB extension '{ext}' is not wrapped "
                    f"in a DO $$ BEGIN ... EXCEPTION ... END $$ block"
                )


class TestNoParadeSpecificTypesInSeed:
    """LST.5: seed.sql must not use ParadeDB-only types."""

    def test_no_parade_specific_types(self) -> None:
        assert SEED_SQL_PATH.exists(), f"seed.sql not found: {SEED_SQL_PATH}"
        sql = SEED_SQL_PATH.read_text().lower()
        for t in PARADEDB_TYPES:
            assert not re.search(t, sql), (
                f"seed.sql references ParadeDB-only type/feature: {t}"
            )


class TestMigrationsExist:
    """Sanity: migrations directory contains expected files."""

    def test_migrations_directory_has_files(self) -> None:
        files = _migration_files()
        assert len(files) >= 1, "Expected at least 1 migration file"

    def test_migrations_are_numbered(self) -> None:
        for path in _migration_files():
            assert re.match(
                r"\d{3}_", path.name
            ), f"Migration {path.name} does not follow NNN_ naming convention"


class TestNoCreateExtensionWithoutGracefulHandling:
    """If any migration creates a ParadeDB extension, verify full pattern."""

    @pytest.mark.parametrize("migration", _migration_files(), ids=lambda p: p.name)
    def test_no_bare_paradedb_extension_create(self, migration: Path) -> None:
        sql = migration.read_text()
        for ext in PARADEDB_EXTENSIONS:
            # Look for CREATE EXTENSION ... <ext> without exception handler.
            create_pattern = re.compile(
                r"CREATE\s+EXTENSION\s+.*?" + re.escape(ext),
                re.IGNORECASE | re.DOTALL,
            )
            if not create_pattern.search(sql):
                continue
            # Must be inside exception-handling block.
            handler_pattern = re.compile(
                r"DO\s+\$\$\s*BEGIN\s*.*?CREATE\s+EXTENSION\s+.*?"
                + re.escape(ext)
                + r".*?EXCEPTION\s+WHEN\s+OTHERS",
                re.IGNORECASE | re.DOTALL,
            )
            assert handler_pattern.search(sql), (
                f"{migration.name}: CREATE EXTENSION {ext} needs "
                f"DO $$ BEGIN ... EXCEPTION WHEN OTHERS ... END $$ wrapper"
            )

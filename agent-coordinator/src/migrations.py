"""Automatic schema migration runner for the coordinator database.

On startup, ensures all SQL migrations in ``supabase/migrations/`` have been
applied.  A ``schema_migrations`` tracking table records which files have
already run, so only *new* migrations execute.

Only the ``postgres`` (asyncpg) backend is supported — the ``supabase``
backend delegates schema management to the Supabase platform.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Migration files follow the naming convention: NNN_<description>.sql
_MIGRATION_RE = re.compile(r"^(\d+)_.+\.sql$")

# Relative to the agent-coordinator package root
_DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "supabase" / "migrations"

_BOOTSTRAP_SQL = """\
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum    TEXT NOT NULL
);
"""


def discover_migrations(migrations_dir: Path | None = None) -> list[tuple[int, str, Path]]:
    """Return sorted list of (sequence_number, filename, path) for all migration files."""
    directory = migrations_dir or _DEFAULT_MIGRATIONS_DIR
    if not directory.is_dir():
        logger.warning("Migrations directory not found: %s", directory)
        return []

    results: list[tuple[int, str, Path]] = []
    for entry in sorted(directory.iterdir()):
        m = _MIGRATION_RE.match(entry.name)
        if m and entry.is_file():
            results.append((int(m.group(1)), entry.name, entry))
    return results


def _checksum(content: str) -> str:
    """SHA-256 hex digest of migration content."""
    return hashlib.sha256(content.encode()).hexdigest()


async def run_migrations(
    dsn: str,
    *,
    migrations_dir: Path | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Apply any unapplied migrations and return the list of newly applied filenames.

    Args:
        dsn: PostgreSQL connection string.
        migrations_dir: Override the default migrations directory.
        dry_run: If True, report what *would* be applied without executing.

    Returns:
        List of migration filenames that were (or would be) applied.
    """
    import asyncpg

    conn = await asyncpg.connect(dsn, timeout=10)
    try:
        # Ensure tracking table exists
        await conn.execute(_BOOTSTRAP_SQL)

        # Fetch already-applied migrations
        rows = await conn.fetch("SELECT filename, checksum FROM schema_migrations")
        applied: dict[str, str] = {r["filename"]: r["checksum"] for r in rows}
        bootstrapping = len(applied) == 0  # First run: tracking table is empty

        all_migrations = discover_migrations(migrations_dir)
        newly_applied: list[str] = []

        for _seq, filename, path in all_migrations:
            if filename in applied:
                # Verify checksum hasn't changed
                content = path.read_text()
                expected = _checksum(content)
                if applied[filename] != expected:
                    logger.warning(
                        "Migration %s checksum mismatch (applied: %s, on-disk: %s). "
                        "Skipping — manual intervention required.",
                        filename,
                        applied[filename][:12],
                        expected[:12],
                    )
                continue

            content = path.read_text()
            if dry_run:
                logger.info("Would apply migration: %s", filename)
                newly_applied.append(filename)
                continue

            logger.info("Applying migration: %s", filename)
            try:
                async with conn.transaction():
                    await conn.execute(content)
                    await conn.execute(
                        "INSERT INTO schema_migrations (filename, checksum) VALUES ($1, $2)",
                        filename,
                        _checksum(content),
                    )
                newly_applied.append(filename)
            except Exception as exc:  # noqa: BLE001
                if bootstrapping:
                    # First run with an empty tracking table — the database was
                    # likely bootstrapped by Docker initdb.  Record the migration
                    # as already applied so future runs skip it.
                    logger.info(
                        "Migration %s already applied (bootstrap, error: %s) — recording.",
                        filename,
                        type(exc).__name__,
                    )
                    await conn.execute(
                        "INSERT INTO schema_migrations (filename, checksum) "
                        "VALUES ($1, $2) ON CONFLICT DO NOTHING",
                        filename,
                        _checksum(content),
                    )
                else:
                    raise

        if newly_applied:
            logger.info("Applied %d migration(s): %s", len(newly_applied), ", ".join(newly_applied))
        else:
            logger.debug("All %d migrations already applied.", len(applied))

        return newly_applied
    finally:
        await conn.close()


async def ensure_schema(*, migrations_dir: Path | None = None) -> list[str]:
    """High-level entry point: apply pending migrations using the current config.

    Returns the list of newly applied migration filenames, or an empty list
    if the backend is not ``postgres`` or migrations are up-to-date.
    """
    from .config import get_config

    config = get_config()
    if config.database.backend != "postgres":
        logger.debug(
            "Migration runner skipped — backend is %r (only 'postgres' supported).",
            config.database.backend,
        )
        return []

    dsn = config.database.postgres.dsn
    if not dsn:
        logger.warning("POSTGRES_DSN not set — cannot run migrations.")
        return []

    # Allow override via env var for non-standard layouts
    override = os.environ.get("COORDINATOR_MIGRATIONS_DIR")
    directory = Path(override) if override else migrations_dir

    return await run_migrations(dsn, migrations_dir=directory)

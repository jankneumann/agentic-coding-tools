"""Migration 028 (code_search_registry) checks.

The structural checks run anywhere (no DB). The apply test carries requires_db and skips without
POSTGRES_DSN — it belongs to the DB-available verification env.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "database" / "migrations" / "028_code_search_registry.sql"
)


def test_migration_exists():
    assert MIGRATION.is_file()


def test_migration_is_additive_and_declares_registry():
    sql = MIGRATION.read_text()
    # Additive-only (design D10): no destructive DDL.
    lowered = sql.lower()
    for forbidden in ("drop table", "drop column", "truncate", "delete from"):
        assert forbidden not in lowered, f"migration must be additive; found {forbidden!r}"
    # Ensures pgvector and the registry with the slug CHECK constraint.
    assert "create extension if not exists vector" in lowered
    assert "create table if not exists code_search_registry" in lowered
    assert "repo_slug" in lowered and "'^[a-z][a-z0-9_]{0,50}$'" in sql
    assert "embedder_model" in lowered and "embedding_dim" in lowered


@pytest.mark.skipif(not os.environ.get("POSTGRES_DSN"), reason="requires a live ParadeDB")
@pytest.mark.asyncio
async def test_migration_applies_and_enforces_slug_check():
    """Apply the migration to a scratch DB; the slug CHECK must reject an illegal slug."""
    import asyncpg

    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        await conn.execute(MIGRATION.read_text())
        # Legal slug inserts; illegal slug violates the CHECK.
        await conn.execute(
            "INSERT INTO code_search_registry (repo_slug, repo_root, embedder_model, embedding_dim)"
            " VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING",
            "test_repo", "/tmp/x", "m", 384,
        )
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await conn.execute(
                "INSERT INTO code_search_registry (repo_slug, repo_root, embedder_model,"
                " embedding_dim) VALUES ($1,$2,$3,$4)",
                "Bad Slug", "/tmp/x", "m", 384,
            )
    finally:
        await conn.close()

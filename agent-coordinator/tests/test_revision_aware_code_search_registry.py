"""Migration 029 contract tests for revision-aware semantic index records.

Structural tests run without PostgreSQL. Live tests require ``POSTGRES_DSN`` and
exercise migration 028 -> 029 compatibility against a real database.
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[1] / "database" / "migrations"
LEGACY_MIGRATION = MIGRATIONS / "028_code_search_registry.sql"
MIGRATION = MIGRATIONS / "029_revision_aware_code_search_indexes.sql"


def _normalized_sql() -> str:
    return re.sub(r"\s+", " ", MIGRATION.read_text(encoding="utf-8").lower())


def test_migration_exists_after_legacy_registry_migration() -> None:
    assert LEGACY_MIGRATION.is_file()
    assert MIGRATION.is_file()
    assert LEGACY_MIGRATION.name < MIGRATION.name


def test_migration_is_additive_and_preserves_legacy_columns() -> None:
    sql = _normalized_sql()

    for forbidden in (
        "drop table",
        "drop column",
        "truncate ",
        "rename column",
        "alter column",
    ):
        assert forbidden not in sql

    assert "create table if not exists code_search_indexes" in sql
    assert (
        "alter table code_search_registry add column if not exists "
        "canonical_index_id uuid"
    ) in sql
    assert "last_indexed_commit" not in sql
    assert "repo_root" not in sql


def test_index_table_freezes_identity_namespace_and_lifecycle_contracts() -> None:
    sql = _normalized_sql()

    for column in (
        "index_id",
        "storage_key",
        "repo_slug",
        "namespace_kind",
        "namespace_key",
        "source_revision",
        "embedder_model",
        "embedding_dim",
        "status",
        "attempt_count",
        "lease_token",
        "lease_owner",
        "lease_expires_at",
        "chunk_count",
        "last_error",
        "retention_until",
        "started_at",
        "completed_at",
        "deleted_at",
        "created_at",
        "updated_at",
    ):
        assert re.search(rf"\b{column}\b", sql), column

    assert "'main', 'feature', 'work_package'" in sql
    assert "'pending', 'indexing', 'ready', 'failed'," in sql
    assert "'not_configured', 'deleting', 'deleted'" in sql
    assert "'^[0-9a-f]{40}([0-9a-f]{24})?$'" in MIGRATION.read_text()
    assert "namespace_kind <> 'main' or namespace_key = 'main'" in sql
    assert "status <> 'ready'" in sql
    assert "status <> 'deleted'" in sql


def test_natural_key_and_lookup_indexes_are_idempotent() -> None:
    sql = _normalized_sql()

    assert (
        "constraint code_search_indexes_natural_key unique ( repo_slug, "
        "namespace_kind, namespace_key, source_revision, embedder_model, "
        "embedding_dim )"
    ) in sql
    assert "create index if not exists code_search_indexes_revision_lookup" in sql
    assert "create index if not exists code_search_indexes_gc_candidates" in sql
    assert "where namespace_kind in ('feature', 'work_package')" in sql


def test_storage_key_is_derived_from_index_uuid_by_trigger() -> None:
    sql = _normalized_sql()

    assert "returns trigger" in sql
    assert "'i_' || replace(new.index_id::text, '-', '')" in sql
    assert "before insert or update" in sql
    assert "code_search_indexes_set_storage_key" in sql


def test_canonical_pointer_has_fk_and_deferrable_safety_trigger() -> None:
    sql = _normalized_sql()

    assert "code_search_registry_canonical_index_fk" in sql
    assert "references code_search_indexes(index_id)" in sql
    assert "on delete restrict" in sql
    assert "create constraint trigger code_search_registry_validate_canonical" in sql
    assert "deferrable initially immediate" in sql
    assert "candidate.repo_slug <> new.repo_slug" in sql
    assert "candidate.namespace_kind <> 'main'" in sql
    assert "candidate.status <> 'ready'" in sql


async def _apply_migrations(conn: object) -> None:
    await conn.execute(LEGACY_MIGRATION.read_text(encoding="utf-8"))
    await conn.execute(MIGRATION.read_text(encoding="utf-8"))
    await conn.execute(MIGRATION.read_text(encoding="utf-8"))


async def _cleanup_repositories(conn: object, repo_slugs: list[str]) -> None:
    await conn.execute(
        "UPDATE code_search_registry SET canonical_index_id = NULL "
        "WHERE repo_slug = ANY($1::text[])",
        repo_slugs,
    )
    await conn.execute(
        "DELETE FROM code_search_indexes WHERE repo_slug = ANY($1::text[])",
        repo_slugs,
    )
    await conn.execute(
        "DELETE FROM code_search_registry WHERE repo_slug = ANY($1::text[])",
        repo_slugs,
    )


@pytest.mark.skipif(
    not os.environ.get("POSTGRES_DSN"),
    reason="requires live PostgreSQL/ParadeDB via POSTGRES_DSN",
)
@pytest.mark.asyncio
async def test_live_migration_is_idempotent_and_concurrent_ensure_is_unique() -> None:
    import asyncpg

    dsn = os.environ["POSTGRES_DSN"]
    repo_slug = f"migration_{uuid.uuid4().hex[:12]}"
    revision = "a" * 40
    conn = await asyncpg.connect(dsn)
    peer = await asyncpg.connect(dsn)
    try:
        await _apply_migrations(conn)
        await conn.execute(
            "INSERT INTO code_search_registry "
            "(repo_slug, repo_root, embedder_model, embedding_dim) "
            "VALUES ($1, $2, $3, $4)",
            repo_slug,
            "/tmp/revision-registry-test",
            "test-embedder",
            384,
        )
        ensure_sql = """
            INSERT INTO code_search_indexes (
                repo_slug, namespace_kind, namespace_key, source_revision,
                embedder_model, embedding_dim
            )
            VALUES ($1, 'main', 'main', $2, 'test-embedder', 384)
            ON CONFLICT ON CONSTRAINT code_search_indexes_natural_key
            DO UPDATE SET updated_at = code_search_indexes.updated_at
            RETURNING index_id, storage_key
        """

        first, second = await asyncio.gather(
            conn.fetchrow(ensure_sql, repo_slug, revision),
            peer.fetchrow(ensure_sql, repo_slug, revision),
        )

        assert first["index_id"] == second["index_id"]
        assert first["storage_key"] == f"i_{first['index_id'].hex}"
        assert await conn.fetchval(
            "SELECT count(*) FROM code_search_indexes WHERE repo_slug = $1",
            repo_slug,
        ) == 1
    finally:
        await _cleanup_repositories(conn, [repo_slug])
        await peer.close()
        await conn.close()


@pytest.mark.skipif(
    not os.environ.get("POSTGRES_DSN"),
    reason="requires live PostgreSQL/ParadeDB via POSTGRES_DSN",
)
@pytest.mark.asyncio
async def test_live_canonical_trigger_and_compare_and_swap_are_guarded() -> None:
    import asyncpg

    dsn = os.environ["POSTGRES_DSN"]
    repo_slug = f"canonical_{uuid.uuid4().hex[:12]}"
    other_slug = f"other_{uuid.uuid4().hex[:12]}"
    conn = await asyncpg.connect(dsn)
    try:
        await _apply_migrations(conn)
        for slug in (repo_slug, other_slug):
            await conn.execute(
                "INSERT INTO code_search_registry "
                "(repo_slug, repo_root, embedder_model, embedding_dim) "
                "VALUES ($1, $2, 'test-embedder', 384)",
                slug,
                f"/tmp/{slug}",
            )

        async def ready_index(slug: str, namespace: str, key: str, sha: str) -> uuid.UUID:
            index_id = await conn.fetchval(
                """
                INSERT INTO code_search_indexes (
                    repo_slug, namespace_kind, namespace_key, source_revision,
                    embedder_model, embedding_dim
                )
                VALUES ($1, $2, $3, $4, 'test-embedder', 384)
                RETURNING index_id
                """,
                slug,
                namespace,
                key,
                sha,
            )
            await conn.execute(
                "UPDATE code_search_indexes "
                "SET status = 'ready', chunk_count = 0, completed_at = now() "
                "WHERE index_id = $1",
                index_id,
            )
            return index_id

        main_a = await ready_index(repo_slug, "main", "main", "b" * 40)
        main_b = await ready_index(repo_slug, "main", "main", "c" * 40)
        feature = await ready_index(repo_slug, "feature", "feature-x", "d" * 40)
        cross_repo = await ready_index(other_slug, "main", "main", "e" * 40)

        await conn.execute(
            "UPDATE code_search_registry SET canonical_index_id = $2 "
            "WHERE repo_slug = $1",
            repo_slug,
            main_a,
        )
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await conn.execute(
                "UPDATE code_search_registry SET canonical_index_id = $2 "
                "WHERE repo_slug = $1",
                repo_slug,
                feature,
            )
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await conn.execute(
                "UPDATE code_search_registry SET canonical_index_id = $2 "
                "WHERE repo_slug = $1",
                repo_slug,
                cross_repo,
            )

        stale_result = await conn.fetchval(
            "UPDATE code_search_registry SET canonical_index_id = $2 "
            "WHERE repo_slug = $1 AND canonical_index_id IS NOT DISTINCT FROM $3 "
            "RETURNING canonical_index_id",
            repo_slug,
            main_b,
            uuid.uuid4(),
        )
        assert stale_result is None
        assert await conn.fetchval(
            "SELECT canonical_index_id FROM code_search_registry WHERE repo_slug = $1",
            repo_slug,
        ) == main_a

        promoted = await conn.fetchval(
            "UPDATE code_search_registry SET canonical_index_id = $2 "
            "WHERE repo_slug = $1 AND canonical_index_id IS NOT DISTINCT FROM $3 "
            "RETURNING canonical_index_id",
            repo_slug,
            main_b,
            main_a,
        )
        assert promoted == main_b
    finally:
        await _cleanup_repositories(conn, [repo_slug, other_slug])
        await conn.close()

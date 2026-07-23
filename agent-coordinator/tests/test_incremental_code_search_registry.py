from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "agent-coordinator" / "database" / "migrations"
LEGACY_MIGRATION = MIGRATIONS / "028_code_search_registry.sql"
REVISION_MIGRATION = MIGRATIONS / "029_revision_aware_code_search_indexes.sql"
MIGRATION = MIGRATIONS / "030_incremental_code_search_indexes.sql"


def normalized_sql() -> str:
    return re.sub(r"\s+", " ", MIGRATION.read_text(encoding="utf-8").lower())


def test_migration_adds_fingerprint_identity_and_legacy_backfill() -> None:
    sql = normalized_sql()

    for column in (
        "policy_fingerprint",
        "pipeline_fingerprint",
        "embedder_fingerprint",
        "parent_index_id",
    ):
        assert re.search(rf"\b{column}\b", sql)
    assert "repeat('0', 64)" in sql
    assert "^[0-9a-f]{64}$" in MIGRATION.read_text(encoding="utf-8")
    assert (
        "repo_slug, namespace_kind, namespace_key, source_revision, "
        "embedder_model, embedding_dim, policy_fingerprint, "
        "pipeline_fingerprint, embedder_fingerprint"
    ) in sql


def test_migration_backfills_and_freezes_repository_git_identity() -> None:
    sql = normalized_sql()

    assert (
        "alter table code_search_registry add column if not exists git_common_dir_fingerprint text"
    ) in sql
    assert (
        "update code_search_registry set git_common_dir_fingerprint = "
        "repeat('0', 64) where git_common_dir_fingerprint is null"
    ) in sql
    assert "alter column git_common_dir_fingerprint set not null" in sql
    assert "code_search_registry_git_common_dir_fingerprint_ck" in sql
    assert "git_common_dir_fingerprint ~ '^[0-9a-f]{64}$'" in sql
    assert "validate_code_search_repository_identity" in sql
    assert "new.repo_root is distinct from old.repo_root" in sql
    assert "repository root identity is immutable" in sql
    assert "old.git_common_dir_fingerprint = repeat('0', 64)" in sql
    assert "new.git_common_dir_fingerprint <> repeat('0', 64)" in sql
    assert "repository git common-directory identity is immutable" in sql


def test_migration_adds_attempt_and_published_manifest_contracts() -> None:
    sql = normalized_sql()

    assert "create table if not exists code_search_index_file_attempts" in sql
    assert "primary key (index_id, attempt_count, file_path)" in sql
    assert "create table if not exists code_search_index_files" in sql
    assert "primary key (index_id, file_path)" in sql
    assert "git_blob_id" in sql
    assert "content_digest" in sql
    assert "chunk_digest" in sql
    assert "chunk_count" in sql
    assert "eligible" in sql
    assert "eligibility_reason" in sql


def test_migration_guards_parent_compatibility_and_ready_immutability() -> None:
    sql = normalized_sql()

    assert "validate_code_search_parent" in sql
    assert "if tg_op = 'update'" in sql
    assert "create trigger code_search_indexes_parent_insert_guard before insert" in sql
    assert "ready index parent is immutable" in sql
    assert "incompatible semantic index parent" in sql
    assert "and status = 'ready' for share" in sql
    for field in (
        "repo_slug",
        "namespace_kind",
        "namespace_key",
        "embedder_model",
        "embedding_dim",
        "policy_fingerprint",
        "pipeline_fingerprint",
        "embedder_fingerprint",
    ):
        assert f"candidate.{field} <> new.{field}" in sql
    for field in (
        "policy_fingerprint",
        "pipeline_fingerprint",
        "embedder_fingerprint",
    ):
        assert f"candidate.{field} = repeat('0', 64)" in sql
    assert "validate_code_search_parent_target" in sql
    assert "referenced semantic index parent must remain compatible and ready" in sql


def test_migration_is_additive_and_does_not_destroy_registry_or_storage() -> None:
    sql = normalized_sql()

    assert "drop table" not in sql
    assert "truncate " not in sql
    assert "drop column" not in sql
    assert "rename column" not in sql
    assert "drop constraint if exists code_search_indexes_natural_key" in sql


async def apply_migrations(conn: object) -> None:
    await conn.execute(LEGACY_MIGRATION.read_text(encoding="utf-8"))
    await conn.execute(REVISION_MIGRATION.read_text(encoding="utf-8"))
    await conn.execute(MIGRATION.read_text(encoding="utf-8"))
    await conn.execute(MIGRATION.read_text(encoding="utf-8"))


@pytest.mark.skipif(
    not os.environ.get("POSTGRES_DSN"),
    reason="requires live PostgreSQL/ParadeDB via POSTGRES_DSN",
)
@pytest.mark.asyncio
async def test_live_migration_enforces_fingerprinted_identity_and_parent() -> None:
    import asyncpg

    dsn = os.environ["POSTGRES_DSN"]
    slug = f"incremental_{uuid.uuid4().hex[:12]}"
    conn = await asyncpg.connect(dsn)
    try:
        await apply_migrations(conn)
        await conn.execute(
            "INSERT INTO code_search_registry "
            "(repo_slug, repo_root, git_common_dir_fingerprint, "
            "embedder_model, embedding_dim) "
            "VALUES ($1, '/tmp/incremental-registry', $2, 'model', 8)",
            slug,
            "0" * 64,
        )
        await conn.execute(
            "UPDATE code_search_registry SET git_common_dir_fingerprint = $2 WHERE repo_slug = $1",
            slug,
            "9" * 64,
        )
        assert (
            await conn.fetchval(
                "SELECT git_common_dir_fingerprint FROM code_search_registry WHERE repo_slug = $1",
                slug,
            )
            == "9" * 64
        )
        values = (slug, "a" * 40, "1" * 64, "2" * 64, "3" * 64)
        parent_id = await conn.fetchval(
            """
            INSERT INTO code_search_indexes (
                repo_slug, namespace_kind, namespace_key, source_revision,
                embedder_model, embedding_dim, policy_fingerprint,
                pipeline_fingerprint, embedder_fingerprint
            )
            VALUES ($1, 'main', 'main', $2, 'model', 8, $3, $4, $5)
            RETURNING index_id
            """,
            *values,
        )
        await conn.execute(
            "UPDATE code_search_indexes "
            "SET status = 'ready', chunk_count = 0, completed_at = now() "
            "WHERE index_id = $1",
            parent_id,
        )
        child_id = await conn.fetchval(
            """
            INSERT INTO code_search_indexes (
                repo_slug, namespace_kind, namespace_key, source_revision,
                embedder_model, embedding_dim, policy_fingerprint,
                pipeline_fingerprint, embedder_fingerprint, parent_index_id
            )
            VALUES ($1, 'main', 'main', $2, 'model', 8, $3, $4, $5, $6)
            RETURNING index_id
            """,
            slug,
            "b" * 40,
            "1" * 64,
            "2" * 64,
            "3" * 64,
            parent_id,
        )
        assert (
            await conn.fetchval(
                "SELECT parent_index_id FROM code_search_indexes WHERE index_id = $1",
                child_id,
            )
            == parent_id
        )
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await conn.execute(
                """
                INSERT INTO code_search_indexes (
                    repo_slug, namespace_kind, namespace_key, source_revision,
                    embedder_model, embedding_dim, policy_fingerprint,
                    pipeline_fingerprint, embedder_fingerprint, parent_index_id
                )
                VALUES ($1, 'main', 'main', $2, 'model', 8, $3, $4, $5, $6)
                """,
                slug,
                "c" * 40,
                "4" * 64,
                "2" * 64,
                "3" * 64,
                parent_id,
            )
        legacy_parent_id = await conn.fetchval(
            """
            INSERT INTO code_search_indexes (
                repo_slug, namespace_kind, namespace_key, source_revision,
                embedder_model, embedding_dim, policy_fingerprint,
                pipeline_fingerprint, embedder_fingerprint
            )
            VALUES (
                $1, 'main', 'main', $2, 'model', 8,
                repeat('0', 64), repeat('0', 64), repeat('0', 64)
            )
            RETURNING index_id
            """,
            slug,
            "d" * 40,
        )
        await conn.execute(
            "UPDATE code_search_indexes "
            "SET status = 'ready', chunk_count = 0, completed_at = now() "
            "WHERE index_id = $1",
            legacy_parent_id,
        )
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await conn.execute(
                """
                INSERT INTO code_search_indexes (
                    repo_slug, namespace_kind, namespace_key, source_revision,
                    embedder_model, embedding_dim, policy_fingerprint,
                    pipeline_fingerprint, embedder_fingerprint, parent_index_id
                )
                VALUES (
                    $1, 'main', 'main', $2, 'model', 8,
                    repeat('0', 64), repeat('0', 64), repeat('0', 64), $3
                )
                """,
                slug,
                "e" * 40,
                legacy_parent_id,
            )
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await conn.execute(
                "UPDATE code_search_indexes SET policy_fingerprint = $2 WHERE index_id = $1",
                parent_id,
                "4" * 64,
            )
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await conn.execute(
                "UPDATE code_search_registry SET repo_root = '/tmp/remapped' WHERE repo_slug = $1",
                slug,
            )
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await conn.execute(
                "UPDATE code_search_registry "
                "SET git_common_dir_fingerprint = $2 WHERE repo_slug = $1",
                slug,
                "8" * 64,
            )
    finally:
        await conn.execute(
            "UPDATE code_search_indexes SET parent_index_id = NULL WHERE repo_slug = $1",
            slug,
        )
        await conn.execute("DELETE FROM code_search_indexes WHERE repo_slug = $1", slug)
        await conn.execute("DELETE FROM code_search_registry WHERE repo_slug = $1", slug)
        await conn.close()

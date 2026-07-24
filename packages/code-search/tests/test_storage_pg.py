from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from code_search_pkg.identifiers import attempt_chunk_table_name, index_chunk_table_name
from code_search_pkg.registry import IndexLeaseConflictError
from code_search_pkg.registry_models import (
    IndexStatus,
    NamespaceKind,
    SemanticIndexRecord,
)
from code_search_pkg.schema import CodeChunk
from code_search_pkg.storage_pg import StoragePublisher

INDEX_ID = UUID("11111111-1111-4111-8111-111111111111")
LEASE = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 7, 23, tzinfo=UTC)


def record(**overrides) -> SemanticIndexRecord:
    base = SemanticIndexRecord(
        index_id=INDEX_ID,
        storage_key="i_11111111111141118111111111111111",
        repo_slug="repo",
        namespace_kind=NamespaceKind.MAIN,
        namespace_key="main",
        source_revision="a" * 40,
        embedder_model="model",
        embedding_dim=3,
        policy_fingerprint="1" * 64,
        pipeline_fingerprint="2" * 64,
        embedder_fingerprint="3" * 64,
        parent_index_id=None,
        status=IndexStatus.INDEXING,
        attempt_count=2,
        chunk_count=None,
        last_error=None,
        lease_token=LEASE,
        lease_owner="worker",
        lease_expires_at=NOW + timedelta(minutes=5),
        retention_until=None,
        started_at=NOW,
        completed_at=None,
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    return replace(base, **overrides)


VALID_VERIFICATION = {
    "chunk_count": 1,
    "file_count": 1,
    "expected_chunk_count": 1,
    "expected_file_count": 1,
    "vector_index_present": True,
    "schema_valid": True,
    "manifest_covered": True,
}


class FakeConnection:
    def __init__(
        self,
        current_row: dict | None = None,
        *,
        verification_rows: list[dict] | None = None,
    ):
        self.current_row = current_row
        self.verification_rows = list(verification_rows or [])
        self.commands: list[tuple[str, tuple]] = []

    @asynccontextmanager
    async def transaction(self):
        self.commands.append(("BEGIN", ()))
        yield
        self.commands.append(("COMMIT", ()))

    async def execute(self, query: str, *args):
        self.commands.append((query, args))
        return "OK"

    async def fetchrow(self, query: str, *args):
        self.commands.append((query, args))
        if "WITH target_counts AS" in query:
            if self.verification_rows:
                return self.verification_rows.pop(0)
            return VALID_VERIFICATION
        return self.current_row

    async def fetchval(self, query: str, *args):
        self.commands.append((query, args))
        return 1

    async def executemany(self, query: str, args):
        values = tuple(args)
        self.commands.append((query, values))


class FakePool:
    def __init__(self, connection: FakeConnection):
        self.connection = connection
        self.commands = connection.commands

    @asynccontextmanager
    async def acquire(self):
        yield self.connection

    async def execute(self, query: str, *args):
        return await self.connection.execute(query, *args)

    async def fetchrow(self, query: str, *args):
        return await self.connection.fetchrow(query, *args)


class FakeManifestPublisher:
    def __init__(self):
        self.executor = None
        self.calls = []

    async def publish_attempt_manifest(
        self,
        index_id,
        lease_token,
        attempt_count,
        *,
        executor,
    ):
        self.executor = executor
        self.calls.append((index_id, lease_token, attempt_count))
        await executor.execute("/* fake:publish_manifest */ SELECT 1")
        return 2


def test_attempt_table_name_is_bounded_and_identifier_safe():
    name = attempt_chunk_table_name(INDEX_ID, 123)
    assert name == "ccs__11111111111141118111111111111111__123"
    assert len(name) < 64
    with pytest.raises(ValueError):
        attempt_chunk_table_name(INDEX_ID, 0)


@pytest.mark.asyncio
async def test_prepare_attempt_uses_only_attempt_scoped_table():
    connection = FakeConnection()
    storage = StoragePublisher(FakePool(connection))

    attempt = await storage.prepare_attempt(record(), embedding_dim=3)

    sql = "\n".join(query for query, _ in connection.commands)
    assert attempt.table_name == attempt_chunk_table_name(INDEX_ID, 2)
    assert f"DROP TABLE IF EXISTS {attempt.table_name}" in sql
    assert f"CREATE TABLE {attempt.table_name}" in sql
    assert "vector(3)" in sql
    assert index_chunk_table_name(record().storage_key) not in sql


@pytest.mark.asyncio
async def test_replace_file_is_transactional_and_path_owned():
    connection = FakeConnection()
    storage = StoragePublisher(FakePool(connection))
    attempt = storage.attempt_for(record())
    chunks = [
        CodeChunk(
            id="chunk-1",
            file_path="src/app.py",
            language="python",
            content="print('ok')",
            start_line=1,
            end_line=1,
            embedding=[0.1, 0.2, 0.3],
        )
    ]

    await storage.replace_file(attempt, "src/app.py", chunks)

    sql = "\n".join(query for query, _ in connection.commands)
    assert "BEGIN" in sql and "COMMIT" in sql
    assert f"DELETE FROM {attempt.table_name} WHERE file_path = $1" in sql
    assert f"INSERT INTO {attempt.table_name}" in sql


@pytest.mark.asyncio
async def test_verify_attempt_requires_complete_attempt_manifest_coverage():
    connection = FakeConnection(
        verification_rows=[
            {
                **VALID_VERIFICATION,
                "manifest_covered": False,
            }
        ]
    )
    storage = StoragePublisher(FakePool(connection))

    with pytest.raises(RuntimeError, match="manifest=False"):
        await storage.verify_attempt(
            storage.attempt_for(record()),
            expected_chunks=1,
            expected_files=1,
        )

    sql = "\n".join(query for query, _ in connection.commands)
    assert "code_search_index_file_attempts" in sql
    assert "chunk_count" in sql


@pytest.mark.asyncio
async def test_publish_rejects_stale_attempt_before_rename():
    stale_row = {
        "status": "indexing",
        "lease_token": UUID("33333333-3333-4333-8333-333333333333"),
        "attempt_count": 3,
        "lease_current": True,
    }
    connection = FakeConnection(current_row=stale_row)
    storage = StoragePublisher(FakePool(connection))

    with pytest.raises(IndexLeaseConflictError):
        await storage.publish_attempt(record(), storage.attempt_for(record()))

    sql = "\n".join(query for query, _ in connection.commands)
    assert "ALTER TABLE" not in sql
    assert index_chunk_table_name(record().storage_key) not in sql


@pytest.mark.asyncio
async def test_publish_fences_then_atomically_renames_and_publishes_manifest():
    current = {
        "status": "indexing",
        "lease_token": LEASE,
        "attempt_count": 2,
        "lease_current": True,
    }
    connection = FakeConnection(current_row=current)
    manifest_publisher = FakeManifestPublisher()
    storage = StoragePublisher(
        FakePool(connection),
        manifest_publisher=manifest_publisher,
    )
    attempt = storage.attempt_for(record())

    await storage.publish_attempt(record(), attempt)

    sql = "\n".join(query for query, _ in connection.commands)
    final_name = index_chunk_table_name(record().storage_key)
    assert "pg_advisory_xact_lock" in sql
    assert f"LOCK TABLE {attempt.table_name} IN ACCESS EXCLUSIVE MODE" in sql
    assert "FOR UPDATE" in sql
    assert "WITH target_counts AS" in sql
    assert f"ALTER TABLE {attempt.table_name} RENAME TO {final_name}" in sql
    assert "fake:publish_manifest" in sql
    assert sql.index("FOR UPDATE") < sql.index("WITH target_counts AS")
    assert sql.index("WITH target_counts AS") < sql.index("ALTER TABLE")
    assert sql.index("ALTER TABLE") < sql.index("fake:publish_manifest")
    assert manifest_publisher.executor is connection
    assert manifest_publisher.calls == [(INDEX_ID, LEASE, 2)]


@pytest.mark.asyncio
async def test_current_publish_requires_registry_owned_manifest_publisher():
    current = {
        "status": "indexing",
        "lease_token": LEASE,
        "attempt_count": 2,
        "lease_current": True,
    }
    storage = StoragePublisher(FakePool(FakeConnection(current_row=current)))

    with pytest.raises(RuntimeError, match="manifest publisher"):
        await storage.publish_attempt(record(), storage.attempt_for(record()))


@pytest.mark.asyncio
async def test_publish_rechecks_mutated_attempt_inside_fenced_transaction():
    current = {
        "status": "indexing",
        "lease_token": LEASE,
        "attempt_count": 2,
        "lease_current": True,
    }
    connection = FakeConnection(
        current_row=current,
        verification_rows=[
            VALID_VERIFICATION,
            {
                **VALID_VERIFICATION,
                "chunk_count": 2,
                "manifest_covered": False,
            },
        ],
    )
    manifest_publisher = FakeManifestPublisher()
    storage = StoragePublisher(
        FakePool(connection),
        manifest_publisher=manifest_publisher,
    )
    attempt = storage.attempt_for(record())

    # A preliminary check passes, then the fake models a write racing before publish.
    await storage.verify_attempt(attempt, expected_chunks=1, expected_files=1)
    with pytest.raises(RuntimeError, match="storage verification failed"):
        await storage.publish_attempt(record(), attempt)

    sql = "\n".join(query for query, _ in connection.commands)
    assert sql.count("WITH target_counts AS") == 2
    assert f"ALTER TABLE {attempt.table_name}" not in sql
    assert manifest_publisher.calls == []

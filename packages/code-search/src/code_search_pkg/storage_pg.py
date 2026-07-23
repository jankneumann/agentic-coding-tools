"""Attempt-scoped Postgres storage with lease-fenced atomic publication.

The registry decides *who* owns an indexing attempt. This module ensures that a
worker can only mutate its own staging table and that only the current registry
lease may publish staging as the immutable revision table.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from .identifiers import attempt_chunk_table_name, index_chunk_table_name
from .registry_models import (
    IndexLeaseConflictError,
    IndexStatus,
    SemanticIndexRecord,
)
from .schema import CodeChunk


class StorageConnection(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[Any]: ...

    async def execute(self, query: str, *args: Any) -> Any: ...

    async def executemany(self, query: str, args: Iterable[Sequence[Any]]) -> Any: ...

    async def fetchrow(self, query: str, *args: Any) -> Mapping[str, Any] | None: ...

    async def fetchval(self, query: str, *args: Any) -> Any: ...


class StoragePool(Protocol):
    def acquire(self) -> AbstractAsyncContextManager[StorageConnection]: ...

    async def execute(self, query: str, *args: Any) -> Any: ...

    async def fetchrow(self, query: str, *args: Any) -> Mapping[str, Any] | None: ...


class VerificationExecutor(Protocol):
    async def fetchrow(self, query: str, *args: Any) -> Mapping[str, Any] | None: ...


class ManifestPublisher(Protocol):
    async def publish_attempt_manifest(
        self,
        index_id: UUID,
        lease_token: UUID | None,
        attempt_count: int,
        *,
        executor: StorageConnection,
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class StorageAttempt:
    index_id: UUID
    attempt_count: int
    storage_key: str
    table_name: str
    final_table_name: str
    embedding_dim: int


@dataclass(frozen=True, slots=True)
class StorageVerification:
    chunk_count: int
    file_count: int
    vector_index_present: bool
    schema_valid: bool
    manifest_covered: bool


class StoragePublisher:
    """Build and publish isolated semantic-index tables."""

    def __init__(
        self,
        pool: StoragePool,
        *,
        manifest_publisher: ManifestPublisher | None = None,
    ) -> None:
        self._pool = pool
        self._manifest_publisher = manifest_publisher

    def attempt_for(self, record: SemanticIndexRecord) -> StorageAttempt:
        if record.status is not IndexStatus.INDEXING:
            raise ValueError("storage attempts require an indexing record")
        if record.lease_token is None or record.attempt_count <= 0:
            raise ValueError("storage attempts require a current lease generation")
        return StorageAttempt(
            index_id=record.index_id,
            attempt_count=record.attempt_count,
            storage_key=record.storage_key,
            table_name=attempt_chunk_table_name(record.index_id, record.attempt_count),
            final_table_name=index_chunk_table_name(record.storage_key),
            embedding_dim=record.embedding_dim,
        )

    async def prepare_attempt(
        self,
        record: SemanticIndexRecord,
        *,
        embedding_dim: int,
    ) -> StorageAttempt:
        if isinstance(embedding_dim, bool) or embedding_dim <= 0:
            raise ValueError("embedding_dim must be positive")
        if embedding_dim != record.embedding_dim:
            raise ValueError("embedding dimension differs from registry identity")
        attempt = self.attempt_for(record)
        vector_index = _attempt_vector_index_name(
            attempt.index_id, attempt.attempt_count
        )
        await self._pool.execute(f"DROP TABLE IF EXISTS {attempt.table_name}")
        await self._pool.execute(
            f"""
            CREATE TABLE {attempt.table_name} (
                id text PRIMARY KEY,
                file_path text NOT NULL,
                language text NOT NULL,
                content text NOT NULL,
                start_line integer NOT NULL CHECK (start_line >= 1),
                end_line integer NOT NULL CHECK (end_line >= start_line),
                embedding vector({embedding_dim}) NOT NULL
            )
            """
        )
        await self._pool.execute(
            f"""
            CREATE INDEX {vector_index}
            ON {attempt.table_name}
            USING hnsw (embedding vector_cosine_ops)
            """
        )
        return attempt

    async def copy_unchanged(
        self,
        parent_storage_key: str,
        attempt: StorageAttempt,
        paths: Sequence[str],
    ) -> int:
        if not paths:
            return 0
        _validate_paths(paths)
        parent_table = index_chunk_table_name(parent_storage_key)
        row = await self._pool.fetchrow(
            f"""
            WITH copied AS (
                INSERT INTO {attempt.table_name} (
                    id, file_path, language, content, start_line, end_line, embedding
                )
                SELECT id, file_path, language, content, start_line, end_line, embedding
                FROM {parent_table} AS parent_chunk
                WHERE parent_chunk.file_path = ANY($1::text[])
                  AND EXISTS (
                      SELECT 1
                      FROM code_search_indexes AS parent_index
                      JOIN code_search_index_files AS parent_manifest
                        ON parent_manifest.index_id = parent_index.index_id
                      WHERE parent_index.storage_key = $2
                        AND parent_index.status = 'ready'
                        AND parent_manifest.file_path = parent_chunk.file_path
                        AND parent_manifest.eligible
                  )
                ON CONFLICT (id) DO NOTHING
                RETURNING 1
            )
            SELECT count(*)::integer AS copied FROM copied
            """,
            list(paths),
            parent_storage_key,
        )
        return int(row["copied"]) if row is not None else 0

    async def replace_file(
        self,
        attempt: StorageAttempt,
        file_path: str,
        chunks: Sequence[CodeChunk],
    ) -> None:
        _validate_paths([file_path])
        if any(chunk.file_path != file_path for chunk in chunks):
            raise ValueError("all chunks must belong to the replaced file")
        rows = [
            (
                str(chunk.id),
                chunk.file_path,
                chunk.language,
                chunk.content,
                chunk.start_line,
                chunk.end_line,
                chunk.embedding,
            )
            for chunk in chunks
        ]
        async with self._pool.acquire() as connection, connection.transaction():
            await connection.execute(
                f"DELETE FROM {attempt.table_name} WHERE file_path = $1",
                file_path,
            )
            if rows:
                await connection.executemany(
                    f"""
                        INSERT INTO {attempt.table_name} (
                            id, file_path, language, content,
                            start_line, end_line, embedding
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """,
                    rows,
                )

    async def verify_attempt(
        self,
        attempt: StorageAttempt,
        *,
        expected_chunks: int,
        expected_files: int,
    ) -> StorageVerification:
        if expected_chunks < 0 or expected_files < 0:
            raise ValueError("expected counts must not be negative")
        return await self._verify_attempt_with(
            self._pool,
            attempt,
            expected_chunks=expected_chunks,
            expected_files=expected_files,
        )

    async def _verify_attempt_with(
        self,
        executor: VerificationExecutor,
        attempt: StorageAttempt,
        *,
        expected_chunks: int | None = None,
        expected_files: int | None = None,
    ) -> StorageVerification:
        row = await executor.fetchrow(
            f"""
            WITH target_counts AS (
                SELECT
                    count(*)::integer AS chunk_count,
                    count(DISTINCT file_path)::integer AS file_count
                FROM {attempt.table_name}
            ),
            manifest_counts AS (
                SELECT
                    COALESCE(
                        sum(chunk_count) FILTER (WHERE eligible),
                        0
                    )::integer AS expected_chunk_count,
                    count(*) FILTER (
                        WHERE eligible AND chunk_count > 0
                    )::integer AS expected_file_count
                FROM code_search_index_file_attempts
                WHERE index_id = $2
                  AND attempt_count = $3
            ),
            manifest_coverage AS (
                SELECT
                    NOT EXISTS (
                        SELECT 1
                        FROM code_search_index_file_attempts AS manifest
                        WHERE manifest.index_id = $2
                          AND manifest.attempt_count = $3
                          AND (
                              (
                                  manifest.eligible
                                  AND manifest.chunk_count <> (
                                      SELECT count(*)
                                      FROM {attempt.table_name} AS target
                                      WHERE target.file_path = manifest.file_path
                                  )
                              )
                              OR (
                                  NOT manifest.eligible
                                  AND EXISTS (
                                      SELECT 1
                                      FROM {attempt.table_name} AS target
                                      WHERE target.file_path = manifest.file_path
                                  )
                              )
                          )
                    )
                    AND NOT EXISTS (
                        SELECT 1
                        FROM {attempt.table_name} AS target
                        LEFT JOIN code_search_index_file_attempts AS manifest
                          ON manifest.index_id = $2
                         AND manifest.attempt_count = $3
                         AND manifest.file_path = target.file_path
                        WHERE manifest.file_path IS NULL OR NOT manifest.eligible
                    ) AS manifest_covered
            )
            SELECT
                target_counts.chunk_count,
                target_counts.file_count,
                manifest_counts.expected_chunk_count,
                manifest_counts.expected_file_count,
                EXISTS (
                    SELECT 1
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND tablename = $1
                      AND indexdef ILIKE '%USING hnsw%'
                      AND indexdef ILIKE '%vector_cosine_ops%'
                ) AS vector_index_present,
                EXISTS (
                    SELECT 1
                    FROM pg_attribute AS attribute
                    JOIN pg_class AS relation
                      ON relation.oid = attribute.attrelid
                    JOIN pg_namespace AS namespace
                      ON namespace.oid = relation.relnamespace
                    WHERE namespace.nspname = current_schema()
                      AND relation.relname = $1
                      AND attribute.attname = 'embedding'
                      AND format_type(
                          attribute.atttypid, attribute.atttypmod
                      ) = $4
                ) AS schema_valid,
                manifest_coverage.manifest_covered
            FROM target_counts
            CROSS JOIN manifest_counts
            CROSS JOIN manifest_coverage
            """,
            attempt.table_name,
            attempt.index_id,
            attempt.attempt_count,
            f"vector({attempt.embedding_dim})",
        )
        if row is None:
            raise RuntimeError("storage verification returned no result")
        result = StorageVerification(
            chunk_count=int(row["chunk_count"]),
            file_count=int(row["file_count"]),
            vector_index_present=bool(row["vector_index_present"]),
            schema_valid=bool(row["schema_valid"]),
            manifest_covered=bool(row["manifest_covered"]),
        )
        manifest_chunks = int(row["expected_chunk_count"])
        manifest_files = int(row["expected_file_count"])
        required_chunks = (
            manifest_chunks if expected_chunks is None else expected_chunks
        )
        required_files = manifest_files if expected_files is None else expected_files
        if (
            result.chunk_count != required_chunks
            or result.file_count != required_files
            or result.chunk_count != manifest_chunks
            or result.file_count != manifest_files
            or not result.vector_index_present
            or not result.schema_valid
            or not result.manifest_covered
        ):
            raise RuntimeError(
                "storage verification failed: "
                f"chunks={result.chunk_count}/{required_chunks}"
                f"/manifest:{manifest_chunks}, "
                f"files={result.file_count}/{required_files}"
                f"/manifest:{manifest_files}, "
                f"hnsw={result.vector_index_present}, "
                f"schema={result.schema_valid}, "
                f"manifest={result.manifest_covered}"
            )
        return result

    async def publish_attempt(
        self,
        record: SemanticIndexRecord,
        attempt: StorageAttempt,
    ) -> None:
        """Atomically publish only if ``record`` still owns the current attempt."""
        if record.lease_token is None:
            raise ValueError("publication requires a lease token")
        if (
            attempt.index_id != record.index_id
            or attempt.attempt_count != record.attempt_count
            or attempt.storage_key != record.storage_key
        ):
            raise ValueError("attempt does not match registry record")

        async with self._pool.acquire() as connection, connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1::text, 0))",
                str(record.index_id),
            )
            await connection.execute(
                f"LOCK TABLE {attempt.table_name} IN ACCESS EXCLUSIVE MODE"
            )
            current = await connection.fetchrow(
                """
                    SELECT
                        status,
                        lease_token,
                        attempt_count,
                        lease_expires_at > clock_timestamp() AS lease_current
                    FROM code_search_indexes
                    WHERE index_id = $1
                    FOR UPDATE
                    """,
                record.index_id,
            )
            if not _lease_matches(current, record):
                raise IndexLeaseConflictError(
                    f"index {record.index_id} no longer owns storage publication"
                )
            if self._manifest_publisher is None:
                raise RuntimeError(
                    "storage publication requires a registry manifest publisher"
                )
            await self._verify_attempt_with(connection, attempt)
            await connection.execute(f"DROP TABLE IF EXISTS {attempt.final_table_name}")
            await connection.execute(
                f"ALTER TABLE {attempt.table_name} RENAME TO {attempt.final_table_name}"
            )
            await self._manifest_publisher.publish_attempt_manifest(
                record.index_id,
                record.lease_token,
                record.attempt_count,
                executor=connection,
            )

    async def cleanup_attempt(self, attempt: StorageAttempt) -> None:
        await self._pool.execute(f"DROP TABLE IF EXISTS {attempt.table_name}")
        await self._pool.execute(
            """
            DELETE FROM code_search_index_file_attempts
            WHERE index_id = $1 AND attempt_count = $2
            """,
            attempt.index_id,
            attempt.attempt_count,
        )


def _lease_matches(
    current: Mapping[str, Any] | None, record: SemanticIndexRecord
) -> bool:
    if current is None:
        return False
    status = (
        current["status"].value
        if isinstance(current["status"], IndexStatus)
        else str(current["status"])
    )
    token = current["lease_token"]
    if token is not None and not isinstance(token, UUID):
        token = UUID(str(token))
    return (
        status == IndexStatus.INDEXING.value
        and token == record.lease_token
        and int(current["attempt_count"]) == record.attempt_count
        and bool(current["lease_current"])
    )


def _validate_paths(paths: Sequence[str]) -> None:
    for path in paths:
        if (
            not path
            or path.startswith("/")
            or "\\" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
        ):
            raise ValueError(f"unsafe repository-relative path: {path!r}")


def _attempt_vector_index_name(index_id: UUID, attempt_count: int) -> str:
    name = f"hnsw__{index_id.hex}__{attempt_count}"
    if len(name) >= 64:
        raise ValueError("attempt vector index name exceeds PostgreSQL limit")
    return name

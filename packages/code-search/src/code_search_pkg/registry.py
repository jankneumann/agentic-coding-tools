"""Typed async repository for revision-aware semantic index lifecycle state."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from .identifiers import storage_key_for_index, validate_slug
from .registry_models import (
    CanonicalPromotionError,
    GarbageCollectionResult,
    IndexIdentity,
    IndexLeaseConflictError,
    IndexNotFoundError,
    IndexRegistryError as IndexRegistryError,
    IndexStateConflictError,
    IndexStatus as IndexStatus,
    NamespaceKind as NamespaceKind,
    SemanticIndexRecord,
    as_uuid,
)


_UNSET = object()


class AsyncpgPool(Protocol):
    async def fetchrow(self, query: str, *args: Any) -> Mapping[str, Any] | None: ...

    async def fetch(self, query: str, *args: Any) -> Sequence[Mapping[str, Any]]: ...


class SemanticIndexRegistry:
    """Atomic registry operations implemented with asyncpg-style pool calls."""

    def __init__(
        self,
        pool: AsyncpgPool,
        *,
        clock: Callable[[], datetime] | None = None,
        uuid_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._pool = pool
        self._clock = clock or (lambda: datetime.now(UTC))
        self._uuid_factory = uuid_factory

    async def ensure_index(
        self,
        identity: IndexIdentity,
        *,
        retention_until: datetime | None = None,
    ) -> SemanticIndexRecord:
        now = self._now()
        index_id = self._uuid_factory()
        row = await self._pool.fetchrow(
            """
            /* registry:ensure */
            INSERT INTO code_search_indexes (
                index_id, storage_key, repo_slug, namespace_kind, namespace_key,
                source_revision, embedder_model, embedding_dim, retention_until,
                created_at, updated_at
            )
            SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10
            FROM code_search_registry AS repository
            WHERE repository.repo_slug = $3
            ON CONFLICT (
                repo_slug, namespace_kind, namespace_key, source_revision,
                embedder_model, embedding_dim
            ) DO UPDATE SET updated_at = code_search_indexes.updated_at
            RETURNING *
            """,
            index_id,
            storage_key_for_index(index_id),
            identity.repo_slug,
            identity.namespace_kind.value,
            identity.namespace_key,
            identity.source_revision,
            identity.embedder_model,
            identity.embedding_dim,
            retention_until,
            now,
        )
        if row is None:
            raise IndexNotFoundError(
                f"repository {identity.repo_slug!r} does not exist"
            )
        return SemanticIndexRecord.from_row(row)

    async def get_index(self, index_id: UUID) -> SemanticIndexRecord:
        row = await self._pool.fetchrow(
            "/* registry:get */ SELECT * FROM code_search_indexes WHERE index_id = $1",
            index_id,
        )
        if row is None:
            raise IndexNotFoundError(f"index {index_id} does not exist")
        return SemanticIndexRecord.from_row(row)

    async def claim_index(
        self,
        index_id: UUID,
        *,
        lease_owner: str,
        lease_duration: timedelta,
    ) -> SemanticIndexRecord:
        if not lease_owner:
            raise ValueError("lease_owner must not be empty")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        now = self._now()
        lease_token = self._uuid_factory()
        row = await self._pool.fetchrow(
            """
            /* registry:claim */
            UPDATE code_search_indexes
            SET status = 'indexing',
                attempt_count = attempt_count + 1,
                lease_token = $2,
                lease_owner = $3,
                lease_expires_at = $4,
                started_at = $5,
                completed_at = NULL,
                deleted_at = NULL,
                last_error = NULL,
                updated_at = $5
            WHERE index_id = $1
              AND (
                status IN ('pending', 'failed', 'not_configured')
                OR (
                    status = 'indexing'
                    AND lease_expires_at <= $5
                )
              )
            RETURNING *
            """,
            index_id,
            lease_token,
            lease_owner,
            now + lease_duration,
            now,
        )
        if row is None:
            await self.get_index(index_id)
            raise IndexStateConflictError(
                f"index {index_id} is complete or actively leased"
            )
        return SemanticIndexRecord.from_row(row)

    async def mark_ready(
        self, index_id: UUID, lease_token: UUID | None, *, chunk_count: int
    ) -> SemanticIndexRecord:
        if isinstance(chunk_count, bool) or chunk_count < 0:
            raise ValueError("chunk_count must not be negative")
        return await self._complete_index("ready", index_id, lease_token, chunk_count)

    async def mark_failed(
        self, index_id: UUID, lease_token: UUID | None, error: str
    ) -> SemanticIndexRecord:
        if not error:
            raise ValueError("error must not be empty")
        return await self._complete_index("failed", index_id, lease_token, error)

    async def mark_not_configured(
        self, index_id: UUID, lease_token: UUID | None, reason: str
    ) -> SemanticIndexRecord:
        if not reason:
            raise ValueError("reason must not be empty")
        return await self._complete_index(
            "not_configured", index_id, lease_token, reason
        )

    async def promote_canonical(
        self,
        repo_slug: str,
        index_id: UUID,
        *,
        expected_current_index_id: UUID | None | object = _UNSET,
    ) -> UUID:
        validate_slug(repo_slug)
        check_expected = expected_current_index_id is not _UNSET
        expected = (
            None if expected_current_index_id is _UNSET else expected_current_index_id
        )
        row = await self._pool.fetchrow(
            """
            /* registry:promote */
            UPDATE code_search_registry AS repository
            SET canonical_index_id = $2
            FROM code_search_indexes AS candidate
            WHERE repository.repo_slug = $1
              AND candidate.index_id = $2
              AND candidate.repo_slug = repository.repo_slug
              AND candidate.namespace_kind = 'main'
              AND candidate.status = 'ready'
              AND (
                NOT $3::boolean
                OR repository.canonical_index_id IS NOT DISTINCT FROM $4::uuid
              )
            RETURNING repository.canonical_index_id
            """,
            repo_slug,
            index_id,
            check_expected,
            expected,
        )
        if row is None:
            raise CanonicalPromotionError(
                "candidate is not a ready same-repository main index "
                "or the expected canonical index is stale"
            )
        return as_uuid(row["canonical_index_id"])

    async def collect_garbage(
        self,
        storage_deleter: Callable[[str], Awaitable[None] | None],
        *,
        limit: int = 100,
        lease_owner: str = "semantic-index-gc",
        lease_duration: timedelta = timedelta(minutes=5),
    ) -> GarbageCollectionResult:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if not lease_owner:
            raise ValueError("lease_owner must not be empty")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        now = self._now()
        candidates = await self._pool.fetch(
            """
            /* registry:gc_candidates */
            SELECT candidate.*
            FROM code_search_indexes AS candidate
            WHERE candidate.namespace_kind IN ('feature', 'work_package')
              AND candidate.retention_until <= $1
              AND (
                candidate.status IN ('pending', 'ready', 'failed', 'not_configured')
                OR (
                    candidate.status IN ('indexing', 'deleting')
                    AND candidate.lease_expires_at <= $1
                )
              )
              AND NOT EXISTS (
                SELECT 1
                FROM code_search_registry AS repository
                WHERE repository.canonical_index_id = candidate.index_id
              )
            ORDER BY candidate.retention_until, candidate.created_at
            LIMIT $2
            """,
            now,
            limit,
        )
        deleted: list[UUID] = []
        failed: list[UUID] = []
        for candidate in candidates:
            index_id = as_uuid(candidate["index_id"])
            lease_token = self._uuid_factory()
            claimed = await self._pool.fetchrow(
                """
                /* registry:gc_claim */
                UPDATE code_search_indexes AS candidate
                SET status = 'deleting',
                    lease_token = $2,
                    lease_owner = $3,
                    lease_expires_at = $4,
                    updated_at = $5
                WHERE candidate.index_id = $1
                  AND candidate.namespace_kind IN ('feature', 'work_package')
                  AND candidate.retention_until <= $5
                  AND (
                    candidate.status IN (
                        'pending', 'ready', 'failed', 'not_configured'
                    )
                    OR (
                        candidate.status IN ('indexing', 'deleting')
                        AND candidate.lease_expires_at <= $5
                    )
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM code_search_registry AS repository
                    WHERE repository.canonical_index_id = candidate.index_id
                  )
                RETURNING candidate.*
                """,
                index_id,
                lease_token,
                lease_owner,
                now + lease_duration,
                now,
            )
            if claimed is None:
                continue
            try:
                maybe_awaitable = storage_deleter(claimed["storage_key"])
                if inspect.isawaitable(maybe_awaitable):
                    await maybe_awaitable
            except Exception as error:
                await self._pool.fetchrow(
                    """
                    /* registry:gc_failed */
                    UPDATE code_search_indexes
                    SET status = 'failed',
                        last_error = $3,
                        lease_token = NULL,
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        deleted_at = NULL,
                        updated_at = $4
                    WHERE index_id = $1
                      AND status = 'deleting'
                      AND lease_token = $2
                    RETURNING *
                    """,
                    index_id,
                    lease_token,
                    str(error),
                    self._now(),
                )
                failed.append(index_id)
                continue
            deleted_at = self._now()
            tombstoned = await self._pool.fetchrow(
                """
                /* registry:gc_deleted */
                UPDATE code_search_indexes
                SET status = 'deleted',
                    deleted_at = $3,
                    last_error = NULL,
                    lease_token = NULL,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    updated_at = $4
                WHERE index_id = $1
                  AND status = 'deleting'
                  AND lease_token = $2
                RETURNING *
                """,
                index_id,
                lease_token,
                deleted_at,
                deleted_at,
            )
            if tombstoned is None:
                raise IndexLeaseConflictError(
                    f"garbage-collection lease for index {index_id} was lost"
                )
            deleted.append(index_id)
        return GarbageCollectionResult(tuple(deleted), tuple(failed))

    async def _complete_index(
        self,
        status: str,
        index_id: UUID,
        lease_token: UUID | None,
        value: int | str,
    ) -> SemanticIndexRecord:
        if lease_token is None:
            raise IndexLeaseConflictError("a lease token is required")
        now = self._now()
        if status == "ready":
            marker = "/* registry:mark_ready */"
            assignments = """
                chunk_count = $3,
                completed_at = $4,
                last_error = NULL,
            """
        else:
            marker = (
                "/* registry:mark_failed */"
                if status == "failed"
                else "/* registry:mark_not_configured */"
            )
            assignments = """
                chunk_count = NULL,
                completed_at = NULL,
                last_error = $3,
            """
        row = await self._pool.fetchrow(
            f"""
            {marker}
            UPDATE code_search_indexes
            SET status = '{status}',
                {assignments}
                lease_token = NULL,
                lease_owner = NULL,
                lease_expires_at = NULL,
                updated_at = $4
            WHERE index_id = $1
              AND status = 'indexing'
              AND lease_token = $2
              AND lease_expires_at > $4
            RETURNING *
            """,
            index_id,
            lease_token,
            value,
            now,
        )
        if row is None:
            await self.get_index(index_id)
            raise IndexLeaseConflictError(
                f"index {index_id} is not owned by the supplied current lease"
            )
        return SemanticIndexRecord.from_row(row)

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("registry clock must return a timezone-aware datetime")
        return now

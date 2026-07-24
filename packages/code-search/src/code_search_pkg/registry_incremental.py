"""Incremental semantic-index registry operations and publication SQL."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from .identifiers import validate_slug
from .registry_models import (
    FileManifestEntry,
    IndexIdentity,
    IndexLeaseConflictError,
    IndexNotFoundError,
    RepositoryIdentity,
    RepositoryIdentityConflictError,
    SemanticIndexRecord,
    as_uuid,
)


PUBLISH_ATTEMPT_MANIFEST_SQL = """
/* registry:publish_attempt_manifest */
WITH current_lease AS (
    SELECT index_id
    FROM code_search_indexes
    WHERE index_id = $1
      AND status = 'indexing'
      AND lease_token = $2
      AND attempt_count = $3
      AND lease_expires_at > $4
    FOR UPDATE
),
published AS (
    INSERT INTO code_search_index_files (
        index_id, file_path, git_blob_id, git_entry_type, eligible,
        eligibility_reason, content_digest, chunk_digest, chunk_count
    )
    SELECT attempt.index_id, attempt.file_path, attempt.git_blob_id,
           attempt.git_entry_type, attempt.eligible,
           attempt.eligibility_reason, attempt.content_digest,
           attempt.chunk_digest, attempt.chunk_count
    FROM code_search_index_file_attempts AS attempt
    JOIN current_lease ON current_lease.index_id = attempt.index_id
    WHERE attempt.attempt_count = $3
    ON CONFLICT (index_id, file_path) DO UPDATE SET
        git_blob_id = EXCLUDED.git_blob_id,
        git_entry_type = EXCLUDED.git_entry_type,
        eligible = EXCLUDED.eligible,
        eligibility_reason = EXCLUDED.eligibility_reason,
        content_digest = EXCLUDED.content_digest,
        chunk_digest = EXCLUDED.chunk_digest,
        chunk_count = EXCLUDED.chunk_count
    RETURNING index_id
),
removed_stale AS (
    DELETE FROM code_search_index_files AS final
    USING current_lease
    WHERE final.index_id = current_lease.index_id
      AND NOT EXISTS (
          SELECT 1
          FROM code_search_index_file_attempts AS attempt
          WHERE attempt.index_id = final.index_id
            AND attempt.attempt_count = $3
            AND attempt.file_path = final.file_path
      )
),
discarded_old_attempts AS (
    DELETE FROM code_search_index_file_attempts AS attempt
    USING current_lease
    WHERE attempt.index_id = current_lease.index_id
      AND attempt.attempt_count <> $3
)
SELECT EXISTS (SELECT 1 FROM current_lease) AS lease_valid,
       (SELECT count(*) FROM published) AS entry_count
"""


class AsyncpgExecutor(Protocol):
    async def fetchrow(self, query: str, *args: Any) -> Mapping[str, Any] | None: ...

    async def fetch(self, query: str, *args: Any) -> Sequence[Mapping[str, Any]]: ...


class IncrementalRegistryMixin:
    """Fingerprint-parent, heartbeat, and file-manifest registry operations."""

    _pool: AsyncpgExecutor

    async def get_index(self, index_id: UUID) -> SemanticIndexRecord:
        raise NotImplementedError

    def _now(self) -> datetime:
        raise NotImplementedError

    async def get_repository_identity(self, repo_slug: str) -> RepositoryIdentity:
        """Read the exact durable root/common-directory binding for one slug."""
        validate_slug(repo_slug)
        row = await self._pool.fetchrow(
            """
            /* registry:get_repository_identity */
            SELECT repo_slug, repo_root, git_common_dir_fingerprint
            FROM code_search_registry
            WHERE repo_slug = $1
            """,
            repo_slug,
        )
        if row is None:
            raise IndexNotFoundError(f"repository {repo_slug!r} does not exist")
        return RepositoryIdentity.from_row(row)

    async def ensure_repository_identity(
        self,
        identity: RepositoryIdentity,
        *,
        embedder_model: str,
        embedding_dim: int,
    ) -> RepositoryIdentity:
        """Insert a slug binding or upgrade only its same-root legacy sentinel."""
        if identity.is_legacy:
            raise ValueError("new repository identities require a real fingerprint")
        if not embedder_model:
            raise ValueError("embedder_model must not be empty")
        if isinstance(embedding_dim, bool) or embedding_dim <= 0:
            raise ValueError("embedding_dim must be a positive integer")
        row = await self._pool.fetchrow(
            """
            /* registry:ensure_repository_identity */
            INSERT INTO code_search_registry (
                repo_slug, repo_root, git_common_dir_fingerprint,
                embedder_model, embedding_dim, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (repo_slug) DO UPDATE SET
                git_common_dir_fingerprint = CASE
                    WHEN code_search_registry.git_common_dir_fingerprint =
                         repeat('0', 64)
                    THEN EXCLUDED.git_common_dir_fingerprint
                    ELSE code_search_registry.git_common_dir_fingerprint
                END,
                updated_at = $6
            WHERE code_search_registry.repo_root = EXCLUDED.repo_root
              AND code_search_registry.git_common_dir_fingerprint IN (
                  EXCLUDED.git_common_dir_fingerprint, repeat('0', 64)
              )
            RETURNING repo_slug, repo_root, git_common_dir_fingerprint
            """,
            identity.repo_slug,
            identity.repo_root,
            identity.git_common_dir_fingerprint,
            embedder_model,
            embedding_dim,
            self._now(),
        )
        if row is None:
            raise RepositoryIdentityConflictError(
                f"repository slug {identity.repo_slug!r} is already bound"
            )
        return RepositoryIdentity.from_row(row)

    async def get_canonical_index_id(self, repo_slug: str) -> UUID | None:
        """Return the repository's current canonical pointer, including unset."""
        validate_slug(repo_slug)
        row = await self._pool.fetchrow(
            """
            /* registry:get_canonical */
            SELECT canonical_index_id
            FROM code_search_registry
            WHERE repo_slug = $1
            """,
            repo_slug,
        )
        if row is None:
            raise IndexNotFoundError(f"repository {repo_slug!r} does not exist")
        value = row["canonical_index_id"]
        return None if value is None else as_uuid(value)

    async def find_index(self, identity: IndexIdentity) -> SemanticIndexRecord | None:
        """Find one exact full natural key without creating or mutating it."""
        row = await self._pool.fetchrow(
            """
            /* registry:find */
            SELECT *
            FROM code_search_indexes
            WHERE repo_slug = $1
              AND namespace_kind = $2
              AND namespace_key = $3
              AND source_revision = $4
              AND embedder_model = $5
              AND embedding_dim = $6
              AND policy_fingerprint = $7
              AND pipeline_fingerprint = $8
              AND embedder_fingerprint = $9
            """,
            identity.repo_slug,
            identity.namespace_kind.value,
            identity.namespace_key,
            identity.source_revision,
            identity.embedder_model,
            identity.embedding_dim,
            identity.policy_fingerprint,
            identity.pipeline_fingerprint,
            identity.embedder_fingerprint,
        )
        return None if row is None else SemanticIndexRecord.from_row(row)

    async def renew_index_lease(
        self,
        index_id: UUID,
        lease_token: UUID | None,
        lease_duration: timedelta,
    ) -> SemanticIndexRecord:
        """Extend only the current, unexpired indexing lease."""
        if lease_token is None:
            raise IndexLeaseConflictError("a lease token is required")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        now = self._now()
        row = await self._pool.fetchrow(
            """
            /* registry:renew */
            UPDATE code_search_indexes
            SET lease_expires_at = GREATEST(lease_expires_at, $3),
                updated_at = $4
            WHERE index_id = $1
              AND status = 'indexing'
              AND lease_token = $2
              AND lease_expires_at > $4
            RETURNING *
            """,
            index_id,
            lease_token,
            now + lease_duration,
            now,
        )
        if row is None:
            await self.get_index(index_id)
            raise IndexLeaseConflictError(
                f"index {index_id} is not owned by the supplied current lease"
            )
        return SemanticIndexRecord.from_row(row)

    async def find_compatible_parents(
        self,
        identity: IndexIdentity,
        *,
        limit: int = 20,
    ) -> tuple[SemanticIndexRecord, ...]:
        """Return newest compatible ready candidates; callers prove Git ancestry."""
        if identity.is_legacy:
            return ()
        if limit <= 0:
            raise ValueError("limit must be positive")
        rows = await self._pool.fetch(
            """
            /* registry:compatible_parents */
            SELECT candidate.*
            FROM code_search_indexes AS candidate
            WHERE candidate.repo_slug = $1
              AND candidate.namespace_kind = $2
              AND candidate.namespace_key = $3
              AND candidate.embedder_model = $4
              AND candidate.embedding_dim = $5
              AND candidate.policy_fingerprint = $6
              AND candidate.pipeline_fingerprint = $7
              AND candidate.embedder_fingerprint = $8
              AND candidate.status = 'ready'
              AND candidate.policy_fingerprint <> repeat('0', 64)
              AND candidate.pipeline_fingerprint <> repeat('0', 64)
              AND candidate.embedder_fingerprint <> repeat('0', 64)
            ORDER BY candidate.completed_at DESC, candidate.created_at DESC
            LIMIT $9
            """,
            identity.repo_slug,
            identity.namespace_kind.value,
            identity.namespace_key,
            identity.embedder_model,
            identity.embedding_dim,
            identity.policy_fingerprint,
            identity.pipeline_fingerprint,
            identity.embedder_fingerprint,
            limit,
        )
        return tuple(SemanticIndexRecord.from_row(row) for row in rows)

    async def set_parent_index(
        self,
        index_id: UUID,
        lease_token: UUID | None,
        parent_index_id: UUID,
    ) -> SemanticIndexRecord:
        """Link a DB-compatible parent while holding the current indexing lease."""
        if lease_token is None:
            raise IndexLeaseConflictError("a lease token is required")
        if index_id == parent_index_id:
            raise ValueError("an index cannot be its own compatible parent")
        now = self._now()
        row = await self._pool.fetchrow(
            """
            /* registry:set_parent */
            UPDATE code_search_indexes
            SET parent_index_id = $3,
                updated_at = $4
            WHERE index_id = $1
              AND status = 'indexing'
              AND lease_token = $2
              AND lease_expires_at > $4
            RETURNING *
            """,
            index_id,
            lease_token,
            parent_index_id,
            now,
        )
        if row is None:
            await self.get_index(index_id)
            raise IndexLeaseConflictError(
                f"index {index_id} is not owned by the supplied current lease"
            )
        return SemanticIndexRecord.from_row(row)

    async def replace_attempt_manifest(
        self,
        index_id: UUID,
        lease_token: UUID | None,
        attempt_count: int,
        entries: Sequence[FileManifestEntry],
    ) -> tuple[FileManifestEntry, ...]:
        """Replace one attempt manifest in a current-lease-fenced SQL statement."""
        if lease_token is None:
            raise IndexLeaseConflictError("a lease token is required")
        if attempt_count <= 0:
            raise ValueError("attempt_count must be positive")
        ordered = tuple(sorted(entries, key=lambda entry: entry.file_path))
        paths = [entry.file_path for entry in ordered]
        if len(paths) != len(set(paths)):
            raise ValueError("attempt manifest file paths must be unique")
        payload = json.dumps(
            [entry.to_dict() for entry in ordered],
            separators=(",", ":"),
            sort_keys=True,
        )
        now = self._now()
        result = await self._pool.fetchrow(
            """
            /* registry:replace_attempt_manifest */
            WITH current_lease AS (
                SELECT index_id
                FROM code_search_indexes
                WHERE index_id = $1
                  AND status = 'indexing'
                  AND lease_token = $2
                  AND attempt_count = $3
                  AND lease_expires_at > $5
                FOR UPDATE
            ),
            payload AS (
                SELECT *
                FROM jsonb_to_recordset($4::jsonb) AS entry(
                    file_path text,
                    git_blob_id text,
                    git_entry_type text,
                    eligible boolean,
                    eligibility_reason text,
                    content_digest text,
                    chunk_digest text,
                    chunk_count integer
                )
            ),
            inserted AS (
                INSERT INTO code_search_index_file_attempts (
                    index_id, attempt_count, file_path, git_blob_id,
                    git_entry_type, eligible, eligibility_reason,
                    content_digest, chunk_digest, chunk_count
                )
                SELECT current_lease.index_id, $3, payload.file_path,
                       payload.git_blob_id, payload.git_entry_type,
                       payload.eligible, payload.eligibility_reason,
                       payload.content_digest, payload.chunk_digest,
                       payload.chunk_count
                FROM current_lease
                CROSS JOIN payload
                WHERE true
                ON CONFLICT (index_id, attempt_count, file_path) DO UPDATE SET
                    git_blob_id = EXCLUDED.git_blob_id,
                    git_entry_type = EXCLUDED.git_entry_type,
                    eligible = EXCLUDED.eligible,
                    eligibility_reason = EXCLUDED.eligibility_reason,
                    content_digest = EXCLUDED.content_digest,
                    chunk_digest = EXCLUDED.chunk_digest,
                    chunk_count = EXCLUDED.chunk_count
                RETURNING index_id
            ),
            removed_stale AS (
                DELETE FROM code_search_index_file_attempts AS attempt
                USING current_lease
                WHERE attempt.index_id = current_lease.index_id
                  AND attempt.attempt_count = $3
                  AND NOT EXISTS (
                      SELECT 1
                      FROM payload
                      WHERE payload.file_path = attempt.file_path
                  )
            )
            SELECT EXISTS (SELECT 1 FROM current_lease) AS lease_valid
            """,
            index_id,
            lease_token,
            attempt_count,
            payload,
            now,
        )
        if result is None or not result["lease_valid"]:
            await self.get_index(index_id)
            raise IndexLeaseConflictError(
                f"attempt {attempt_count} is not owned by the supplied current lease"
            )
        return ordered

    async def get_attempt_manifest(
        self, index_id: UUID, attempt_count: int
    ) -> tuple[FileManifestEntry, ...]:
        if attempt_count <= 0:
            raise ValueError("attempt_count must be positive")
        rows = await self._pool.fetch(
            """
            /* registry:get_attempt_manifest */
            SELECT *
            FROM code_search_index_file_attempts
            WHERE index_id = $1
              AND attempt_count = $2
            ORDER BY file_path
            """,
            index_id,
            attempt_count,
        )
        return tuple(FileManifestEntry.from_row(row) for row in rows)

    async def get_published_manifest(
        self, index_id: UUID
    ) -> tuple[FileManifestEntry, ...]:
        rows = await self._pool.fetch(
            """
            /* registry:get_published_manifest */
            SELECT *
            FROM code_search_index_files
            WHERE index_id = $1
            ORDER BY file_path
            """,
            index_id,
        )
        return tuple(FileManifestEntry.from_row(row) for row in rows)

    async def publish_attempt_manifest(
        self,
        index_id: UUID,
        lease_token: UUID | None,
        attempt_count: int,
        *,
        executor: AsyncpgExecutor | None = None,
    ) -> int:
        """Publish a manifest using a caller's transaction-bound connection.

        Storage publication passes the same asyncpg connection used for the
        attempt-table rename. This keeps rename and manifest replacement in one
        transaction while centralizing the current-lease fence.
        """
        if lease_token is None:
            raise IndexLeaseConflictError("a lease token is required")
        if attempt_count <= 0:
            raise ValueError("attempt_count must be positive")
        now = self._now()
        result = await (executor or self._pool).fetchrow(
            PUBLISH_ATTEMPT_MANIFEST_SQL,
            index_id,
            lease_token,
            attempt_count,
            now,
        )
        if result is None or not result["lease_valid"]:
            await self.get_index(index_id)
            raise IndexLeaseConflictError(
                f"attempt {attempt_count} is not owned by the supplied current lease"
            )
        return int(result["entry_count"])

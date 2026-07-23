"""Stateful asyncpg test double for the semantic-index registry."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID


class FakeRegistryPool:
    """Interpret the registry's named SQL statements against in-memory rows."""

    def __init__(self) -> None:
        self.repositories: dict[str, UUID | None] = {}
        self.indexes: dict[UUID, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def add_repository(self, repo_slug: str) -> None:
        self.repositories[repo_slug] = None

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        async with self._lock:
            sql = query
            if "/* registry:ensure */" in sql:
                return self._ensure(*args)
            if "/* registry:get */" in sql:
                return self._copy(self.indexes.get(args[0]))
            if "/* registry:claim */" in sql:
                return self._claim(*args)
            if "/* registry:mark_ready */" in sql:
                return self._complete(*args, status="ready")
            if "/* registry:mark_failed */" in sql:
                return self._complete(*args, status="failed")
            if "/* registry:mark_not_configured */" in sql:
                return self._complete(*args, status="not_configured")
            if "/* registry:promote */" in sql:
                return self._promote(*args)
            if "/* registry:gc_claim */" in sql:
                return self._gc_claim(*args)
            if "/* registry:gc_deleted */" in sql:
                return self._gc_complete(*args, success=True)
            if "/* registry:gc_failed */" in sql:
                return self._gc_complete(*args, success=False)
        raise AssertionError(f"unexpected SQL: {sql}")

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        async with self._lock:
            sql = query
            if "/* registry:gc_candidates */" not in sql:
                raise AssertionError(f"unexpected SQL: {sql}")
            now, limit = args
            candidates = [
                row
                for row in self.indexes.values()
                if row["namespace_kind"] in {"feature", "work_package"}
                and row["retention_until"] is not None
                and row["retention_until"] <= now
                and row["status"]
                in {"pending", "ready", "failed", "not_configured", "indexing"}
                and not (
                    row["status"] == "indexing"
                    and row["lease_expires_at"] is not None
                    and row["lease_expires_at"] > now
                )
                and all(
                    canonical_id != row["index_id"]
                    for canonical_id in self.repositories.values()
                )
            ]
            candidates.sort(key=lambda row: (row["retention_until"], row["created_at"]))
            return [dict(row) for row in candidates[:limit]]

    def _ensure(
        self,
        index_id: UUID,
        storage_key: str,
        repo_slug: str,
        namespace_kind: str,
        namespace_key: str,
        source_revision: str,
        embedder_model: str,
        embedding_dim: int,
        retention_until: datetime | None,
        now: datetime,
    ) -> dict[str, Any] | None:
        if repo_slug not in self.repositories:
            return None
        natural_key = (
            repo_slug,
            namespace_kind,
            namespace_key,
            source_revision,
            embedder_model,
            embedding_dim,
        )
        for row in self.indexes.values():
            if self._natural_key(row) == natural_key:
                return dict(row)
        row = {
            "index_id": index_id,
            "storage_key": storage_key,
            "repo_slug": repo_slug,
            "namespace_kind": namespace_kind,
            "namespace_key": namespace_key,
            "source_revision": source_revision,
            "embedder_model": embedder_model,
            "embedding_dim": embedding_dim,
            "status": "pending",
            "attempt_count": 0,
            "chunk_count": None,
            "last_error": None,
            "lease_token": None,
            "lease_owner": None,
            "lease_expires_at": None,
            "retention_until": retention_until,
            "started_at": None,
            "completed_at": None,
            "deleted_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self.indexes[index_id] = row
        return dict(row)

    def _claim(
        self,
        index_id: UUID,
        lease_token: UUID,
        lease_owner: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> dict[str, Any] | None:
        row = self.indexes.get(index_id)
        if row is None:
            return None
        available = row["status"] in {"pending", "failed", "not_configured"} or (
            row["status"] == "indexing"
            and row["lease_expires_at"] is not None
            and row["lease_expires_at"] <= now
        )
        if not available:
            return None
        row.update(
            status="indexing",
            attempt_count=row["attempt_count"] + 1,
            lease_token=lease_token,
            lease_owner=lease_owner,
            lease_expires_at=lease_expires_at,
            started_at=now,
            completed_at=None,
            deleted_at=None,
            last_error=None,
            updated_at=now,
        )
        return self._copy(row)

    def _complete(
        self,
        index_id: UUID,
        lease_token: UUID,
        value: int | str,
        now: datetime,
        *,
        status: str,
    ) -> dict[str, Any] | None:
        row = self.indexes.get(index_id)
        if (
            row is None
            or row["status"] != "indexing"
            or row["lease_token"] != lease_token
            or row["lease_expires_at"] is None
            or row["lease_expires_at"] <= now
        ):
            return None
        row.update(
            status=status,
            lease_token=None,
            lease_owner=None,
            lease_expires_at=None,
            updated_at=now,
        )
        if status == "ready":
            row.update(chunk_count=value, completed_at=now, last_error=None)
        else:
            row.update(chunk_count=None, completed_at=None, last_error=value)
        return self._copy(row)

    def _promote(
        self,
        repo_slug: str,
        index_id: UUID,
        check_expected: bool,
        expected_current: UUID | None,
    ) -> dict[str, Any] | None:
        candidate = self.indexes.get(index_id)
        if (
            repo_slug not in self.repositories
            or candidate is None
            or candidate["repo_slug"] != repo_slug
            or candidate["namespace_kind"] != "main"
            or candidate["status"] != "ready"
            or (check_expected and self.repositories[repo_slug] != expected_current)
        ):
            return None
        self.repositories[repo_slug] = index_id
        return {"canonical_index_id": index_id}

    def _gc_claim(
        self,
        index_id: UUID,
        lease_token: UUID,
        lease_owner: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> dict[str, Any] | None:
        row = self.indexes.get(index_id)
        if (
            row is None
            or row["namespace_kind"] == "main"
            or row["retention_until"] is None
            or row["retention_until"] > now
            or row["status"]
            not in {"pending", "ready", "failed", "not_configured", "indexing"}
            or (
                row["status"] == "indexing"
                and row["lease_expires_at"] is not None
                and row["lease_expires_at"] > now
            )
            or any(
                canonical_id == index_id for canonical_id in self.repositories.values()
            )
        ):
            return None
        row.update(
            status="deleting",
            lease_token=lease_token,
            lease_owner=lease_owner,
            lease_expires_at=lease_expires_at,
            updated_at=now,
        )
        return self._copy(row)

    def _gc_complete(
        self,
        index_id: UUID,
        lease_token: UUID,
        value: str | datetime,
        now: datetime,
        *,
        success: bool,
    ) -> dict[str, Any] | None:
        row = self.indexes.get(index_id)
        if (
            row is None
            or row["status"] != "deleting"
            or row["lease_token"] != lease_token
        ):
            return None
        row.update(
            status="deleted" if success else "failed",
            lease_token=None,
            lease_owner=None,
            lease_expires_at=None,
            updated_at=now,
        )
        if success:
            row.update(deleted_at=value, last_error=None)
        else:
            row.update(deleted_at=None, last_error=value)
        return self._copy(row)

    @staticmethod
    def _copy(row: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if row is None else dict(row)

    @staticmethod
    def _natural_key(row: dict[str, Any]) -> tuple[Any, ...]:
        return (
            row["repo_slug"],
            row["namespace_kind"],
            row["namespace_key"],
            row["source_revision"],
            row["embedder_model"],
            row["embedding_dim"],
        )

"""Pure identity, lifecycle, and record types for semantic index state."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from .identifiers import validate_slug, validate_storage_key


_REVISION_RE = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")


class NamespaceKind(StrEnum):
    MAIN = "main"
    FEATURE = "feature"
    WORK_PACKAGE = "work_package"


class IndexStatus(StrEnum):
    PENDING = "pending"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"
    NOT_CONFIGURED = "not_configured"
    DELETING = "deleting"
    DELETED = "deleted"


class IndexRegistryError(RuntimeError):
    """Base class for semantic-index registry errors."""


class IndexNotFoundError(IndexRegistryError):
    """The requested index or repository does not exist."""


class IndexLeaseConflictError(IndexRegistryError):
    """The lifecycle transition did not own a current lease."""


class IndexStateConflictError(IndexRegistryError):
    """The index cannot transition from its current state."""


class CanonicalPromotionError(IndexRegistryError):
    """Canonical promotion failed validation or compare-and-swap."""


@dataclass(frozen=True, slots=True)
class IndexIdentity:
    repo_slug: str
    namespace_kind: NamespaceKind
    namespace_key: str
    source_revision: str
    embedder_model: str
    embedding_dim: int

    def __post_init__(self) -> None:
        validate_slug(self.repo_slug)
        try:
            kind = NamespaceKind(self.namespace_kind)
        except ValueError as error:
            raise ValueError(
                f"invalid namespace kind {self.namespace_kind!r}"
            ) from error
        object.__setattr__(self, "namespace_kind", kind)
        if not 1 <= len(self.namespace_key) <= 255:
            raise ValueError("namespace_key must contain between 1 and 255 characters")
        if kind is NamespaceKind.MAIN and self.namespace_key != "main":
            raise ValueError("main indexes must use namespace_key='main'")
        if not _REVISION_RE.fullmatch(self.source_revision):
            raise ValueError(
                "source_revision must be a full lowercase 40- or 64-hex object ID"
            )
        if not self.embedder_model:
            raise ValueError("embedder_model must not be empty")
        if isinstance(self.embedding_dim, bool) or self.embedding_dim <= 0:
            raise ValueError("embedding_dim must be a positive integer")

    @property
    def natural_key(self) -> tuple[str, str, str, str, str, int]:
        """Return the ordered identity used by the database uniqueness constraint."""
        return (
            self.repo_slug,
            self.namespace_kind.value,
            self.namespace_key,
            self.source_revision,
            self.embedder_model,
            self.embedding_dim,
        )


@dataclass(frozen=True, slots=True)
class SemanticIndexRecord:
    index_id: UUID
    storage_key: str
    repo_slug: str
    namespace_kind: NamespaceKind
    namespace_key: str
    source_revision: str
    embedder_model: str
    embedding_dim: int
    status: IndexStatus
    attempt_count: int
    chunk_count: int | None
    last_error: str | None
    lease_token: UUID | None
    lease_owner: str | None
    lease_expires_at: datetime | None
    retention_until: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> SemanticIndexRecord:
        values = dict(row)
        values["index_id"] = as_uuid(values["index_id"])
        values["namespace_kind"] = NamespaceKind(values["namespace_kind"])
        values["status"] = IndexStatus(values["status"])
        if values["lease_token"] is not None:
            values["lease_token"] = as_uuid(values["lease_token"])
        return cls(**values)

    def __post_init__(self) -> None:
        validate_storage_key(self.storage_key)
        IndexIdentity(
            self.repo_slug,
            self.namespace_kind,
            self.namespace_key,
            self.source_revision,
            self.embedder_model,
            self.embedding_dim,
        )
        if self.attempt_count < 0:
            raise ValueError("attempt_count must not be negative")
        if self.chunk_count is not None and self.chunk_count < 0:
            raise ValueError("chunk_count must not be negative")
        leased = self.status in {IndexStatus.INDEXING, IndexStatus.DELETING}
        lease_shape = (
            self.lease_token is not None
            and bool(self.lease_owner)
            and self.lease_expires_at is not None
        )
        if leased != lease_shape:
            raise ValueError("lease fields must be populated exactly for leased states")
        if self.status is IndexStatus.READY and (
            self.chunk_count is None
            or self.completed_at is None
            or self.last_error is not None
        ):
            raise ValueError(
                "ready indexes require chunks and completion without an error"
            )
        if self.status is IndexStatus.DELETED and self.deleted_at is None:
            raise ValueError("deleted indexes require deleted_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "index_id": str(self.index_id),
            "storage_key": self.storage_key,
            "repo_slug": self.repo_slug,
            "namespace_kind": self.namespace_kind.value,
            "namespace_key": self.namespace_key,
            "source_revision": self.source_revision,
            "embedder_model": self.embedder_model,
            "embedding_dim": self.embedding_dim,
            "status": self.status.value,
            "attempt_count": self.attempt_count,
            "chunk_count": self.chunk_count,
            "last_error": self.last_error,
            "lease_token": _json_value(self.lease_token),
            "lease_owner": self.lease_owner,
            "lease_expires_at": _json_value(self.lease_expires_at),
            "retention_until": _json_value(self.retention_until),
            "started_at": _json_value(self.started_at),
            "completed_at": _json_value(self.completed_at),
            "deleted_at": _json_value(self.deleted_at),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class GarbageCollectionResult:
    deleted: tuple[UUID, ...]
    failed: tuple[UUID, ...]


def as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(value)


def _json_value(value: UUID | datetime | None) -> str | None:
    if value is None:
        return None
    return str(value) if isinstance(value, UUID) else value.isoformat()

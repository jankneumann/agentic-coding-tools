"""Pure identity, lifecycle, and record types for semantic index state."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from .identifiers import validate_slug, validate_storage_key


_REVISION_RE = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_DIGEST_RE = _FINGERPRINT_RE
_GIT_OBJECT_RE = _REVISION_RE

LEGACY_FINGERPRINT = "0" * 64


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


class RepositoryIdentityConflictError(IndexRegistryError):
    """A repository slug is already bound to another durable Git identity."""


@dataclass(frozen=True, slots=True)
class RepositoryIdentity:
    """Stable slug mapping used to prove source worktree identity."""

    repo_slug: str
    repo_root: str
    git_common_dir_fingerprint: str

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> RepositoryIdentity:
        return cls(
            repo_slug=row["repo_slug"],
            repo_root=row["repo_root"],
            git_common_dir_fingerprint=row["git_common_dir_fingerprint"],
        )

    def __post_init__(self) -> None:
        validate_slug(self.repo_slug)
        root = Path(self.repo_root)
        if (
            not root.is_absolute()
            or ".." in root.parts
            or root.as_posix() != self.repo_root
        ):
            raise ValueError("repo_root must be a canonical absolute path")
        if not _FINGERPRINT_RE.fullmatch(self.git_common_dir_fingerprint):
            raise ValueError(
                "git_common_dir_fingerprint must be 64 lowercase hexadecimal characters"
            )

    @property
    def is_legacy(self) -> bool:
        return self.git_common_dir_fingerprint == LEGACY_FINGERPRINT


@dataclass(frozen=True, slots=True)
class IndexIdentity:
    repo_slug: str
    namespace_kind: NamespaceKind
    namespace_key: str
    source_revision: str
    embedder_model: str
    embedding_dim: int
    policy_fingerprint: str = LEGACY_FINGERPRINT
    pipeline_fingerprint: str = LEGACY_FINGERPRINT
    embedder_fingerprint: str = LEGACY_FINGERPRINT

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
        for name in (
            "policy_fingerprint",
            "pipeline_fingerprint",
            "embedder_fingerprint",
        ):
            if not _FINGERPRINT_RE.fullmatch(getattr(self, name)):
                raise ValueError(f"{name} must be 64 lowercase hexadecimal characters")
        legacy_fields = (
            self.policy_fingerprint == LEGACY_FINGERPRINT,
            self.pipeline_fingerprint == LEGACY_FINGERPRINT,
            self.embedder_fingerprint == LEGACY_FINGERPRINT,
        )
        if any(legacy_fields) and not all(legacy_fields):
            raise ValueError(
                "the legacy fingerprint sentinel must apply to all fingerprints"
            )

    @property
    def natural_key(self) -> tuple[str | int, ...]:
        """Return the ordered identity used by the database uniqueness constraint."""
        legacy_key: tuple[str | int, ...] = (
            self.repo_slug,
            self.namespace_kind.value,
            self.namespace_key,
            self.source_revision,
            self.embedder_model,
            self.embedding_dim,
        )
        if self.is_legacy:
            return legacy_key
        return legacy_key + (
            self.policy_fingerprint,
            self.pipeline_fingerprint,
            self.embedder_fingerprint,
        )

    @property
    def is_legacy(self) -> bool:
        return (
            self.policy_fingerprint == LEGACY_FINGERPRINT
            and self.pipeline_fingerprint == LEGACY_FINGERPRINT
            and self.embedder_fingerprint == LEGACY_FINGERPRINT
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
    policy_fingerprint: str = LEGACY_FINGERPRINT
    pipeline_fingerprint: str = LEGACY_FINGERPRINT
    embedder_fingerprint: str = LEGACY_FINGERPRINT
    parent_index_id: UUID | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> SemanticIndexRecord:
        values = dict(row)
        values["index_id"] = as_uuid(values["index_id"])
        values["namespace_kind"] = NamespaceKind(values["namespace_kind"])
        values["status"] = IndexStatus(values["status"])
        values.setdefault("policy_fingerprint", LEGACY_FINGERPRINT)
        values.setdefault("pipeline_fingerprint", LEGACY_FINGERPRINT)
        values.setdefault("embedder_fingerprint", LEGACY_FINGERPRINT)
        values.setdefault("parent_index_id", None)
        if values["lease_token"] is not None:
            values["lease_token"] = as_uuid(values["lease_token"])
        if values["parent_index_id"] is not None:
            values["parent_index_id"] = as_uuid(values["parent_index_id"])
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
            self.policy_fingerprint,
            self.pipeline_fingerprint,
            self.embedder_fingerprint,
        )
        if self.parent_index_id == self.index_id:
            raise ValueError("an index cannot be its own compatible parent")
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
        payload = {
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
        if not self.identity.is_legacy or self.parent_index_id is not None:
            payload.update(
                policy_fingerprint=self.policy_fingerprint,
                pipeline_fingerprint=self.pipeline_fingerprint,
                embedder_fingerprint=self.embedder_fingerprint,
                parent_index_id=_json_value(self.parent_index_id),
            )
        return payload

    @property
    def identity(self) -> IndexIdentity:
        return IndexIdentity(
            self.repo_slug,
            self.namespace_kind,
            self.namespace_key,
            self.source_revision,
            self.embedder_model,
            self.embedding_dim,
            self.policy_fingerprint,
            self.pipeline_fingerprint,
            self.embedder_fingerprint,
        )


@dataclass(frozen=True, slots=True)
class FileManifestEntry:
    """One revision-specific file eligibility and chunk-set manifest entry."""

    file_path: str
    git_blob_id: str | None
    git_entry_type: str | None
    eligible: bool
    eligibility_reason: str
    content_digest: str | None
    chunk_digest: str | None
    chunk_count: int

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> FileManifestEntry:
        values = dict(row)
        values.pop("index_id", None)
        values.pop("attempt_count", None)
        return cls(**values)

    def __post_init__(self) -> None:
        path = PurePosixPath(self.file_path)
        if (
            not self.file_path
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in self.file_path
            or self.file_path != path.as_posix()
        ):
            raise ValueError("file_path must be a normalized repository-relative path")
        if not self.eligibility_reason:
            raise ValueError("eligibility_reason must not be empty")
        if isinstance(self.chunk_count, bool) or self.chunk_count < 0:
            raise ValueError("chunk_count must not be negative")
        if self.git_blob_id is not None and not _GIT_OBJECT_RE.fullmatch(
            self.git_blob_id
        ):
            raise ValueError("git_blob_id must be a full lowercase Git object ID")
        if self.git_entry_type not in {None, "blob", "symlink"}:
            raise ValueError("git_entry_type must be 'blob', 'symlink', or None")
        for name in ("content_digest", "chunk_digest"):
            value = getattr(self, name)
            if value is not None and not _DIGEST_RE.fullmatch(value):
                raise ValueError(f"{name} must be 64 lowercase hexadecimal characters")
        if self.eligible and (
            self.git_blob_id is None
            or self.git_entry_type is None
            or self.content_digest is None
            or self.chunk_digest is None
        ):
            raise ValueError("eligible manifest entries require all digest metadata")
        if not self.eligible and self.chunk_count != 0:
            raise ValueError("ineligible manifest entries cannot contain chunks")

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "git_blob_id": self.git_blob_id,
            "git_entry_type": self.git_entry_type,
            "eligible": self.eligible,
            "eligibility_reason": self.eligibility_reason,
            "content_digest": self.content_digest,
            "chunk_digest": self.chunk_digest,
            "chunk_count": self.chunk_count,
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

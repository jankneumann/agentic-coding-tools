"""Pure contracts and helpers for dependency-injected indexing orchestration."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol, TypeVar
from uuid import UUID

from .embedding_protocol import EmbeddingReadiness
from .registry_models import (
    FileManifestEntry,
    IndexIdentity,
    IndexLeaseConflictError,
    NamespaceKind,
    SemanticIndexRecord,
)
from .source_proof import SourceProof, SourceProofError
from .storage_pg import StorageAttempt, StorageVerification


_T = TypeVar("_T")
_LEASE_CONFLICT_MESSAGE = "another worker owns the current indexing lease"


class IndexExecutionStatus(StrEnum):
    READY = "ready"
    NOT_CONFIGURED = "not_configured"
    FAILED = "failed"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class IndexExecutionError:
    code: str
    message: str

    def __post_init__(self) -> None:
        if (
            not self.code
            or len(self.code) > 64
            or not self.code[0].islower()
            or any(
                char not in "abcdefghijklmnopqrstuvwxyz0123456789_"
                for char in self.code
            )
        ):
            raise ValueError("error code must be a bounded lowercase identifier")
        if not self.message or len(self.message) > 1000:
            raise ValueError("error message must contain between 1 and 1000 characters")
        if any(ord(char) < 32 for char in self.message):
            raise ValueError("error message must not contain control characters")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class IndexExecutionCounts:
    eligible_files: int = 0
    copied_files: int = 0
    changed_files: int = 0
    removed_files: int = 0
    skipped_files: int = 0
    embedded_chunks: int = 0
    chunks: int = 0

    def __post_init__(self) -> None:
        for value in (
            self.eligible_files,
            self.copied_files,
            self.changed_files,
            self.removed_files,
            self.skipped_files,
            self.embedded_chunks,
            self.chunks,
        ):
            if isinstance(value, bool) or value < 0:
                raise ValueError("execution counts must not be negative")

    def to_dict(self) -> dict[str, int]:
        return {
            "eligible_files": self.eligible_files,
            "copied_files": self.copied_files,
            "changed_files": self.changed_files,
            "removed_files": self.removed_files,
            "skipped_files": self.skipped_files,
            "embedded_chunks": self.embedded_chunks,
            "chunks": self.chunks,
        }


@dataclass(frozen=True, slots=True)
class IndexExecutionResult:
    status: IndexExecutionStatus
    durable: bool
    reused: bool
    repo_slug: str
    source_revision: str
    namespace_kind: NamespaceKind
    namespace_key: str
    index_id: UUID | None
    storage_key: str | None
    parent_index_id: UUID | None = None
    parent_revision: str | None = None
    promoted: bool = False
    counts: IndexExecutionCounts = field(default_factory=IndexExecutionCounts)
    error: IndexExecutionError | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", IndexExecutionStatus(self.status))
        object.__setattr__(self, "namespace_kind", NamespaceKind(self.namespace_kind))
        if self.durable != (self.index_id is not None and self.storage_key is not None):
            raise ValueError("durable results require an index ID and storage key")
        if self.status is IndexExecutionStatus.READY:
            if not self.durable or self.error is not None:
                raise ValueError("ready results must be durable and error-free")
        elif self.error is None:
            raise ValueError("non-ready results require a sanitized error")
        if self.reused and self.status is not IndexExecutionStatus.READY:
            raise ValueError("only ready results may be reused")
        if (self.parent_index_id is None) != (self.parent_revision is None):
            raise ValueError("parent identity and revision must be present together")
        if (
            self.parent_index_id is not None
            and self.status is not IndexExecutionStatus.READY
        ):
            raise ValueError("only ready results may expose an incremental parent")
        if self.promoted and (
            self.status is not IndexExecutionStatus.READY
            or self.namespace_kind is not NamespaceKind.MAIN
            or self.namespace_key != "main"
        ):
            raise ValueError("only a ready main index may be promoted")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "durable": self.durable,
            "reused": self.reused,
            "repo_slug": self.repo_slug,
            "source_revision": self.source_revision,
            "namespace_kind": self.namespace_kind.value,
            "namespace_key": self.namespace_key,
            "index_id": None if self.index_id is None else str(self.index_id),
            "storage_key": self.storage_key,
            "parent_index_id": (
                None if self.parent_index_id is None else str(self.parent_index_id)
            ),
            "parent_revision": self.parent_revision,
            "promoted": self.promoted,
            "counts": self.counts.to_dict(),
            "error": None if self.error is None else self.error.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class IndexExecutionRequest:
    identity: IndexIdentity
    repo_root: str
    lease_owner: str
    lease_duration: timedelta
    full_rebuild: bool = False
    retention_until: datetime | None = None
    parent_candidate_limit: int = 20

    def __post_init__(self) -> None:
        if not self.repo_root:
            raise ValueError("repo_root must not be empty")
        if not self.lease_owner:
            raise ValueError("lease_owner must not be empty")
        if self.lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        if self.parent_candidate_limit <= 0:
            raise ValueError("parent_candidate_limit must be positive")


@dataclass(frozen=True, slots=True)
class IndexBuildPlan:
    """Pre-finalized manifest rows plus the physical delta to materialize.

    ``entries`` contains copied eligible rows and final ineligible rows.
    Changed eligible paths are deliberately absent until ``process_changed``
    returns their measured chunk metadata.
    """

    entries: tuple[FileManifestEntry, ...]
    unchanged_paths: tuple[str, ...]
    changed_paths: tuple[str, ...]
    removed_files: int = 0

    def __post_init__(self) -> None:
        entries = tuple(sorted(self.entries, key=lambda entry: entry.file_path))
        unchanged = tuple(sorted(self.unchanged_paths))
        changed = tuple(sorted(self.changed_paths))
        object.__setattr__(self, "entries", entries)
        object.__setattr__(self, "unchanged_paths", unchanged)
        object.__setattr__(self, "changed_paths", changed)
        if len({entry.file_path for entry in entries}) != len(entries):
            raise ValueError("manifest paths must be unique")
        if len(set(unchanged)) != len(unchanged) or len(set(changed)) != len(changed):
            raise ValueError("delta paths must be unique")
        if set(unchanged) & set(changed):
            raise ValueError("unchanged and changed paths must be disjoint")
        entry_paths = {entry.file_path for entry in entries}
        eligible = {entry.file_path for entry in entries if entry.eligible}
        if not set(unchanged).issubset(eligible):
            raise ValueError(
                "unchanged paths must be finalized eligible manifest paths"
            )
        if set(changed) & entry_paths:
            raise ValueError("changed paths must not have pre-finalized manifest rows")
        if isinstance(self.removed_files, bool) or self.removed_files < 0:
            raise ValueError("removed_files must not be negative")


@dataclass(frozen=True, slots=True)
class IndexProcessResult:
    """Final measured manifest rows for every changed eligible path."""

    entries: tuple[FileManifestEntry, ...]
    embedded_chunks: int

    def __post_init__(self) -> None:
        entries = tuple(sorted(self.entries, key=lambda entry: entry.file_path))
        object.__setattr__(self, "entries", entries)
        if len({entry.file_path for entry in entries}) != len(entries):
            raise ValueError("processed manifest paths must be unique")
        if any(not entry.eligible for entry in entries):
            raise ValueError("processed manifest rows must be eligible")
        if isinstance(self.embedded_chunks, bool) or self.embedded_chunks < 0:
            raise ValueError("embedded_chunks must not be negative")

    @property
    def processed_files(self) -> int:
        return len(self.entries)


class IndexRegistry(Protocol):
    async def find_index(
        self, identity: IndexIdentity
    ) -> SemanticIndexRecord | None: ...

    async def ensure_index(
        self,
        identity: IndexIdentity,
        *,
        retention_until: datetime | None = None,
    ) -> SemanticIndexRecord: ...

    async def claim_index(
        self,
        index_id: UUID,
        *,
        lease_owner: str,
        lease_duration: timedelta,
    ) -> SemanticIndexRecord: ...

    async def get_index(self, index_id: UUID) -> SemanticIndexRecord: ...

    async def renew_index_lease(
        self,
        index_id: UUID,
        lease_token: UUID | None,
        lease_duration: timedelta,
    ) -> SemanticIndexRecord: ...

    async def find_compatible_parents(
        self, identity: IndexIdentity, *, limit: int = 20
    ) -> tuple[SemanticIndexRecord, ...]: ...

    async def set_parent_index(
        self, index_id: UUID, lease_token: UUID | None, parent_index_id: UUID
    ) -> SemanticIndexRecord: ...

    async def get_published_manifest(
        self, index_id: UUID
    ) -> tuple[FileManifestEntry, ...]: ...

    async def replace_attempt_manifest(
        self,
        index_id: UUID,
        lease_token: UUID | None,
        attempt_count: int,
        entries: Sequence[FileManifestEntry],
    ) -> tuple[FileManifestEntry, ...]: ...

    async def get_canonical_index_id(self, repo_slug: str) -> UUID | None: ...

    async def mark_ready(
        self, index_id: UUID, lease_token: UUID | None, *, chunk_count: int
    ) -> SemanticIndexRecord: ...

    async def mark_failed(
        self, index_id: UUID, lease_token: UUID | None, error: str
    ) -> SemanticIndexRecord: ...

    async def mark_not_configured(
        self, index_id: UUID, lease_token: UUID | None, reason: str
    ) -> SemanticIndexRecord: ...

    async def promote_canonical(
        self,
        repo_slug: str,
        index_id: UUID,
        *,
        expected_current_index_id: UUID | None,
    ) -> UUID: ...


class IndexStorage(Protocol):
    async def prepare_attempt(
        self, record: SemanticIndexRecord, *, embedding_dim: int
    ) -> StorageAttempt: ...

    async def copy_unchanged(
        self,
        parent_storage_key: str,
        attempt: StorageAttempt,
        paths: Sequence[str],
    ) -> int: ...

    async def verify_attempt(
        self,
        attempt: StorageAttempt,
        *,
        expected_chunks: int,
        expected_files: int,
    ) -> StorageVerification: ...

    async def publish_attempt(
        self, record: SemanticIndexRecord, attempt: StorageAttempt
    ) -> None: ...

    async def cleanup_attempt(self, attempt: StorageAttempt) -> None: ...


ProofSource = Callable[[IndexExecutionRequest], SourceProof | Awaitable[SourceProof]]
VerifySource = Callable[[SourceProof], SourceProof | Awaitable[SourceProof]]
CheckReadiness = Callable[[], Awaitable[EmbeddingReadiness]]
GitAncestry = Callable[[str, str], bool | Awaitable[bool]]
BuildPlan = Callable[
    [
        SourceProof,
        SemanticIndexRecord | None,
        tuple[FileManifestEntry, ...],
    ],
    IndexBuildPlan | Awaitable[IndexBuildPlan],
]
ProcessChanged = Callable[
    [StorageAttempt, tuple[str, ...]],
    IndexProcessResult | Awaitable[IndexProcessResult],
]


class LeaseGuard:
    def __init__(
        self,
        registry: IndexRegistry,
        record: SemanticIndexRecord,
        lease_duration: timedelta,
        *,
        interval: float | None,
    ) -> None:
        self._registry = registry
        self._record = record
        self._lease_duration = lease_duration
        duration_seconds = lease_duration.total_seconds()
        self._interval = interval or max(0.1, duration_seconds / 3)
        self._stop = asyncio.Event()
        self._lost = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._heartbeat())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task

    async def run(self, operation: Awaitable[_T]) -> _T:
        operation_task = asyncio.ensure_future(operation)
        lost_task = asyncio.create_task(self._lost.wait())
        await asyncio.wait(
            {operation_task, lost_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if self._lost.is_set():
            operation_task.cancel()
            await asyncio.gather(operation_task, return_exceptions=True)
            lost_task.cancel()
            await asyncio.gather(lost_task, return_exceptions=True)
            raise IndexLeaseConflictError(_LEASE_CONFLICT_MESSAGE)
        lost_task.cancel()
        await asyncio.gather(lost_task, return_exceptions=True)
        return operation_task.result()

    async def _heartbeat(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
                return
            except TimeoutError:
                pass
            try:
                await self._registry.renew_index_lease(
                    self._record.index_id,
                    self._record.lease_token,
                    self._lease_duration,
                )
            except Exception:
                self._lost.set()
                return


async def await_maybe(value: _T | Awaitable[_T]) -> _T:
    if inspect.isawaitable(value):
        return await value
    return value


async def best_effort_cleanup(storage: IndexStorage, attempt: StorageAttempt) -> None:
    try:
        await storage.cleanup_attempt(attempt)
    except Exception:
        pass


def safe_source_message(error: SourceProofError) -> str:
    message = str(error)
    if not message or len(message) > 1000 or any(ord(char) < 32 for char in message):
        return "the exact source revision could not be proven"
    return message

"""Pure result and finalized-manifest assembly for indexing orchestration."""

from __future__ import annotations

from .indexing_runtime_models import (
    IndexBuildPlan,
    IndexExecutionCounts,
    IndexExecutionError,
    IndexExecutionResult,
    IndexExecutionStatus,
    IndexProcessResult,
)
from .registry_models import (
    FileManifestEntry,
    IndexIdentity,
    SemanticIndexRecord,
)


LEASE_CONFLICT_MESSAGE = "another worker owns the current indexing lease"


def merge_manifest(
    plan: IndexBuildPlan,
    processed: IndexProcessResult,
) -> tuple[FileManifestEntry, ...]:
    entries = tuple(
        sorted(plan.entries + processed.entries, key=lambda entry: entry.file_path)
    )
    if len({entry.file_path for entry in entries}) != len(entries):
        raise RuntimeError("finalized manifest paths are not unique")
    return entries


def success_result(
    record: SemanticIndexRecord,
    plan: IndexBuildPlan,
    processed: IndexProcessResult,
    entries: tuple[FileManifestEntry, ...],
    *,
    parent: SemanticIndexRecord | None,
    promoted: bool,
) -> IndexExecutionResult:
    eligible = [entry for entry in entries if entry.eligible]
    return durable_result(
        record,
        IndexExecutionStatus.READY,
        parent=parent,
        promoted=promoted,
        counts=IndexExecutionCounts(
            eligible_files=len(eligible),
            copied_files=len(plan.unchanged_paths),
            changed_files=len(plan.changed_paths),
            removed_files=plan.removed_files,
            skipped_files=len(entries) - len(eligible),
            embedded_chunks=processed.embedded_chunks,
            chunks=sum(entry.chunk_count for entry in eligible),
        ),
    )


def error_result(
    record: SemanticIndexRecord,
    status: IndexExecutionStatus,
    code: str,
    message: str,
) -> IndexExecutionResult:
    return durable_result(
        record,
        status,
        error=IndexExecutionError(code, message),
    )


def conflict_result(record: SemanticIndexRecord) -> IndexExecutionResult:
    return error_result(
        record,
        IndexExecutionStatus.CONFLICT,
        "lease_conflict",
        LEASE_CONFLICT_MESSAGE,
    )


def ephemeral_failure(
    identity: IndexIdentity,
    *,
    code: str = "registry_unavailable",
    message: str = "semantic indexing could not create a durable operation",
) -> IndexExecutionResult:
    return IndexExecutionResult(
        status=IndexExecutionStatus.FAILED,
        durable=False,
        reused=False,
        repo_slug=identity.repo_slug,
        source_revision=identity.source_revision,
        namespace_kind=identity.namespace_kind,
        namespace_key=identity.namespace_key,
        index_id=None,
        storage_key=None,
        error=IndexExecutionError(code, message),
    )


def durable_result(
    record: SemanticIndexRecord,
    status: IndexExecutionStatus,
    *,
    reused: bool = False,
    parent: SemanticIndexRecord | None = None,
    promoted: bool = False,
    counts: IndexExecutionCounts | None = None,
    error: IndexExecutionError | None = None,
) -> IndexExecutionResult:
    return IndexExecutionResult(
        status=status,
        durable=True,
        reused=reused,
        repo_slug=record.repo_slug,
        source_revision=record.source_revision,
        namespace_kind=record.namespace_kind,
        namespace_key=record.namespace_key,
        index_id=record.index_id,
        storage_key=record.storage_key,
        parent_index_id=None if parent is None else parent.index_id,
        parent_revision=None if parent is None else parent.source_revision,
        promoted=promoted,
        counts=counts or IndexExecutionCounts(),
        error=error,
    )

"""Durable, cross-process operation store backed by the Git common directory.

Mutable operation records live below ``<git-common-dir>/project-context/
refresh-operations/<operation-id>/`` so every linked worktree and later process
in one clone shares state, while retry timestamps, attempt counters, and lock
files stay out of Git-tracked content.

Every mutation acquires a per-operation advisory lock, reloads and validates the
current record, applies exactly one legal transition, increments
``record_revision``, and replaces the record atomically. Readers validate the
whole record and never infer a default status from a missing or partial file.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path

from atomic import atomic_write_json, file_lock, read_json
from models import (
    ContextRefreshError,
    CorruptRecordError,
    DuplicateProducerError,
    IdentityMismatchError,
    InvalidTransitionError,
    ManifestPointer,
    ManifestPointerStatus,
    OperationRecord,
    OperationState,
    ProducerResult,
    RecordValidationError,
    SafeError,
    SemanticIndexReference,
    can_transition,
    derive_operation_id,
    ensure_git_revision,
    initial_semantic_index,
)

_STORE_SUBDIR = ("project-context", "refresh-operations")
_FINALIZE_STATES = frozenset(
    {OperationState.SUCCEEDED, OperationState.DEGRADED, OperationState.FAILED}
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_git_common_dir(repo_path: Path | str) -> Path:
    """Resolve the shared Git common directory for *repo_path*.

    For a linked worktree this returns the main clone's ``.git`` directory, so
    the operation ledger is shared across worktrees. The store is never derived
    from a worktree-local ``.git`` file path.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        check=True,
    )
    common = Path(result.stdout.strip())
    if not common.is_absolute():
        common = Path(repo_path) / common
    # Resolve symlinks so the main checkout and its linked worktrees agree on
    # one canonical ledger path (e.g. macOS /var -> /private/var).
    return common.resolve()


class OperationStore:
    """Filesystem-backed durable store for refresh operations.

    Pass *base_dir* only for adapter or test seams; the default resolves the
    store location through Git so cross-worktree sharing is guaranteed.
    """

    def __init__(self, repo_path: Path | str = ".", *, base_dir: Path | str | None = None) -> None:
        self._repo_path = Path(repo_path)
        if base_dir is not None:
            self._base = Path(base_dir)
        else:
            self._base = resolve_git_common_dir(self._repo_path).joinpath(*_STORE_SUBDIR)

    @property
    def base_dir(self) -> Path:
        return self._base

    # ---- path helpers ---------------------------------------------------- #
    def _op_dir(self, operation_id: str) -> Path:
        return self._base / operation_id

    def _record_path(self, operation_id: str) -> Path:
        return self._op_dir(operation_id) / "operation.json"

    def _lock_path(self, operation_id: str) -> Path:
        return self._op_dir(operation_id) / "operation.lock"

    # ---- read paths ------------------------------------------------------ #
    def _load_unlocked(self, operation_id: str) -> OperationRecord | None:
        path = self._record_path(operation_id)
        if not path.exists():
            return None
        try:
            data = read_json(path)
        except JSONDecodeError as exc:
            raise CorruptRecordError(
                f"operation record {operation_id} is not valid JSON"
            ) from exc
        record = OperationRecord.from_dict(data)
        if record.operation_id != operation_id:
            raise IdentityMismatchError(
                f"record {record.operation_id!r} is stored under {operation_id!r}"
            )
        # Confirm the stored identity tuple still hashes to this operation id.
        record.verify_identity(record.repository_id, record.source_revision)
        return record

    def load(self, operation_id: str) -> OperationRecord:
        """Load and validate a persisted operation, failing closed if absent."""
        with file_lock(self._lock_path(operation_id)):
            record = self._load_unlocked(operation_id)
        if record is None:
            raise CorruptRecordError(f"no operation record for {operation_id}")
        return record

    # ---- write paths ----------------------------------------------------- #
    def _write_unlocked(self, record: OperationRecord) -> None:
        data = record.to_dict()
        # Re-validate the full document so we never persist a record that would
        # fail closed on a later load.
        OperationRecord.from_dict(data)
        atomic_write_json(self._record_path(record.operation_id), data)

    def _mutate(
        self,
        operation_id: str,
        transition: Callable[[OperationRecord], OperationRecord],
    ) -> OperationRecord:
        with file_lock(self._lock_path(operation_id)):
            record = self._load_unlocked(operation_id)
            if record is None:
                raise CorruptRecordError(f"no operation record for {operation_id}")
            updated = transition(record)
            if updated is record:
                return record  # idempotent no-op: nothing written
            self._write_unlocked(updated)
            return updated

    def create_or_load(self, repository_id: str, source_revision: str) -> OperationRecord:
        """Return the one operation for *repository_id* at *source_revision*.

        Creates a pending record if none exists; otherwise returns the existing
        validated record. Serialized per operation so concurrent creation yields
        one record and one shared id.
        """
        ensure_git_revision(source_revision)
        operation_id = derive_operation_id(repository_id, source_revision)
        self._op_dir(operation_id).mkdir(parents=True, exist_ok=True)
        with file_lock(self._lock_path(operation_id)):
            existing = self._load_unlocked(operation_id)
            if existing is not None:
                existing.verify_identity(repository_id, source_revision)
                return existing
            now = _utcnow_iso()
            record = OperationRecord(
                operation_id=operation_id,
                repository_id=repository_id,
                source_revision=source_revision,
                state=OperationState.PENDING,
                record_revision=1,
                attempt=0,
                created_at=now,
                updated_at=now,
                producer_results=(),
                semantic_index=initial_semantic_index(source_revision),
                manifest=ManifestPointer(status=ManifestPointerStatus.ABSENT),
            )
            self._write_unlocked(record)
            return record

    def begin_attempt(self, operation_id: str) -> OperationRecord:
        """Move an operation into ``running`` and increment its attempt.

        Idempotent while already running (no attempt increment, no write). A
        begin from ``succeeded`` is rejected as an invalid transition.
        """

        def transition(record: OperationRecord) -> OperationRecord:
            if record.state is OperationState.RUNNING:
                return record
            if not can_transition(record.state, OperationState.RUNNING):
                raise InvalidTransitionError(
                    f"cannot begin attempt from {record.state.value}"
                )
            return replace(
                record,
                state=OperationState.RUNNING,
                attempt=record.attempt + 1,
                record_revision=record.record_revision + 1,
                updated_at=_utcnow_iso(),
            )

        return self._mutate(operation_id, transition)

    def record_producer_result(
        self, operation_id: str, result: ProducerResult
    ) -> OperationRecord:
        """Append one producer result to a running operation."""

        def transition(record: OperationRecord) -> OperationRecord:
            if record.state is not OperationState.RUNNING:
                raise InvalidTransitionError(
                    "producer results require a running operation"
                )
            if result.producer_id in record.producer_ids():
                raise DuplicateProducerError(
                    f"duplicate producer_id {result.producer_id!r}"
                )
            return replace(
                record,
                producer_results=record.producer_results + (result,),
                record_revision=record.record_revision + 1,
                updated_at=_utcnow_iso(),
            )

        return self._mutate(operation_id, transition)

    def record_semantic_index(
        self, operation_id: str, reference: SemanticIndexReference
    ) -> OperationRecord:
        """Record the external semantic-index reference on a running operation."""

        def transition(record: OperationRecord) -> OperationRecord:
            if record.state is not OperationState.RUNNING:
                raise InvalidTransitionError(
                    "semantic index reference requires a running operation"
                )
            if reference == record.semantic_index:
                return record
            return replace(
                record,
                semantic_index=reference,
                record_revision=record.record_revision + 1,
                updated_at=_utcnow_iso(),
            )

        return self._mutate(operation_id, transition)

    def finalize(
        self,
        operation_id: str,
        outcome: OperationState,
        *,
        error: SafeError | None = None,
    ) -> OperationRecord:
        """Transition a running operation to a terminal outcome."""
        if outcome not in _FINALIZE_STATES:
            raise ContextRefreshError(f"{outcome.value} is not a terminal outcome")

        def transition(record: OperationRecord) -> OperationRecord:
            if not can_transition(record.state, outcome):
                raise InvalidTransitionError(
                    f"cannot finalize from {record.state.value} to {outcome.value}"
                )
            if outcome is OperationState.FAILED and error is None:
                raise RecordValidationError("failed finalize requires an error")
            return replace(
                record,
                state=outcome,
                error=error if outcome is OperationState.FAILED else None,
                record_revision=record.record_revision + 1,
                updated_at=_utcnow_iso(),
            )

        return self._mutate(operation_id, transition)

    def record_manifest(
        self,
        operation_id: str,
        *,
        path: str,
        sha256: str,
        status: ManifestPointerStatus = ManifestPointerStatus.VALIDATED,
    ) -> OperationRecord:
        """Record where the deterministic manifest was written for this operation.

        Permitted in a terminal state because it updates the manifest pointer,
        not the operation's lifecycle state.
        """

        def transition(record: OperationRecord) -> OperationRecord:
            pointer = ManifestPointer(status=status, path=path, sha256=sha256)
            if pointer == record.manifest:
                return record
            return replace(
                record,
                manifest=pointer,
                record_revision=record.record_revision + 1,
                updated_at=_utcnow_iso(),
            )

        return self._mutate(operation_id, transition)

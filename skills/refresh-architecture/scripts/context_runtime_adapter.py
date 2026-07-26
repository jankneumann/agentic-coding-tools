"""Architecture adapter over ``project-context-runtime`` (ri-04 D5/D6).

Architecture owns its deterministic provenance and freshness rules; this adapter
bridges those to ri-06's canonical durable operation store. It:

* creates/loads the one canonical ``(repository_id, source_revision)`` operation;
* records exactly one ``producer_id=architecture`` :class:`ProducerResult`;
* reads that producer result across processes; and
* projects canonical operation/producer state onto the legacy RPC status strings.

It never defines an architecture-specific operation ledger, lock, or result
schema, and never calls the runtime's whole-operation ``finalize`` — ri-07 owns
the multi-producer terminal outcome (design decision D5, spec scenario .13).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from arch_utils import provenance as _prov

# --- import the ri-06 runtime facade (stacked on add-durable-context-refresh-records) ---
_RUNTIME_SCRIPTS = Path(__file__).resolve().parents[2] / "project-context-runtime" / "scripts"
if _RUNTIME_SCRIPTS.is_dir() and str(_RUNTIME_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_SCRIPTS))

from models import (  # noqa: E402  (ri-06 canonical types — imported, never copied)
    ChangeKind,
    ContextRefreshError,
    Fallback,
    FallbackKind,
    OperationRecord,
    OperationState,
    ProducerResult,
    ProducerStatus,
    Remediation,
    RepositoryArtifact,
    SafeError,
    ValidationResult,
    ValidationStatus,
    derive_operation_id,
)
from store import OperationStore  # noqa: E402

PRODUCER_ID = _prov.PRODUCER_ID

# RPC status strings (mirror rpc_server.RefreshStatus values without importing it).
_RPC_RUNNING = "RUNNING"
_RPC_COMPLETED = "COMPLETED"
_RPC_FAILED = "FAILED"
_RPC_UNKNOWN = "UNKNOWN"

_REMEDIATION_REFRESH = Remediation(
    summary="Regenerate the architecture artifacts with a staged refresh.",
    # Canonical repo entry point (make architecture-refresh -> run_architecture.py
    # --staged). Avoids a hardcoded `skills/` path that breaks once the skill is
    # installed to a runtime dir (.claude/skills, .agents/skills).
    command="make architecture-refresh",
)


# --------------------------------------------------------------------------- #
# ProducerResult builders (architecture → canonical ri-06 result)
# --------------------------------------------------------------------------- #
def architecture_result_fresh(provenance_doc: dict[str, Any]) -> ProducerResult:
    """Build a ``fresh`` architecture producer result from a provenance document."""
    artifacts = tuple(
        RepositoryArtifact(
            path=art["path"], change=ChangeKind.MODIFIED, sha256=art["sha256"]
        )
        for art in provenance_doc.get("artifacts", [])
    )
    validation = provenance_doc.get("validation", {})
    summary = (
        "architecture provenance validated; artifacts current"
        if validation.get("warning_count", 0) == 0
        else "architecture provenance validated with warnings; artifacts current"
    )
    return ProducerResult(
        producer_id=PRODUCER_ID,
        producer_version=provenance_doc["producer"]["producer_version"],
        status=ProducerStatus.FRESH,
        artifacts=artifacts,
        validations=(
            ValidationResult(
                validation_id="architecture-provenance",
                status=ValidationStatus.PASSED,
                summary=summary,
            ),
        ),
    )


def architecture_result_failed(summary: str) -> ProducerResult:
    """Build a ``failed`` architecture producer result with safe error + remediation."""
    return ProducerResult(
        producer_id=PRODUCER_ID,
        producer_version=_prov.PRODUCER_VERSION,
        status=ProducerStatus.FAILED,
        remediation=(_REMEDIATION_REFRESH,),
        error=SafeError(error_class="ArchitectureRefreshError", summary=summary),
    )


def architecture_result_not_configured(reason: str) -> ProducerResult:
    """Build a ``not-configured`` result (e.g. analyzers unavailable) with fallback."""
    return ProducerResult(
        producer_id=PRODUCER_ID,
        producer_version=_prov.PRODUCER_VERSION,
        status=ProducerStatus.NOT_CONFIGURED,
        remediation=(_REMEDIATION_REFRESH,),
        fallback=Fallback(kind=FallbackKind.SKIP, reason=reason),
    )


# --------------------------------------------------------------------------- #
# Adapter
# --------------------------------------------------------------------------- #
@dataclass
class ArchitectureStatus:
    """Projection of canonical state onto the architecture RPC contract."""

    rpc_status: str
    operation_id: str | None
    source_revision: str | None
    producer_version: str | None = None
    producer_status: str | None = None
    remediation: tuple[dict[str, Any], ...] = ()
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.rpc_status,
            "operation_id": self.operation_id,
            "refresh_id": self.operation_id,
            "source_revision": self.source_revision,
            "producer_version": self.producer_version,
            "producer_status": self.producer_status,
            "remediation": list(self.remediation),
            "error_message": self.error_message,
        }


class ArchitectureAdapter:
    """Bridge architecture refresh to the canonical ri-06 operation store."""

    def __init__(self, repo_root: Path | str = ".", *, store: OperationStore | None = None):
        self.repo_root = Path(repo_root)
        self._store = store if store is not None else OperationStore(repo_root)

    # ---- identity -------------------------------------------------------- #
    def _resolve_identity(
        self, repository_id: str | None, source_revision: str | None
    ) -> tuple[str, str | None]:
        repo_id = repository_id or _prov.repository_id(self.repo_root)
        rev = source_revision or _prov.analyzed_revision(self.repo_root)
        return repo_id, rev

    # ---- write paths ----------------------------------------------------- #
    def ensure_operation(
        self, *, repository_id: str | None = None, source_revision: str | None = None
    ) -> OperationRecord:
        """Create or load the one canonical operation for the current revision."""
        repo_id, rev = self._resolve_identity(repository_id, source_revision)
        if rev is None:
            raise ContextRefreshError("cannot resolve HEAD revision for operation")
        return self._store.create_or_load(repo_id, rev)

    def record_architecture(
        self,
        result: ProducerResult,
        *,
        repository_id: str | None = None,
        source_revision: str | None = None,
    ) -> OperationRecord:
        """Record exactly one architecture producer result on the operation.

        Idempotent: if an architecture result already exists on the operation,
        the existing record is returned unchanged (a duplicate trigger reuses the
        canonical operation and starts no second pipeline — scenario .12). Never
        calls ``finalize`` (scenario .13).
        """
        if result.producer_id != PRODUCER_ID:
            raise ContextRefreshError(
                f"adapter only records {PRODUCER_ID!r} results, got {result.producer_id!r}"
            )
        repo_id, rev = self._resolve_identity(repository_id, source_revision)
        if rev is None:
            raise ContextRefreshError("cannot resolve HEAD revision for operation")
        op = self._store.create_or_load(repo_id, rev)
        if PRODUCER_ID in op.producer_ids():
            return op  # already recorded — idempotent reuse
        if op.state is OperationState.SUCCEEDED:
            return op  # terminal operation owned elsewhere; nothing to add
        if op.state in (
            OperationState.PENDING,
            OperationState.FAILED,
            OperationState.DEGRADED,
        ):
            op = self._store.begin_attempt(op.operation_id)
        # state is now RUNNING (either just begun, or another producer began it)
        return self._store.record_producer_result(op.operation_id, result)

    # ---- read paths ------------------------------------------------------ #
    def load_operation(
        self, *, repository_id: str | None = None, source_revision: str | None = None
    ) -> OperationRecord | None:
        """Load the canonical operation across processes, or ``None`` if absent/corrupt."""
        repo_id, rev = self._resolve_identity(repository_id, source_revision)
        if rev is None:
            return None
        op_id = derive_operation_id(repo_id, rev)
        try:
            return self._store.load(op_id)
        except ContextRefreshError:
            return None

    def read_architecture_result(
        self, *, repository_id: str | None = None, source_revision: str | None = None
    ) -> ProducerResult | None:
        """Return the persisted ``architecture`` producer result, or ``None``."""
        op = self.load_operation(
            repository_id=repository_id, source_revision=source_revision
        )
        if op is None:
            return None
        for r in op.producer_results:
            if r.producer_id == PRODUCER_ID:
                return r
        return None

    # ---- status projection (D6) ----------------------------------------- #
    def project_status(
        self, *, repository_id: str | None = None, source_revision: str | None = None
    ) -> ArchitectureStatus:
        """Map canonical operation/architecture-result state onto RPC status."""
        repo_id, rev = self._resolve_identity(repository_id, source_revision)
        op = self.load_operation(repository_id=repo_id, source_revision=rev)
        if op is None:
            return ArchitectureStatus(_RPC_UNKNOWN, operation_id=None, source_revision=rev)

        arch = next(
            (r for r in op.producer_results if r.producer_id == PRODUCER_ID), None
        )
        if arch is None:
            rpc = (
                _RPC_RUNNING
                if op.state in (OperationState.PENDING, OperationState.RUNNING)
                else _RPC_UNKNOWN
            )
            return ArchitectureStatus(
                rpc, operation_id=op.operation_id, source_revision=op.source_revision
            )

        remediation = tuple(r.to_dict() for r in arch.remediation)
        if arch.status is ProducerStatus.FRESH:
            rpc, error = _RPC_COMPLETED, None
        elif arch.status is ProducerStatus.FAILED:
            rpc = _RPC_FAILED
            error = arch.error.summary if arch.error else "architecture refresh failed"
        else:  # DEGRADED / NOT_CONFIGURED
            rpc = _RPC_FAILED
            error = f"architecture producer {arch.status.value}"
        return ArchitectureStatus(
            rpc,
            operation_id=op.operation_id,
            source_revision=op.source_revision,
            producer_version=arch.producer_version,
            producer_status=arch.status.value,
            remediation=remediation,
            error_message=error,
        )

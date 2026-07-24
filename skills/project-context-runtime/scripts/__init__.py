"""Supported facade for the project-context-runtime shared library.

Consumers use the durable operation store, the deterministic manifest writer,
and the strict record models exported here. The ``atomic`` module is
runtime-core infrastructure and is intentionally not re-exported.

Both import styles are supported to match this repo's shared-runtime
convention: callers may add ``scripts/`` to ``sys.path`` and import the bare
module names, or import this package and use the re-exported symbols.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

from manifest import (  # noqa: E402
    ManifestWriteResult,
    project_manifest,
    write_manifest,
)
from models import (  # noqa: E402
    SCHEMA_VERSION,
    ChangeKind,
    ContextRefreshError,
    CorruptRecordError,
    DegradedFallback,
    DuplicateProducerError,
    Fallback,
    FallbackKind,
    IdentityMismatchError,
    InvalidTransitionError,
    ManifestPointer,
    ManifestPointerStatus,
    OperationRecord,
    OperationState,
    ProducerResult,
    ProducerStatus,
    RecordValidationError,
    RefreshManifest,
    RefreshOutcome,
    Remediation,
    RepositoryArtifact,
    SafeError,
    SchemaVersionError,
    SemanticIndexReference,
    SemanticIndexStatus,
    UnsafePathError,
    ValidationResult,
    ValidationStatus,
    derive_operation_id,
    initial_semantic_index,
)
from store import OperationStore  # noqa: E402

__all__ = [
    # Store
    "OperationStore",
    # Manifest
    "write_manifest",
    "project_manifest",
    "ManifestWriteResult",
    # Identity / helpers
    "derive_operation_id",
    "initial_semantic_index",
    "SCHEMA_VERSION",
    # Documents
    "OperationRecord",
    "RefreshManifest",
    # Value objects
    "ProducerResult",
    "RepositoryArtifact",
    "ValidationResult",
    "Remediation",
    "Fallback",
    "SafeError",
    "SemanticIndexReference",
    "ManifestPointer",
    "DegradedFallback",
    # Enums
    "OperationState",
    "ProducerStatus",
    "SemanticIndexStatus",
    "ChangeKind",
    "ValidationStatus",
    "FallbackKind",
    "ManifestPointerStatus",
    "RefreshOutcome",
    # Exceptions
    "ContextRefreshError",
    "SchemaVersionError",
    "RecordValidationError",
    "UnsafePathError",
    "DuplicateProducerError",
    "InvalidTransitionError",
    "IdentityMismatchError",
    "CorruptRecordError",
]

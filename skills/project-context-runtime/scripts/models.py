"""Strict, versioned models for durable project-context refresh records.

This module owns the ``v1`` contract boundary in Python: enums, frozen
dataclasses, typed fail-closed exceptions, deterministic operation-identity
derivation, and offline JSON-Schema validation against the installed schema
assets.

Design invariants (see the change's ``design.md``):

* Freshness-bearing fields have no permissive defaults. A document that omits
  or malforms them is rejected, never coerced into a "looks fresh" record.
* Unknown ``schema_version`` values raise a typed :class:`SchemaVersionError`
  and are never downgraded or reinterpreted.
* Duplicate producer identities within one record or manifest are rejected.
* Persisted paths are repository-relative POSIX paths without traversal.
* Schema resolution is fully local; it never performs a network fetch.
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMA_VERSION = 1

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "install_assets" / "openspec" / "schemas"
_SCHEMA_FILES = {
    "types": "context-refresh-types.schema.json",
    "operation": "context-refresh-operation.schema.json",
    "manifest": "context-refresh-manifest.schema.json",
}

_OPERATION_ID_PREFIX = "pcr-"
_OPERATION_ID_HASH_LEN = 24
_IDENTITY_DOMAIN = "context-refresh-v1"

# Mirrors the RepositoryPath pattern in context-refresh-types.schema.json:
# reject absolute paths, ``..`` traversal segments, backslashes, and NUL.
_REPO_PATH_RE = re.compile(r"^(?!/)(?!.*(^|/)\.\.(/|$))(?!.*\\)(?!.*\x00).+$")
_GIT_REVISION_RE = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")


# --------------------------------------------------------------------------- #
# Typed, fail-closed exceptions
# --------------------------------------------------------------------------- #
class ContextRefreshError(Exception):
    """Base class for every project-context-runtime failure."""


class SchemaVersionError(ContextRefreshError):
    """A document declares an unsupported ``schema_version``."""


class RecordValidationError(ContextRefreshError):
    """A document failed JSON-Schema or structural validation."""


class UnsafePathError(ContextRefreshError):
    """A path is absolute, escapes the repository, or contains illegal bytes."""


class DuplicateProducerError(ContextRefreshError):
    """Two producer results share one producer identity."""


class InvalidTransitionError(ContextRefreshError):
    """An operation state transition is not permitted."""


class IdentityMismatchError(ContextRefreshError):
    """A loaded record's identity tuple does not match its location."""


class CorruptRecordError(ContextRefreshError):
    """A persisted record is truncated or otherwise unreadable."""


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class OperationState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    DEGRADED = "degraded"
    FAILED = "failed"


class ProducerStatus(str, Enum):
    FRESH = "fresh"
    DEGRADED = "degraded"
    FAILED = "failed"
    NOT_CONFIGURED = "not-configured"


class SemanticIndexStatus(str, Enum):
    NOT_CONFIGURED = "not-configured"
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STALE = "stale"


class ChangeKind(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"


class ValidationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class FallbackKind(str, Enum):
    EXACT_SEARCH = "exact-search"
    DIRECT_SOURCE = "direct-source"
    RETRY = "retry"
    SKIP = "skip"
    CUSTOM = "custom"


class ManifestPointerStatus(str, Enum):
    ABSENT = "absent"
    WRITTEN = "written"
    VALIDATED = "validated"


class RefreshOutcome(str, Enum):
    """Terminal refresh statuses projected into the deterministic manifest."""

    SUCCEEDED = "succeeded"
    DEGRADED = "degraded"
    FAILED = "failed"


# Legal operation state transitions. ``succeeded`` is terminal.
_TRANSITIONS: dict[OperationState, frozenset[OperationState]] = {
    OperationState.PENDING: frozenset({OperationState.RUNNING}),
    OperationState.RUNNING: frozenset(
        {OperationState.SUCCEEDED, OperationState.DEGRADED, OperationState.FAILED}
    ),
    OperationState.FAILED: frozenset({OperationState.RUNNING}),
    OperationState.DEGRADED: frozenset({OperationState.RUNNING}),
    OperationState.SUCCEEDED: frozenset(),
}


def can_transition(src: OperationState, dst: OperationState) -> bool:
    """Return whether ``src -> dst`` is a permitted operation transition."""
    return dst in _TRANSITIONS[src]


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def is_safe_repository_path(path: str) -> bool:
    """Return whether *path* is a safe repository-relative POSIX path."""
    return bool(_REPO_PATH_RE.match(path)) and len(path) <= 512


def ensure_repository_relative(path: str) -> str:
    """Return *path* unchanged if safe; otherwise raise :class:`UnsafePathError`.

    The rejected value is never normalized into a different path.
    """
    if not isinstance(path, str) or not is_safe_repository_path(path):
        raise UnsafePathError(f"unsafe repository path: {path!r}")
    return path


def ensure_git_revision(revision: str) -> str:
    """Return *revision* if it is a full 40- or 64-char lowercase Git object id."""
    if not isinstance(revision, str) or not _GIT_REVISION_RE.match(revision):
        raise RecordValidationError(f"invalid git revision: {revision!r}")
    return revision


def derive_operation_id(repository_id: str, source_revision: str) -> str:
    """Derive the deterministic operation id for one repository and revision.

    ``pcr-<first 24 hex chars of sha256("context-refresh-v1\\0" + repository_id
    + "\\0" + source_revision)>``. The domain prefix prevents cross-namespace
    hash reuse; the full identity tuple is still stored and verified on load.
    """
    if not repository_id:
        raise RecordValidationError("repository_id must be non-empty")
    ensure_git_revision(source_revision)
    payload = f"{_IDENTITY_DOMAIN}\x00{repository_id}\x00{source_revision}".encode()
    digest = hashlib.sha256(payload).hexdigest()
    return f"{_OPERATION_ID_PREFIX}{digest[:_OPERATION_ID_HASH_LEN]}"


def _enum(cls: type[Enum], value: Any) -> Any:
    """Parse *value* into enum *cls*, raising a typed error on an unknown member."""
    try:
        return cls(value)
    except ValueError as exc:
        raise RecordValidationError(f"invalid {cls.__name__}: {value!r}") from exc


# --------------------------------------------------------------------------- #
# Offline schema loading and validation
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=1)
def _load_schemas() -> tuple[Registry, dict[str, dict[str, Any]]]:
    """Build a local ``referencing`` registry from the installed schema assets.

    Resources are registered under their absolute ``$id`` so the schemas'
    sibling-relative ``$ref`` values resolve locally without any network fetch.
    """
    contents: dict[str, dict[str, Any]] = {}
    resources: list[tuple[str, Resource[dict[str, Any]]]] = []
    for name, filename in _SCHEMA_FILES.items():
        data = json.loads((_SCHEMA_DIR / filename).read_text(encoding="utf-8"))
        contents[name] = data
        resources.append(
            (data["$id"], Resource.from_contents(data, default_specification=DRAFT202012))
        )
    registry = Registry().with_resources(resources)
    return registry, contents


def validate_document(data: object, schema_name: str) -> None:
    """Validate *data* against the named installed schema.

    Raises :class:`RecordValidationError` with a stable, path-sorted message on
    any violation. Does not check ``schema_version`` specially; callers use
    :func:`ensure_supported_version` first to surface a typed compatibility
    error.
    """
    registry, contents = _load_schemas()
    validator = Draft202012Validator(contents[schema_name], registry=registry)
    errors = sorted(validator.iter_errors(data), key=lambda err: list(err.absolute_path))
    if errors:
        rendered = "; ".join(
            f"{'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
            for err in errors
        )
        raise RecordValidationError(f"{schema_name} schema validation failed: {rendered}")


def ensure_supported_version(data: object, *, kind: str) -> None:
    """Raise :class:`SchemaVersionError` when ``schema_version`` is not supported.

    Runs before full validation so an unknown version yields a compatibility
    error rather than a generic malformed-document error, and is never rewritten
    or downgraded.
    """
    if not isinstance(data, dict) or "schema_version" not in data:
        raise RecordValidationError(f"{kind} is missing schema_version")
    version = data["schema_version"]
    if version != SCHEMA_VERSION:
        raise SchemaVersionError(
            f"unsupported {kind} schema_version {version!r}; only {SCHEMA_VERSION} is supported"
        )


def _reject_duplicate_producers(results: list[dict[str, Any]], *, context: str) -> None:
    seen: set[str] = set()
    for result in results:
        producer_id = result.get("producer_id")
        if not isinstance(producer_id, str):
            continue
        if producer_id in seen:
            raise DuplicateProducerError(
                f"duplicate producer_id {producer_id!r} in {context}"
            )
        seen.add(producer_id)


# --------------------------------------------------------------------------- #
# Leaf value objects
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Remediation:
    summary: str
    command: str | None = None
    documentation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"summary": self.summary}
        if self.command is not None:
            out["command"] = self.command
        if self.documentation is not None:
            out["documentation"] = self.documentation
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Remediation:
        return cls(
            summary=data["summary"],
            command=data.get("command"),
            documentation=data.get("documentation"),
        )


@dataclass(frozen=True, slots=True)
class Fallback:
    kind: FallbackKind
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Fallback:
        return cls(kind=_enum(FallbackKind, data["kind"]), reason=data["reason"])


@dataclass(frozen=True, slots=True)
class ValidationResult:
    validation_id: str
    status: ValidationStatus
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "validation_id": self.validation_id,
            "status": self.status.value,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValidationResult:
        return cls(
            validation_id=data["validation_id"],
            status=_enum(ValidationStatus, data["status"]),
            summary=data["summary"],
        )


@dataclass(frozen=True, slots=True)
class RepositoryArtifact:
    path: str
    change: ChangeKind
    sha256: str | None

    def __post_init__(self) -> None:
        ensure_repository_relative(self.path)
        if self.change is ChangeKind.DELETED and self.sha256 is not None:
            raise RecordValidationError("deleted artifact must have null sha256")
        if self.change is not ChangeKind.DELETED and self.sha256 is None:
            raise RecordValidationError(f"{self.change.value} artifact requires sha256")

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "change": self.change.value, "sha256": self.sha256}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RepositoryArtifact:
        return cls(
            path=data["path"],
            change=_enum(ChangeKind, data["change"]),
            sha256=data.get("sha256"),
        )


@dataclass(frozen=True, slots=True)
class SafeError:
    error_class: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {"error_class": self.error_class, "summary": self.summary}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SafeError:
        return cls(error_class=data["error_class"], summary=data["summary"])


@dataclass(frozen=True, slots=True)
class ProducerResult:
    producer_id: str
    producer_version: str
    status: ProducerStatus
    artifacts: tuple[RepositoryArtifact, ...] = ()
    validations: tuple[ValidationResult, ...] = ()
    remediation: tuple[Remediation, ...] = ()
    fallback: Fallback | None = None
    error: SafeError | None = None

    def __post_init__(self) -> None:
        non_fresh = self.status is not ProducerStatus.FRESH
        if non_fresh and not self.remediation:
            raise RecordValidationError(
                f"non-fresh producer {self.producer_id!r} requires remediation"
            )
        if self.status in (ProducerStatus.DEGRADED, ProducerStatus.NOT_CONFIGURED) and (
            self.fallback is None
        ):
            raise RecordValidationError(
                f"{self.status.value} producer {self.producer_id!r} requires a fallback"
            )
        if self.status is ProducerStatus.FAILED and self.error is None:
            raise RecordValidationError(
                f"failed producer {self.producer_id!r} requires an error"
            )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "producer_id": self.producer_id,
            "producer_version": self.producer_version,
            "status": self.status.value,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "validations": [validation.to_dict() for validation in self.validations],
            "remediation": [item.to_dict() for item in self.remediation],
        }
        if self.fallback is not None:
            out["fallback"] = self.fallback.to_dict()
        if self.error is not None:
            out["error"] = self.error.to_dict()
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProducerResult:
        fallback = data.get("fallback")
        error = data.get("error")
        return cls(
            producer_id=data["producer_id"],
            producer_version=data["producer_version"],
            status=_enum(ProducerStatus, data["status"]),
            artifacts=tuple(
                RepositoryArtifact.from_dict(item) for item in data.get("artifacts", [])
            ),
            validations=tuple(
                ValidationResult.from_dict(item) for item in data.get("validations", [])
            ),
            remediation=tuple(
                Remediation.from_dict(item) for item in data.get("remediation", [])
            ),
            fallback=Fallback.from_dict(fallback) if fallback is not None else None,
            error=SafeError.from_dict(error) if error is not None else None,
        )


@dataclass(frozen=True, slots=True)
class SemanticIndexReference:
    status: SemanticIndexStatus
    requested_revision: str
    operation_id: str | None = None
    registry_record_id: str | None = None
    indexed_revision: str | None = None
    fallback: Fallback | None = None

    def __post_init__(self) -> None:
        ensure_git_revision(self.requested_revision)
        if self.status is SemanticIndexStatus.SUCCEEDED:
            if not self.operation_id or not self.registry_record_id:
                raise RecordValidationError(
                    "succeeded semantic index requires operation_id and registry_record_id"
                )
            if self.indexed_revision is None:
                raise RecordValidationError(
                    "succeeded semantic index requires indexed_revision"
                )
            ensure_git_revision(self.indexed_revision)
            if self.indexed_revision != self.requested_revision:
                raise RecordValidationError(
                    "semantic index indexed_revision must equal requested_revision"
                )
        else:
            if self.fallback is None:
                raise RecordValidationError(
                    f"{self.status.value} semantic index requires a fallback"
                )
            if self.indexed_revision is not None:
                ensure_git_revision(self.indexed_revision)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "status": self.status.value,
            "requested_revision": self.requested_revision,
            "operation_id": self.operation_id,
            "registry_record_id": self.registry_record_id,
            "indexed_revision": self.indexed_revision,
        }
        if self.fallback is not None:
            out["fallback"] = self.fallback.to_dict()
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SemanticIndexReference:
        fallback = data.get("fallback")
        return cls(
            status=_enum(SemanticIndexStatus, data["status"]),
            requested_revision=data["requested_revision"],
            operation_id=data.get("operation_id"),
            registry_record_id=data.get("registry_record_id"),
            indexed_revision=data.get("indexed_revision"),
            fallback=Fallback.from_dict(fallback) if fallback is not None else None,
        )


@dataclass(frozen=True, slots=True)
class ManifestPointer:
    status: ManifestPointerStatus
    path: str | None = None
    sha256: str | None = None

    def __post_init__(self) -> None:
        if self.status is ManifestPointerStatus.ABSENT:
            if self.path is not None or self.sha256 is not None:
                raise RecordValidationError("absent manifest pointer must be empty")
        else:
            if self.path is None or self.sha256 is None:
                raise RecordValidationError(
                    f"{self.status.value} manifest pointer requires path and sha256"
                )
            ensure_repository_relative(self.path)

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "path": self.path, "sha256": self.sha256}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ManifestPointer:
        return cls(
            status=_enum(ManifestPointerStatus, data["status"]),
            path=data.get("path"),
            sha256=data.get("sha256"),
        )


# --------------------------------------------------------------------------- #
# Top-level documents
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class OperationRecord:
    """The mutable clone-local operation ledger (``operation.json``)."""

    operation_id: str
    repository_id: str
    source_revision: str
    state: OperationState
    record_revision: int
    attempt: int
    created_at: str
    updated_at: str
    producer_results: tuple[ProducerResult, ...]
    semantic_index: SemanticIndexReference
    manifest: ManifestPointer
    error: SafeError | None = None
    schema_version: int = SCHEMA_VERSION

    def verify_identity(self, repository_id: str, source_revision: str) -> None:
        """Fail closed if this record does not match an expected identity tuple."""
        expected = derive_operation_id(repository_id, source_revision)
        if (
            self.operation_id != expected
            or self.repository_id != repository_id
            or self.source_revision != source_revision
        ):
            raise IdentityMismatchError(
                f"record identity {self.operation_id!r} does not match "
                f"{repository_id!r}@{source_revision!r}"
            )

    def producer_ids(self) -> tuple[str, ...]:
        return tuple(result.producer_id for result in self.producer_results)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "repository_id": self.repository_id,
            "source_revision": self.source_revision,
            "state": self.state.value,
            "record_revision": self.record_revision,
            "attempt": self.attempt,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "producer_results": [result.to_dict() for result in self.producer_results],
            "semantic_index": self.semantic_index.to_dict(),
            "manifest": self.manifest.to_dict(),
        }
        if self.error is not None:
            out["error"] = self.error.to_dict()
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OperationRecord:
        ensure_supported_version(data, kind="operation")
        validate_document(data, "operation")
        _reject_duplicate_producers(data["producer_results"], context="operation record")
        error = data.get("error")
        return cls(
            operation_id=data["operation_id"],
            repository_id=data["repository_id"],
            source_revision=data["source_revision"],
            state=_enum(OperationState, data["state"]),
            record_revision=data["record_revision"],
            attempt=data["attempt"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            producer_results=tuple(
                ProducerResult.from_dict(item) for item in data["producer_results"]
            ),
            semantic_index=SemanticIndexReference.from_dict(data["semantic_index"]),
            manifest=ManifestPointer.from_dict(data["manifest"]),
            error=SafeError.from_dict(error) if error is not None else None,
            schema_version=data["schema_version"],
        )


@dataclass(frozen=True, slots=True)
class DegradedFallback:
    producer_id: str
    fallback: Fallback

    def to_dict(self) -> dict[str, Any]:
        return {"producer_id": self.producer_id, "fallback": self.fallback.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DegradedFallback:
        return cls(
            producer_id=data["producer_id"],
            fallback=Fallback.from_dict(data["fallback"]),
        )


@dataclass(frozen=True, slots=True)
class RefreshManifest:
    """The deterministic, committable projection of a terminal operation."""

    operation_id: str
    repository_id: str
    source_revision: str
    operation_created_at: str
    refresh_status: RefreshOutcome
    producer_results: tuple[ProducerResult, ...]
    repository_artifacts: tuple[RepositoryArtifact, ...]
    validations: tuple[ValidationResult, ...]
    semantic_index: SemanticIndexReference
    degraded_fallbacks: tuple[DegradedFallback, ...] = ()
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "repository_id": self.repository_id,
            "source_revision": self.source_revision,
            "operation_created_at": self.operation_created_at,
            "refresh_status": self.refresh_status.value,
            "producer_results": [result.to_dict() for result in self.producer_results],
            "repository_artifacts": [
                artifact.to_dict() for artifact in self.repository_artifacts
            ],
            "validations": [validation.to_dict() for validation in self.validations],
            "semantic_index": self.semantic_index.to_dict(),
            "degraded_fallbacks": [item.to_dict() for item in self.degraded_fallbacks],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RefreshManifest:
        ensure_supported_version(data, kind="manifest")
        validate_document(data, "manifest")
        _reject_duplicate_producers(data["producer_results"], context="manifest")
        return cls(
            operation_id=data["operation_id"],
            repository_id=data["repository_id"],
            source_revision=data["source_revision"],
            operation_created_at=data["operation_created_at"],
            refresh_status=_enum(RefreshOutcome, data["refresh_status"]),
            producer_results=tuple(
                ProducerResult.from_dict(item) for item in data["producer_results"]
            ),
            repository_artifacts=tuple(
                RepositoryArtifact.from_dict(item) for item in data["repository_artifacts"]
            ),
            validations=tuple(
                ValidationResult.from_dict(item) for item in data["validations"]
            ),
            semantic_index=SemanticIndexReference.from_dict(data["semantic_index"]),
            degraded_fallbacks=tuple(
                DegradedFallback.from_dict(item) for item in data["degraded_fallbacks"]
            ),
            schema_version=data["schema_version"],
        )


def initial_semantic_index(source_revision: str) -> SemanticIndexReference:
    """Return the truthful semantic-index state for a freshly created operation.

    Until an index succeeds for the exact revision, callers must use the
    exact-search fallback, so a new operation is ``pending`` with that fallback.
    """
    return SemanticIndexReference(
        status=SemanticIndexStatus.PENDING,
        requested_revision=source_revision,
        fallback=Fallback(
            kind=FallbackKind.EXACT_SEARCH,
            reason="Semantic index has not completed for the requested revision.",
        ),
    )


# Re-exported symbol used by callers that only need field ordering metadata.
__all__ = [
    "SCHEMA_VERSION",
    "OperationState",
    "ProducerStatus",
    "SemanticIndexStatus",
    "ChangeKind",
    "ValidationStatus",
    "FallbackKind",
    "ManifestPointerStatus",
    "RefreshOutcome",
    "Remediation",
    "Fallback",
    "ValidationResult",
    "RepositoryArtifact",
    "SafeError",
    "ProducerResult",
    "SemanticIndexReference",
    "ManifestPointer",
    "DegradedFallback",
    "OperationRecord",
    "RefreshManifest",
    "ContextRefreshError",
    "SchemaVersionError",
    "RecordValidationError",
    "UnsafePathError",
    "DuplicateProducerError",
    "InvalidTransitionError",
    "IdentityMismatchError",
    "CorruptRecordError",
    "derive_operation_id",
    "can_transition",
    "ensure_repository_relative",
    "ensure_git_revision",
    "is_safe_repository_path",
    "validate_document",
    "ensure_supported_version",
    "initial_semantic_index",
]

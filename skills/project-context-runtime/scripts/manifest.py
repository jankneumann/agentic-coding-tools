"""Deterministic manifest projection and atomic committable writer.

Projects a terminal :class:`OperationRecord` into a
:class:`~models.RefreshManifest` containing only stable fields, with every
ordered collection sorted by a documented key so the same logical projection
serializes to identical bytes. External semantic-index state is represented as
a reference, never as a repository artifact.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path

from atomic import atomic_write_json
from models import (
    ContextRefreshError,
    DegradedFallback,
    OperationRecord,
    OperationState,
    ProducerResult,
    RefreshManifest,
    RefreshOutcome,
    RepositoryArtifact,
    ValidationResult,
    ensure_repository_relative,
)

_TERMINAL_TO_OUTCOME = {
    OperationState.SUCCEEDED: RefreshOutcome.SUCCEEDED,
    OperationState.DEGRADED: RefreshOutcome.DEGRADED,
    OperationState.FAILED: RefreshOutcome.FAILED,
}


@dataclass(frozen=True, slots=True)
class ManifestWriteResult:
    """Outcome of writing a manifest: its repo-relative path, digest, and
    whether the on-disk bytes actually changed."""

    path: str
    sha256: str
    changed: bool


def _sorted_artifacts(items: Iterable[RepositoryArtifact]) -> tuple[RepositoryArtifact, ...]:
    unique = {(a.path, a.change.value, a.sha256): a for a in items}
    return tuple(sorted(unique.values(), key=lambda a: (a.path, a.change.value)))


def _sorted_validations(items: Iterable[ValidationResult]) -> tuple[ValidationResult, ...]:
    unique = {(v.validation_id, v.status.value, v.summary): v for v in items}
    return tuple(
        sorted(unique.values(), key=lambda v: (v.validation_id, v.status.value, v.summary))
    )


def _sorted_producer(producer: ProducerResult) -> ProducerResult:
    return replace(
        producer,
        artifacts=_sorted_artifacts(producer.artifacts),
        validations=_sorted_validations(producer.validations),
        remediation=tuple(
            sorted(
                producer.remediation,
                key=lambda r: (r.summary, r.command or "", r.documentation or ""),
            )
        ),
    )


def project_manifest(record: OperationRecord) -> RefreshManifest:
    """Project a terminal operation into a deterministic manifest.

    Raises :class:`ContextRefreshError` for a non-terminal operation, because a
    refresh that has not finished has no truthful committable outcome.
    """
    if record.state not in _TERMINAL_TO_OUTCOME:
        raise ContextRefreshError(
            f"cannot project a non-terminal operation ({record.state.value})"
        )
    ordered = sorted(record.producer_results, key=lambda p: p.producer_id)
    producers = tuple(_sorted_producer(p) for p in ordered)
    artifacts = _sorted_artifacts(a for p in producers for a in p.artifacts)
    validations = _sorted_validations(v for p in producers for v in p.validations)
    fallbacks = tuple(
        DegradedFallback(producer_id=p.producer_id, fallback=p.fallback)
        for p in ordered
        if p.fallback is not None
    )
    return RefreshManifest(
        operation_id=record.operation_id,
        repository_id=record.repository_id,
        source_revision=record.source_revision,
        operation_created_at=record.created_at,
        refresh_status=_TERMINAL_TO_OUTCOME[record.state],
        producer_results=producers,
        repository_artifacts=artifacts,
        validations=validations,
        semantic_index=record.semantic_index,
        degraded_fallbacks=fallbacks,
    )


def write_manifest(
    record: OperationRecord,
    target_path: str,
    *,
    repo_root: Path | str,
) -> ManifestWriteResult:
    """Project, validate, and atomically write the deterministic manifest.

    *target_path* is a repository-relative POSIX path; it is validated before
    any write and joined onto *repo_root* for the actual location. The returned
    ``changed`` flag is ``False`` for a byte-identical rerun.
    """
    relative = ensure_repository_relative(target_path)
    manifest = project_manifest(record)
    data = manifest.to_dict()
    # Full structural re-validation (schema, version, duplicate producers)
    # before touching the target: fail closed rather than write a bad manifest.
    RefreshManifest.from_dict(data)
    absolute = Path(repo_root) / relative
    changed, digest = atomic_write_json(absolute, data)
    return ManifestWriteResult(path=relative, sha256=digest, changed=changed)

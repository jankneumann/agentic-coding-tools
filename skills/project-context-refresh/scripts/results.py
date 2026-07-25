"""Canonical result builders mapping producer observations to ri-06 shapes.

Design decision D2 fixes one table from producer observation to the ri-06
:class:`ProducerResult` shape. Encoding it once here keeps every adapter
consistent and prevents a drift result from ever being emitted as ``fresh``:

| observation                     | builder             | status          |
|---------------------------------|---------------------|-----------------|
| clean check / generate no-op    | :func:`fresh`       | fresh           |
| managed output(s) would change  | :func:`drift`       | degraded        |
| render/parse failure            | :func:`failed`      | failed          |
| optional owner not configured   | :func:`not_configured` | not-configured |

``check`` mode never writes; :func:`drift` therefore always attaches a
``custom`` fallback stating that no checkout write was performed.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from _runtime import (
    Fallback,
    FallbackKind,
    ProducerResult,
    ProducerStatus,
    Remediation,
    RepositoryArtifact,
    SafeError,
    ValidationResult,
    ValidationStatus,
)

# Stable fallback reason for side-effect-free check-mode drift. Keeping it a
# constant makes drift results byte-identical across runs.
CHECK_MODE_NO_WRITE = (
    "Check mode compared rendered output in memory and performed no checkout write."
)


_VID_DISALLOWED = re.compile(r"[^A-Za-z0-9._:-]+")
_VID_LEADING = re.compile(r"^[^A-Za-z0-9]+")


def vid(*parts: str) -> str:
    """Build a schema-valid ``validation_id`` from arbitrary parts.

    The ri-06 schema constrains ids to ``^[A-Za-z0-9][A-Za-z0-9._:-]*$`` and 128
    chars. Path separators and other stray characters become ``-`` so an id
    derived from a file path (``schema:openspec/contracts/a.json``) stays valid
    and stable. The transform is deterministic, so ids remain byte-stable.
    """
    joined = ":".join(p for p in parts if p)
    cleaned = _VID_DISALLOWED.sub("-", joined)
    cleaned = _VID_LEADING.sub("", cleaned) or "check"
    return cleaned[:128]


def passed(validation_id: str, summary: str) -> ValidationResult:
    return ValidationResult(validation_id, ValidationStatus.PASSED, summary)


def failed_validation(validation_id: str, summary: str) -> ValidationResult:
    return ValidationResult(validation_id, ValidationStatus.FAILED, summary)


def skipped(validation_id: str, summary: str) -> ValidationResult:
    return ValidationResult(validation_id, ValidationStatus.SKIPPED, summary)


def fresh(
    producer_id: str,
    producer_version: str,
    *,
    validations: Sequence[ValidationResult],
    artifacts: Sequence[RepositoryArtifact] = (),
) -> ProducerResult:
    """A clean check or a generate that changed nothing: ``status=fresh``."""
    return ProducerResult(
        producer_id=producer_id,
        producer_version=producer_version,
        status=ProducerStatus.FRESH,
        artifacts=tuple(artifacts),
        validations=tuple(validations),
    )


def generated(
    producer_id: str,
    producer_version: str,
    *,
    artifacts: Sequence[RepositoryArtifact],
    validations: Sequence[ValidationResult],
) -> ProducerResult:
    """A generate run that wrote managed artifacts: ``status=fresh`` with paths."""
    return ProducerResult(
        producer_id=producer_id,
        producer_version=producer_version,
        status=ProducerStatus.FRESH,
        artifacts=tuple(artifacts),
        validations=tuple(validations),
    )


def drift(
    producer_id: str,
    producer_version: str,
    *,
    artifacts: Sequence[RepositoryArtifact],
    validations: Sequence[ValidationResult],
    remediation: Sequence[Remediation],
    reason: str = CHECK_MODE_NO_WRITE,
) -> ProducerResult:
    """Managed output differs from a fresh render: ``degraded`` + custom fallback."""
    return ProducerResult(
        producer_id=producer_id,
        producer_version=producer_version,
        status=ProducerStatus.DEGRADED,
        artifacts=tuple(artifacts),
        validations=tuple(validations),
        remediation=tuple(remediation),
        fallback=Fallback(kind=FallbackKind.CUSTOM, reason=reason),
    )


def failed(
    producer_id: str,
    producer_version: str,
    *,
    error: SafeError,
    remediation: Sequence[Remediation],
    validations: Sequence[ValidationResult] = (),
) -> ProducerResult:
    """A producer could not render or compare: ``failed`` with a bounded error."""
    return ProducerResult(
        producer_id=producer_id,
        producer_version=producer_version,
        status=ProducerStatus.FAILED,
        validations=tuple(validations),
        remediation=tuple(remediation),
        error=error,
    )


def not_configured(
    producer_id: str,
    producer_version: str,
    *,
    fallback: Fallback,
    remediation: Sequence[Remediation],
    validations: Sequence[ValidationResult] = (),
) -> ProducerResult:
    """An optional owner is unavailable: ``not-configured`` with a fallback."""
    return ProducerResult(
        producer_id=producer_id,
        producer_version=producer_version,
        status=ProducerStatus.NOT_CONFIGURED,
        validations=tuple(validations),
        remediation=tuple(remediation),
        fallback=fallback,
    )


def sort_artifacts(artifacts: Iterable[RepositoryArtifact]) -> tuple[RepositoryArtifact, ...]:
    """Return artifacts in stable, path-sorted order for deterministic output."""
    return tuple(sorted(artifacts, key=lambda a: (a.path, a.change.value)))

"""Degradable semantic-index adapter (ri-07 D4).

The semantic index (ri-01/ri-02) is a coordinator service backed by Postgres and
CocoIndex — not an in-process function a skill can call. So the refresh
orchestrator treats it as the one *degradable* producer: when the service is
reachable it records a ``SUCCEEDED`` :class:`SemanticIndexReference` pinned to the
exact revision; when it is unconfigured or errors, it records a non-succeeded
reference carrying the canonical ``exact-search`` fallback and **never raises**.

This module owns only the mapping from an indexing attempt to the ri-06
``SemanticIndexReference``. It defines no result model and performs no durable
persistence (the orchestrator records the reference through the ri-06 store).

Design:

* :class:`SemanticIndexOutcome` — the minimal success descriptor an indexer
  returns (the coordinator operation id, its registry record id, and the exact
  revision that was indexed).
* :class:`SemanticIndexUnavailable` — an indexer raises this when the service is
  configured but unreachable (no DB, no coordinator); it maps to ``failed`` with a
  fallback rather than propagating.
* :data:`SemanticIndexer` — the injectable seam: ``(repository, requested_revision)
  -> SemanticIndexOutcome``.
* :func:`resolve_semantic_index` — run the indexer (if any) and return a validated
  reference. With no indexer configured the result is ``not-configured``; any
  indexer failure becomes ``failed``. Both carry an ``exact-search`` fallback.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Importing _runtime first inserts the ri-06 runtime scripts dir onto sys.path.
from _runtime import Fallback, FallbackKind, ensure_git_revision
from models import SemanticIndexReference, SemanticIndexStatus

_MAX_REASON = 300
_EXACT_SEARCH_REASON_UNCONFIGURED = (
    "Semantic index is not configured in this context; use exact search until an "
    "index completes for the requested revision."
)


class SemanticIndexUnavailable(Exception):
    """Raised by an indexer when the service is configured but unreachable.

    Distinct from an arbitrary error: it signals a clean degradation (no DB, no
    coordinator) rather than an indexing bug, but both map to a non-succeeded
    reference with an exact-search fallback.
    """


@dataclass(frozen=True, slots=True)
class SemanticIndexOutcome:
    """Minimal success descriptor returned by a semantic indexer.

    ``indexed_revision`` MUST equal the requested revision — the ri-06
    ``SemanticIndexReference`` rejects a succeeded index whose indexed revision
    differs, so a mismatch is a caller bug surfaced here as ``failed``.
    """

    operation_id: str
    registry_record_id: str
    indexed_revision: str


# The injectable seam. A real indexer reaches the coordinator; tests supply a fake.
SemanticIndexer = Callable[[Path, str], SemanticIndexOutcome]


def _bounded_reason(exc: BaseException) -> str:
    """Reduce an exception to a bounded, machine-safe fallback reason."""
    summary = str(exc).strip() or exc.__class__.__name__
    text = f"Semantic index unavailable ({exc.__class__.__name__}): {summary}"
    if len(text) > _MAX_REASON:
        text = text[: _MAX_REASON - 3] + "..."
    return text


def _degraded(
    status: SemanticIndexStatus, requested_revision: str, reason: str
) -> SemanticIndexReference:
    """Build a non-succeeded reference with the canonical exact-search fallback."""
    return SemanticIndexReference(
        status=status,
        requested_revision=requested_revision,
        fallback=Fallback(kind=FallbackKind.EXACT_SEARCH, reason=reason),
    )


def resolve_semantic_index(
    repository: Path,
    requested_revision: str,
    *,
    indexer: SemanticIndexer | None = None,
) -> SemanticIndexReference:
    """Attempt the semantic index and return a validated reference.

    For a valid ``requested_revision`` (the orchestrator pre-validates it) this
    never raises — every indexer outcome maps to a reference:

    * No indexer configured → ``not-configured`` + exact-search fallback.
    * Indexer raises :class:`SemanticIndexUnavailable` or any other exception →
      ``failed`` + exact-search fallback with a bounded reason.
    * Indexer returns an outcome → ``succeeded`` pinned to the exact revision.

    An invalid revision is a caller (programming) error and raises before dispatch.
    """
    ensure_git_revision(requested_revision)
    if indexer is None:
        return _degraded(
            SemanticIndexStatus.NOT_CONFIGURED,
            requested_revision,
            _EXACT_SEARCH_REASON_UNCONFIGURED,
        )
    try:
        outcome = indexer(Path(repository), requested_revision)
    except Exception as exc:  # noqa: BLE001 - degradation must never propagate
        return _degraded(
            SemanticIndexStatus.FAILED, requested_revision, _bounded_reason(exc)
        )

    try:
        return SemanticIndexReference(
            status=SemanticIndexStatus.SUCCEEDED,
            requested_revision=requested_revision,
            operation_id=outcome.operation_id,
            registry_record_id=outcome.registry_record_id,
            indexed_revision=outcome.indexed_revision,
        )
    except Exception as exc:  # noqa: BLE001 - a bad success descriptor degrades
        return _degraded(
            SemanticIndexStatus.FAILED,
            requested_revision,
            _bounded_reason(exc),
        )


__all__ = [
    "SemanticIndexOutcome",
    "SemanticIndexUnavailable",
    "SemanticIndexer",
    "resolve_semantic_index",
]

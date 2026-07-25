"""Semantic-index adapter tests (ri-07 tasks 1.1-1.2).

The adapter must map every indexing attempt to a validated ri-06
``SemanticIndexReference`` without a database and without ever raising on a
degraded path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from _runtime import FallbackKind
from models import SemanticIndexStatus
from semantic_adapter import (
    SemanticIndexOutcome,
    SemanticIndexUnavailable,
    resolve_semantic_index,
)

FULL_SHA = "a" * 40
OTHER_SHA = "b" * 40


def test_no_indexer_is_not_configured_with_exact_search_fallback():
    ref = resolve_semantic_index(Path("/repo"), FULL_SHA, indexer=None)
    assert ref.status is SemanticIndexStatus.NOT_CONFIGURED
    assert ref.requested_revision == FULL_SHA
    assert ref.fallback is not None
    assert ref.fallback.kind is FallbackKind.EXACT_SEARCH
    assert ref.operation_id is None


def test_successful_index_is_pinned_to_the_exact_revision():
    def indexer(repo: Path, rev: str) -> SemanticIndexOutcome:
        return SemanticIndexOutcome(
            operation_id="op-123", registry_record_id="rec-9", indexed_revision=rev
        )

    ref = resolve_semantic_index(Path("/repo"), FULL_SHA, indexer=indexer)
    assert ref.status is SemanticIndexStatus.SUCCEEDED
    assert ref.operation_id == "op-123"
    assert ref.registry_record_id == "rec-9"
    assert ref.indexed_revision == FULL_SHA
    assert ref.fallback is None


def test_unavailable_service_degrades_to_failed_without_raising():
    def indexer(repo: Path, rev: str) -> SemanticIndexOutcome:
        raise SemanticIndexUnavailable("no database connection")

    ref = resolve_semantic_index(Path("/repo"), FULL_SHA, indexer=indexer)
    assert ref.status is SemanticIndexStatus.FAILED
    assert ref.fallback is not None
    assert ref.fallback.kind is FallbackKind.EXACT_SEARCH
    assert "no database connection" in ref.fallback.reason


def test_arbitrary_indexer_error_degrades_and_is_bounded():
    def indexer(repo: Path, rev: str) -> SemanticIndexOutcome:
        raise RuntimeError("x" * 5000)

    ref = resolve_semantic_index(Path("/repo"), FULL_SHA, indexer=indexer)
    assert ref.status is SemanticIndexStatus.FAILED
    assert ref.fallback is not None
    assert len(ref.fallback.reason) <= 300


def test_mismatched_indexed_revision_degrades_not_raises():
    def indexer(repo: Path, rev: str) -> SemanticIndexOutcome:
        return SemanticIndexOutcome(
            operation_id="op-1", registry_record_id="rec-1", indexed_revision=OTHER_SHA
        )

    ref = resolve_semantic_index(Path("/repo"), FULL_SHA, indexer=indexer)
    assert ref.status is SemanticIndexStatus.FAILED
    assert ref.fallback is not None


def test_invalid_requested_revision_is_a_caller_error():
    with pytest.raises(Exception):
        resolve_semantic_index(Path("/repo"), "not-a-sha", indexer=None)

"""Strict model behaviour tests.

Spec scenarios: project-context-refresh-records.1, .3, .16, .17, .18
Design decisions: D2, D5, D6, D7
"""

from __future__ import annotations

import models as m
import pytest

REV_A = "a" * 40
REV_B = "b" * 40
REPO = "github.com/acme/repo"


def _pending_record(repo: str = REPO, rev: str = REV_A) -> m.OperationRecord:
    return m.OperationRecord(
        operation_id=m.derive_operation_id(repo, rev),
        repository_id=repo,
        source_revision=rev,
        state=m.OperationState.PENDING,
        record_revision=1,
        attempt=0,
        created_at="2026-07-24T00:00:00+00:00",
        updated_at="2026-07-24T00:00:00+00:00",
        producer_results=(),
        semantic_index=m.initial_semantic_index(rev),
        manifest=m.ManifestPointer(status=m.ManifestPointerStatus.ABSENT),
    )


# --- identity --------------------------------------------------------------- #
def test_operation_id_is_deterministic_and_prefixed() -> None:
    first = m.derive_operation_id(REPO, REV_A)
    again = m.derive_operation_id(REPO, REV_A)
    assert first == again
    assert first.startswith("pcr-")
    assert len(first) == len("pcr-") + 24


def test_operation_id_distinct_on_identity_change() -> None:
    assert m.derive_operation_id(REPO, REV_A) != m.derive_operation_id(REPO, REV_B)
    assert m.derive_operation_id(REPO, REV_A) != m.derive_operation_id("other/repo", REV_A)


def test_derive_rejects_invalid_revision() -> None:
    with pytest.raises(m.RecordValidationError):
        m.derive_operation_id(REPO, "not-a-sha")


def test_verify_identity_detects_mismatch() -> None:
    record = _pending_record()
    record.verify_identity(REPO, REV_A)  # ok
    with pytest.raises(m.IdentityMismatchError):
        record.verify_identity(REPO, REV_B)


# --- round trips ------------------------------------------------------------ #
def test_operation_record_round_trip() -> None:
    record = _pending_record()
    restored = m.OperationRecord.from_dict(record.to_dict())
    assert restored == record


def test_producer_result_round_trip_degraded() -> None:
    producer = m.ProducerResult(
        producer_id="architecture",
        producer_version="1.0.0",
        status=m.ProducerStatus.DEGRADED,
        artifacts=(m.RepositoryArtifact("docs/a.md", m.ChangeKind.MODIFIED, "0" * 64),),
        validations=(m.ValidationResult("arch.build", m.ValidationStatus.PASSED, "ok"),),
        remediation=(m.Remediation("re-run with embeddings configured"),),
        fallback=m.Fallback(m.FallbackKind.EXACT_SEARCH, "embedder offline"),
    )
    restored = m.ProducerResult.from_dict(producer.to_dict())
    assert restored == producer


# --- fail closed on construction ------------------------------------------- #
def test_non_fresh_producer_requires_remediation() -> None:
    with pytest.raises(m.RecordValidationError):
        m.ProducerResult(
            producer_id="p",
            producer_version="1",
            status=m.ProducerStatus.DEGRADED,
            fallback=m.Fallback(m.FallbackKind.SKIP, "x"),
        )


def test_degraded_producer_requires_fallback() -> None:
    with pytest.raises(m.RecordValidationError):
        m.ProducerResult(
            producer_id="p",
            producer_version="1",
            status=m.ProducerStatus.DEGRADED,
            remediation=(m.Remediation("fix"),),
        )


def test_failed_producer_requires_error() -> None:
    with pytest.raises(m.RecordValidationError):
        m.ProducerResult(
            producer_id="p",
            producer_version="1",
            status=m.ProducerStatus.FAILED,
            remediation=(m.Remediation("fix"),),
        )


def test_deleted_artifact_forbids_digest() -> None:
    with pytest.raises(m.RecordValidationError):
        m.RepositoryArtifact("docs/gone.md", m.ChangeKind.DELETED, "0" * 64)


def test_non_deleted_artifact_requires_digest() -> None:
    with pytest.raises(m.RecordValidationError):
        m.RepositoryArtifact("docs/a.md", m.ChangeKind.ADDED, None)


def test_unsafe_artifact_path_rejected() -> None:
    for bad in ("/abs/path", "../escape", "a\\b", "has\x00nul"):
        with pytest.raises(m.UnsafePathError):
            m.RepositoryArtifact(bad, m.ChangeKind.MODIFIED, "0" * 64)


def test_succeeded_semantic_index_requires_matching_revision() -> None:
    with pytest.raises(m.RecordValidationError):
        m.SemanticIndexReference(
            status=m.SemanticIndexStatus.SUCCEEDED,
            requested_revision=REV_A,
            operation_id="op",
            registry_record_id="reg",
            indexed_revision=REV_B,  # mismatch
        )


def test_non_succeeded_semantic_index_requires_fallback() -> None:
    with pytest.raises(m.RecordValidationError):
        m.SemanticIndexReference(
            status=m.SemanticIndexStatus.STALE,
            requested_revision=REV_A,
        )


# --- unknown version fails closed ------------------------------------------ #
def test_unknown_schema_version_raises_typed_error() -> None:
    data = _pending_record().to_dict()
    data["schema_version"] = 2
    with pytest.raises(m.SchemaVersionError):
        m.OperationRecord.from_dict(data)


def test_duplicate_producer_ids_rejected_at_model_boundary() -> None:
    record = _pending_record()
    data = record.to_dict()
    running = m.ProducerResult("dup", "1", m.ProducerStatus.FRESH)
    data["state"] = "running"
    data["producer_results"] = [running.to_dict(), running.to_dict()]
    with pytest.raises(m.DuplicateProducerError):
        m.OperationRecord.from_dict(data)


def test_can_transition_matrix() -> None:
    S = m.OperationState
    assert m.can_transition(S.PENDING, S.RUNNING)
    assert m.can_transition(S.RUNNING, S.SUCCEEDED)
    assert m.can_transition(S.FAILED, S.RUNNING)
    assert m.can_transition(S.DEGRADED, S.RUNNING)
    assert not m.can_transition(S.SUCCEEDED, S.RUNNING)
    assert not m.can_transition(S.PENDING, S.SUCCEEDED)

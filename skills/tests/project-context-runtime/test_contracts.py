"""Schema contract tests against the installed Draft 2020-12 assets.

Spec scenarios: project-context-refresh-records.1, .3, .8, .9, .10, .14, .16, .17, .18
Contracts: context-refresh-types / -operation / -manifest schemas
Design decisions: D1, D4, D5, D6
"""

from __future__ import annotations

import models as m
import pytest

REV = "c" * 40
REPO = "github.com/acme/repo"
OP_ID = m.derive_operation_id(REPO, REV)


def _semantic_pending() -> dict:
    return {
        "status": "pending",
        "requested_revision": REV,
        "operation_id": None,
        "registry_record_id": None,
        "indexed_revision": None,
        "fallback": {"kind": "exact-search", "reason": "index not complete"},
    }


def _pending_operation() -> dict:
    return {
        "schema_version": 1,
        "operation_id": OP_ID,
        "repository_id": REPO,
        "source_revision": REV,
        "state": "pending",
        "record_revision": 1,
        "attempt": 0,
        "created_at": "2026-07-24T00:00:00+00:00",
        "updated_at": "2026-07-24T00:00:00+00:00",
        "producer_results": [],
        "semantic_index": _semantic_pending(),
        "manifest": {"status": "absent", "path": None, "sha256": None},
    }


def _degraded_producer() -> dict:
    return {
        "producer_id": "architecture",
        "producer_version": "1.2.0",
        "status": "degraded",
        "artifacts": [
            {"path": "docs/architecture.md", "change": "modified", "sha256": "a" * 64}
        ],
        "validations": [
            {"validation_id": "arch.build", "status": "passed", "summary": "ok"}
        ],
        "remediation": [{"summary": "configure the embedder and re-run"}],
        "fallback": {"kind": "exact-search", "reason": "embedder offline"},
    }


def _successful_manifest() -> dict:
    return {
        "schema_version": 1,
        "operation_id": OP_ID,
        "repository_id": REPO,
        "source_revision": REV,
        "operation_created_at": "2026-07-24T00:00:00+00:00",
        "refresh_status": "succeeded",
        "producer_results": [
            {
                "producer_id": "documentation",
                "producer_version": "2.0.0",
                "status": "fresh",
                "artifacts": [
                    {"path": "docs/index.md", "change": "added", "sha256": "b" * 64}
                ],
                "validations": [
                    {"validation_id": "docs.lint", "status": "passed", "summary": "ok"}
                ],
                "remediation": [],
            }
        ],
        "repository_artifacts": [
            {"path": "docs/index.md", "change": "added", "sha256": "b" * 64}
        ],
        "validations": [
            {"validation_id": "docs.lint", "status": "passed", "summary": "ok"}
        ],
        "semantic_index": {
            "status": "succeeded",
            "requested_revision": REV,
            "operation_id": "sem-op-1",
            "registry_record_id": "reg-1",
            "indexed_revision": REV,
        },
        "degraded_fallbacks": [],
    }


# --- valid canonical examples ---------------------------------------------- #
def test_pending_operation_validates() -> None:
    m.validate_document(_pending_operation(), "operation")


def test_degraded_completed_operation_validates() -> None:
    doc = _pending_operation()
    doc["state"] = "degraded"
    doc["attempt"] = 1
    doc["record_revision"] = 4
    doc["producer_results"] = [_degraded_producer()]
    m.validate_document(doc, "operation")


def test_successful_manifest_validates() -> None:
    m.validate_document(_successful_manifest(), "manifest")


def test_manifest_with_pending_semantic_index_and_fallback_validates() -> None:
    doc = _successful_manifest()
    doc["refresh_status"] = "degraded"
    doc["semantic_index"] = _semantic_pending()
    m.validate_document(doc, "manifest")


# --- schema-level rejections ----------------------------------------------- #
def test_unknown_version_rejected_by_schema() -> None:
    doc = _pending_operation()
    doc["schema_version"] = 2
    with pytest.raises(m.RecordValidationError):
        m.validate_document(doc, "operation")


def test_unsafe_path_rejected_by_schema() -> None:
    for bad in ("/abs.md", "../esc.md", "back\\slash.md"):
        doc = _successful_manifest()
        doc["repository_artifacts"][0]["path"] = bad
        with pytest.raises(m.RecordValidationError):
            m.validate_document(doc, "manifest")


def test_non_fresh_producer_without_remediation_rejected_by_schema() -> None:
    doc = _pending_operation()
    doc["state"] = "degraded"
    bad_producer = _degraded_producer()
    bad_producer["remediation"] = []
    doc["producer_results"] = [bad_producer]
    with pytest.raises(m.RecordValidationError):
        m.validate_document(doc, "operation")


def test_deleted_artifact_with_digest_rejected_by_schema() -> None:
    doc = _successful_manifest()
    doc["repository_artifacts"] = [
        {"path": "docs/gone.md", "change": "deleted", "sha256": "b" * 64}
    ]
    with pytest.raises(m.RecordValidationError):
        m.validate_document(doc, "manifest")


# --- model-level rejections (cross-field, not schema-expressible) ----------- #
def test_duplicate_producer_ids_rejected_by_model() -> None:
    doc = _successful_manifest()
    doc["producer_results"] = [doc["producer_results"][0], doc["producer_results"][0]]
    with pytest.raises(m.DuplicateProducerError):
        m.RefreshManifest.from_dict(doc)


def test_mismatched_semantic_revision_rejected_by_model() -> None:
    doc = _successful_manifest()
    doc["semantic_index"]["indexed_revision"] = "d" * 40  # != requested
    with pytest.raises(m.RecordValidationError):
        m.RefreshManifest.from_dict(doc)

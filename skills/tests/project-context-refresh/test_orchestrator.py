"""Refresh orchestration tests (ri-07 tasks 2.1-4.3).

Fake producers are registered into the conftest-isolated registry so the
orchestrator is exercised without running the real deterministic producers, a
database, or the architecture analyzer toolchain.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import orchestrator
from _runtime import (
    Fallback,
    FallbackKind,
    ProducerResult,
    ProducerStatus,
    Remediation,
    SafeError,
    ValidationResult,
    ValidationStatus,
)
from models import OperationState, SemanticIndexStatus
from registry import Producer, ProducerSpec, register
from semantic_adapter import SemanticIndexOutcome
from store import OperationStore

FULL_SHA = "a" * 40


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
def _result(pid: str, status: ProducerStatus, version: str = "1") -> ProducerResult:
    """Build a fake result that satisfies the ri-06 per-status invariants.

    fresh → passed validation only; degraded → failed validation + remediation +
    fallback; failed → remediation + error.
    """
    is_fresh = status is ProducerStatus.FRESH
    return ProducerResult(
        producer_id=pid,
        producer_version=version,
        status=status,
        validations=(
            ValidationResult(
                validation_id=f"{pid}-check",
                status=ValidationStatus.PASSED if is_fresh else ValidationStatus.FAILED,
                summary="fake",
            ),
        ),
        remediation=() if is_fresh else (Remediation(summary=f"re-run {pid}"),),
        fallback=(
            Fallback(kind=FallbackKind.CUSTOM, reason="fake drift")
            if status is ProducerStatus.DEGRADED
            else None
        ),
        error=(
            SafeError(error_class="FakeError", summary="fake failure")
            if status is ProducerStatus.FAILED
            else None
        ),
    )


class _FakeProducer(Producer):
    def __init__(self, pid: str, status: ProducerStatus, owner: str = "fake-owner"):
        self.spec = ProducerSpec(
            producer_id=pid,
            producer_version="1",
            owner=owner,
            inputs=("x",),
            outputs=(),
        )
        self._status = status

    def run(self, mode, repository, source_revision):  # noqa: ANN001
        return _result(self.spec.producer_id, self._status)


def _register_fakes(*producers: _FakeProducer) -> None:
    for p in producers:
        register(p)


def _fresh_architecture(repo, rev, mode):  # noqa: ANN001
    return _result("architecture", ProducerStatus.FRESH, version="arch-1")


def _ok_indexer(repo: Path, rev: str) -> SemanticIndexOutcome:
    return SemanticIndexOutcome(
        operation_id="sem-op", registry_record_id="sem-rec", indexed_revision=rev
    )


def _store(tmp_path: Path) -> OperationStore:
    return OperationStore(tmp_path, base_dir=tmp_path / "_store")


# --------------------------------------------------------------------------- #
# decide_outcome (D5)
# --------------------------------------------------------------------------- #
def _semantic(status: SemanticIndexStatus):
    from _runtime import Fallback, FallbackKind
    from models import SemanticIndexReference

    if status is SemanticIndexStatus.SUCCEEDED:
        return SemanticIndexReference(
            status=status,
            requested_revision=FULL_SHA,
            operation_id="o",
            registry_record_id="r",
            indexed_revision=FULL_SHA,
        )
    return SemanticIndexReference(
        status=status,
        requested_revision=FULL_SHA,
        fallback=Fallback(kind=FallbackKind.EXACT_SEARCH, reason="down"),
    )


def test_outcome_all_fresh_and_semantic_succeeded_is_succeeded():
    results = [_result("a", ProducerStatus.FRESH), _result("b", ProducerStatus.FRESH)]
    outcome, error = orchestrator.decide_outcome(
        results, _semantic(SemanticIndexStatus.SUCCEEDED)
    )
    assert outcome is OperationState.SUCCEEDED
    assert error is None


def test_outcome_degraded_producer_is_degraded():
    results = [_result("a", ProducerStatus.FRESH), _result("b", ProducerStatus.DEGRADED)]
    outcome, error = orchestrator.decide_outcome(
        results, _semantic(SemanticIndexStatus.SUCCEEDED)
    )
    assert outcome is OperationState.DEGRADED
    assert error is None


def test_outcome_semantic_not_succeeded_is_degraded():
    results = [_result("a", ProducerStatus.FRESH)]
    outcome, _ = orchestrator.decide_outcome(
        results, _semantic(SemanticIndexStatus.FAILED)
    )
    assert outcome is OperationState.DEGRADED


def test_outcome_failed_producer_is_failed_with_error():
    results = [_result("a", ProducerStatus.FRESH), _result("z", ProducerStatus.FAILED)]
    outcome, error = orchestrator.decide_outcome(
        results, _semantic(SemanticIndexStatus.SUCCEEDED)
    )
    assert outcome is OperationState.FAILED
    assert error is not None
    assert "z" in error.summary


# --------------------------------------------------------------------------- #
# generate
# --------------------------------------------------------------------------- #
def test_generate_records_all_producers_and_writes_manifest(tmp_path):
    _register_fakes(
        _FakeProducer("documentation.inventory", ProducerStatus.FRESH),
        _FakeProducer("api.contracts", ProducerStatus.FRESH),
    )
    res = orchestrator.generate(
        tmp_path,
        revision=FULL_SHA,
        store=_store(tmp_path),
        architecture=_fresh_architecture,
        semantic_indexer=_ok_indexer,
    )
    assert res.outcome is OperationState.SUCCEEDED
    assert res.exit_code() == 0
    ids = {r.producer_id for r in res.producer_results}
    assert ids == {"documentation.inventory", "api.contracts", "architecture"}
    # Manifest written to the gitignored path under the repo root, not the tree.
    manifest = tmp_path / orchestrator.DEFAULT_MANIFEST_PATH
    assert manifest.is_file()
    assert res.manifest_path == orchestrator.DEFAULT_MANIFEST_PATH
    doc = json.loads(manifest.read_text())
    assert doc["refresh_status"] == "succeeded"
    assert doc["semantic_index"]["status"] == "succeeded"
    manifest_ids = {p["producer_id"] for p in doc["producer_results"]}
    assert manifest_ids == ids


def test_generate_is_idempotent_no_diff_on_rerun(tmp_path):
    _register_fakes(_FakeProducer("documentation.inventory", ProducerStatus.FRESH))
    store = _store(tmp_path)
    first = orchestrator.generate(
        tmp_path,
        revision=FULL_SHA,
        store=store,
        architecture=_fresh_architecture,
        semantic_indexer=_ok_indexer,
    )
    manifest = tmp_path / orchestrator.DEFAULT_MANIFEST_PATH
    bytes_first = manifest.read_bytes()
    second = orchestrator.generate(
        tmp_path,
        revision=FULL_SHA,
        store=store,
        architecture=_fresh_architecture,
        semantic_indexer=_ok_indexer,
    )
    assert second.operation_id == first.operation_id
    assert second.manifest_sha256 == first.manifest_sha256
    assert manifest.read_bytes() == bytes_first


def test_semantic_failure_preserves_deterministic_output(tmp_path):
    _register_fakes(
        _FakeProducer("documentation.inventory", ProducerStatus.FRESH),
        _FakeProducer("api.contracts", ProducerStatus.FRESH),
    )

    def failing_indexer(repo, rev):  # noqa: ANN001
        raise RuntimeError("postgres unreachable")

    res = orchestrator.generate(
        tmp_path,
        revision=FULL_SHA,
        store=_store(tmp_path),
        architecture=_fresh_architecture,
        semantic_indexer=failing_indexer,
    )
    # Degraded, not failed — deterministic results survive.
    assert res.outcome is OperationState.DEGRADED
    assert res.exit_code() == 2
    ids = {r.producer_id for r in res.producer_results}
    assert {"documentation.inventory", "api.contracts", "architecture"} <= ids
    assert res.semantic_index.status is SemanticIndexStatus.FAILED
    doc = json.loads((tmp_path / orchestrator.DEFAULT_MANIFEST_PATH).read_text())
    assert doc["refresh_status"] == "degraded"
    assert len(doc["producer_results"]) == 3


def test_generate_failed_producer_finalizes_failed(tmp_path):
    _register_fakes(
        _FakeProducer("documentation.inventory", ProducerStatus.FRESH),
        _FakeProducer("api.contracts", ProducerStatus.FAILED),
    )
    res = orchestrator.generate(
        tmp_path,
        revision=FULL_SHA,
        store=_store(tmp_path),
        architecture=_fresh_architecture,
        semantic_indexer=_ok_indexer,
    )
    assert res.outcome is OperationState.FAILED
    assert res.exit_code() == 1


# --------------------------------------------------------------------------- #
# ownership + check mode
# --------------------------------------------------------------------------- #
def test_single_producer_run_records_one_owner_identified_result(tmp_path):
    _register_fakes(
        _FakeProducer("documentation.inventory", ProducerStatus.FRESH, owner="doc-owner"),
        _FakeProducer("api.contracts", ProducerStatus.FRESH),
    )
    res = orchestrator.generate(
        tmp_path,
        revision=FULL_SHA,
        producer_ids=["documentation.inventory"],
        store=_store(tmp_path),
        semantic_indexer=_ok_indexer,
    )
    assert len(res.producer_results) == 1
    assert res.producer_results[0].producer_id == "documentation.inventory"


def test_check_is_read_only(tmp_path):
    _register_fakes(_FakeProducer("documentation.inventory", ProducerStatus.FRESH))
    res = orchestrator.check(
        tmp_path,
        revision=FULL_SHA,
        architecture=_fresh_architecture,
        semantic_indexer=_ok_indexer,
    )
    assert res.operation_id is None
    assert res.outcome is OperationState.SUCCEEDED
    # No store dir and no manifest were written.
    assert not (tmp_path / "_store").exists()
    assert not (tmp_path / orchestrator.DEFAULT_MANIFEST_PATH).exists()


def test_check_reports_drift_exit_code(tmp_path):
    _register_fakes(_FakeProducer("documentation.inventory", ProducerStatus.DEGRADED))
    res = orchestrator.check(
        tmp_path,
        revision=FULL_SHA,
        architecture=_fresh_architecture,
        semantic_indexer=_ok_indexer,
    )
    assert res.outcome is OperationState.DEGRADED
    assert res.exit_code() == 2


def test_unknown_producer_id_is_rejected(tmp_path):
    _register_fakes(_FakeProducer("documentation.inventory", ProducerStatus.FRESH))
    with pytest.raises(ValueError):
        orchestrator.check(tmp_path, revision=FULL_SHA, producer_ids=["nope"])

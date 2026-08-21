"""Refresh orchestration tests (ri-07 tasks 2.1-4.3).

Fake producers are registered into the conftest-isolated registry so the
orchestrator is exercised without running the real deterministic producers, a
database, or the architecture analyzer toolchain.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
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
from models import ChangeKind, OperationState, RepositoryArtifact, SemanticIndexStatus
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
def test_single_producer_run_reports_one_result_without_touching_operation(tmp_path):
    _register_fakes(
        _FakeProducer("documentation.inventory", ProducerStatus.FRESH, owner="doc-owner"),
        _FakeProducer("api.contracts", ProducerStatus.FRESH),
    )
    store = _store(tmp_path)
    res = orchestrator.generate(
        tmp_path,
        revision=FULL_SHA,
        producer_ids=["documentation.inventory"],
        store=store,
        semantic_indexer=_ok_indexer,
    )
    assert len(res.producer_results) == 1
    assert res.producer_results[0].producer_id == "documentation.inventory"
    # A scoped run is regenerate-and-report only: no durable operation, no manifest.
    assert res.operation_id is None
    assert res.manifest_path is None
    assert not (tmp_path / "_store").exists()


def test_scoped_run_does_not_poison_a_later_full_refresh(tmp_path):
    # Regression: a scoped run must not finalize the shared per-revision operation
    # to the immutable SUCCEEDED sink, or a later full refresh would reuse an
    # incomplete operation and skip the other producers.
    _register_fakes(
        _FakeProducer("documentation.inventory", ProducerStatus.FRESH),
        _FakeProducer("api.contracts", ProducerStatus.FRESH),
    )
    store = _store(tmp_path)
    orchestrator.generate(
        tmp_path,
        revision=FULL_SHA,
        producer_ids=["documentation.inventory"],
        store=store,
        semantic_indexer=_ok_indexer,
    )
    full = orchestrator.generate(
        tmp_path,
        revision=FULL_SHA,
        store=store,
        architecture=_fresh_architecture,
        semantic_indexer=_ok_indexer,
    )
    ids = {r.producer_id for r in full.producer_results}
    assert ids == {"documentation.inventory", "api.contracts", "architecture"}
    assert full.outcome is OperationState.SUCCEEDED


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


# --------------------------------------------------------------------------- #
# resume / retry / durability
# --------------------------------------------------------------------------- #
def test_resume_lifts_degraded_semantic_to_succeeded(tmp_path):
    # First run degrades because the index is down; a later run with the index
    # available resumes the same operation and upgrades it to succeeded, without
    # re-running the sealed (append-only) deterministic producers.
    _register_fakes(
        _FakeProducer("documentation.inventory", ProducerStatus.FRESH),
        _FakeProducer("api.contracts", ProducerStatus.FRESH),
    )
    store = _store(tmp_path)

    def down(repo, rev):  # noqa: ANN001
        raise RuntimeError("index down")

    first = orchestrator.generate(
        tmp_path, revision=FULL_SHA, store=store,
        architecture=_fresh_architecture, semantic_indexer=down,
    )
    assert first.outcome is OperationState.DEGRADED

    second = orchestrator.generate(
        tmp_path, revision=FULL_SHA, store=store,
        architecture=_fresh_architecture, semantic_indexer=_ok_indexer,
    )
    assert second.operation_id == first.operation_id
    assert second.outcome is OperationState.SUCCEEDED
    assert second.semantic_index.status is SemanticIndexStatus.SUCCEEDED
    # Manifest re-projected to reflect the upgraded outcome.
    doc = json.loads((tmp_path / orchestrator.DEFAULT_MANIFEST_PATH).read_text())
    assert doc["refresh_status"] == "succeeded"


def test_succeeded_reuse_repairs_absent_manifest(tmp_path):
    # A crash between finalize(succeeded) and record_manifest leaves an ABSENT
    # pointer; reuse must repair it rather than return None forever.
    _register_fakes(_FakeProducer("documentation.inventory", ProducerStatus.FRESH))
    store = _store(tmp_path)
    repo_id = Path(tmp_path).resolve().name
    op = store.create_or_load(repo_id, FULL_SHA)
    op = store.begin_attempt(op.operation_id)
    op = store.record_producer_result(
        op.operation_id, _result("documentation.inventory", ProducerStatus.FRESH)
    )
    op = store.record_semantic_index(op.operation_id, _semantic(SemanticIndexStatus.SUCCEEDED))
    op = store.finalize(op.operation_id, OperationState.SUCCEEDED)
    assert op.manifest.path is None  # never recorded — simulates the crash window

    res = orchestrator.generate(
        tmp_path,
        revision=FULL_SHA,
        producer_ids=None,
        store=store,
        architecture=_fresh_architecture,
        semantic_indexer=_ok_indexer,
    )
    assert res.outcome is OperationState.SUCCEEDED
    assert res.manifest_path is not None
    assert (tmp_path / orchestrator.DEFAULT_MANIFEST_PATH).is_file()


def test_record_tolerant_converges_on_concurrent_duplicate():
    # A concurrent attempt recording the same producer first raises
    # DuplicateProducerError; the orchestrator reloads and converges, not crashes.
    from models import DuplicateProducerError

    sentinel = object()

    class _DupStore:
        def __init__(self):
            self.loaded = False

        def record_producer_result(self, op_id, result):  # noqa: ANN001
            raise DuplicateProducerError("dup")

        def load(self, op_id):  # noqa: ANN001
            self.loaded = True
            return sentinel

    class _Op:
        operation_id = "op-1"

    store = _DupStore()
    out = orchestrator._record_tolerant(
        store, _Op(), _result("documentation.inventory", ProducerStatus.FRESH)
    )
    assert out is sentinel
    assert store.loaded


# --------------------------------------------------------------------------- #
# Review regressions (ri-07 merge triage)
# --------------------------------------------------------------------------- #
def _git_repo(path: Path) -> str:
    """Init a real git repo with one commit; return its full HEAD SHA.

    Identity is passed with ``-c`` rather than ``git config`` so the commit
    succeeds on a CI runner with no global git identity.
    """
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "seed.txt"], check=True)
    subprocess.run(
        [
            "git", "-C", str(path),
            "-c", "user.name=Test",
            "-c", "user.email=test@example.com",
            "commit", "-q", "-m", "seed",
        ],
        check=True,
    )
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def test_revision_must_match_the_checked_out_tree(tmp_path):
    # Regression: producers read the live filesystem, so accepting an arbitrary
    # --revision would persist artifacts under a revision they did not come from.
    repo = tmp_path / "repo"
    head = _git_repo(repo)

    with pytest.raises(orchestrator.RevisionMismatchError):
        orchestrator.resolve_repository_identity(repo, FULL_SHA)

    # The checked-out revision is accepted, and so is "no revision" (defaults to HEAD).
    _root, _rid, rev = orchestrator.resolve_repository_identity(repo, head)
    assert rev == head
    _root, _rid, rev = orchestrator.resolve_repository_identity(repo, None)
    assert rev == head


def test_revision_mismatch_is_rejected_by_generate_and_check(tmp_path):
    # The guard must sit on both entry points, not just the helper.
    repo = tmp_path / "repo"
    _git_repo(repo)
    _register_fakes(_FakeProducer("documentation.inventory", ProducerStatus.FRESH))

    with pytest.raises(orchestrator.RevisionMismatchError):
        orchestrator.check(repo, revision=FULL_SHA)
    with pytest.raises(orchestrator.RevisionMismatchError):
        orchestrator.generate(repo, revision=FULL_SHA, architecture=_fresh_architecture)


def test_empty_repository_does_not_report_head_as_the_revision(tmp_path):
    # `git rev-parse HEAD` in a commit-less repo echoes the literal "HEAD" on
    # stdout and exits 128. Trusting stdout alone would treat "HEAD" as the
    # checked-out revision and reject every explicit --revision as a mismatch.
    repo = tmp_path / "empty"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)

    _root, _rid, rev = orchestrator.resolve_repository_identity(repo, FULL_SHA)
    assert rev == FULL_SHA


def test_repository_id_honors_shared_identity_override(tmp_path, monkeypatch):
    # Regression: ri-04's provenance.repository_id honors PROJECT_CONTEXT_REPO_ID.
    # Disagreeing here would split one clone across two operation ids, hiding the
    # architecture producer's results from this refresh.
    repo = tmp_path / "repo"
    _git_repo(repo)

    _root, default_id, _rev = orchestrator.resolve_repository_identity(repo, None)
    assert default_id == "repo"

    monkeypatch.setenv("PROJECT_CONTEXT_REPO_ID", "shared-identity")
    _root, overridden, _rev = orchestrator.resolve_repository_identity(repo, None)
    assert overridden == "shared-identity"


def test_reuse_recreates_manifest_deleted_from_the_worktree(tmp_path):
    # Regression: .git-context/ is gitignored and per-worktree, so a VALIDATED
    # pointer is not evidence the file is readable here. Reuse must re-verify the
    # digest on disk and rewrite, not report a path that does not exist.
    _register_fakes(_FakeProducer("documentation.inventory", ProducerStatus.FRESH))
    store = _store(tmp_path)
    first = orchestrator.generate(
        tmp_path, revision=FULL_SHA, store=store,
        architecture=_fresh_architecture, semantic_indexer=_ok_indexer,
    )
    assert first.outcome is OperationState.SUCCEEDED
    manifest = tmp_path / orchestrator.DEFAULT_MANIFEST_PATH
    assert manifest.is_file()

    manifest.unlink()  # simulates a cleaned .git-context/ or a sibling worktree

    second = orchestrator.generate(
        tmp_path, revision=FULL_SHA, store=store,
        architecture=_fresh_architecture, semantic_indexer=_ok_indexer,
    )
    assert second.operation_id == first.operation_id
    assert second.manifest_path is not None
    assert manifest.is_file(), "reuse reported a manifest path that does not exist"
    assert second.manifest_sha256 == first.manifest_sha256


def test_reuse_rewrites_a_corrupted_manifest(tmp_path):
    # A truncated/edited manifest no longer matches the recorded digest; reuse
    # must restore the canonical bytes rather than trust the stale pointer.
    _register_fakes(_FakeProducer("documentation.inventory", ProducerStatus.FRESH))
    store = _store(tmp_path)
    first = orchestrator.generate(
        tmp_path, revision=FULL_SHA, store=store,
        architecture=_fresh_architecture, semantic_indexer=_ok_indexer,
    )
    manifest = tmp_path / orchestrator.DEFAULT_MANIFEST_PATH
    manifest.write_text("{}\n", encoding="utf-8")

    second = orchestrator.generate(
        tmp_path, revision=FULL_SHA, store=store,
        architecture=_fresh_architecture, semantic_indexer=_ok_indexer,
    )
    assert second.manifest_sha256 == first.manifest_sha256
    assert json.loads(manifest.read_text())["refresh_status"] == "succeeded"


class _WritingProducer(Producer):
    """A fake that materializes an artifact and records its digest."""

    def __init__(self, pid: str, relative_path: str, content: str):
        self.spec = ProducerSpec(
            producer_id=pid,
            producer_version="1",
            owner="fake-owner",
            inputs=("x",),
            outputs=(relative_path,),
        )
        self.relative_path = relative_path
        self.content = content
        self.runs = 0

    def run(self, mode, repository, source_revision):  # noqa: ANN001
        self.runs += 1
        target = Path(repository) / self.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.content, encoding="utf-8")
        base = _result(self.spec.producer_id, ProducerStatus.FRESH)
        return replace(
            base,
            artifacts=(
                RepositoryArtifact(
                    path=self.relative_path,
                    change=ChangeKind.MODIFIED,
                    sha256=hashlib.sha256(self.content.encode()).hexdigest(),
                ),
            ),
        )


def test_succeeded_reuse_verifies_artifacts_against_the_worktree(tmp_path):
    # Issue #385: the operation ledger lives in the shared git common dir and is
    # keyed on (repository_id, revision), so a succeeded record alone is not
    # evidence that THIS worktree contains the recorded artifacts — a sibling
    # worktree at the same HEAD, or local tampering, satisfies the key. Reuse
    # must re-verify the recorded digests and regenerate in place on mismatch.
    producer = _WritingProducer(
        "documentation.inventory", "docs/generated.md", "canonical\n"
    )
    _register_fakes(producer)
    store = _store(tmp_path)
    first = orchestrator.generate(
        tmp_path, revision=FULL_SHA, store=store,
        architecture=_fresh_architecture, semantic_indexer=_ok_indexer,
    )
    assert first.outcome is OperationState.SUCCEEDED
    artifact = tmp_path / "docs" / "generated.md"
    assert artifact.read_text(encoding="utf-8") == "canonical\n"
    runs_after_first = producer.runs

    artifact.write_text("tampered\n", encoding="utf-8")

    second = orchestrator.generate(
        tmp_path, revision=FULL_SHA, store=store,
        architecture=_fresh_architecture, semantic_indexer=_ok_indexer,
    )
    assert second.operation_id == first.operation_id
    assert producer.runs > runs_after_first, (
        "reuse returned the record verbatim without re-running producers"
    )
    assert artifact.read_text(encoding="utf-8") == "canonical\n", (
        "reuse did not restore the tampered artifact in this worktree"
    )


def test_succeeded_reuse_with_current_artifacts_does_not_rerun(tmp_path):
    # The verification must not tax the honest path: matching digests keep the
    # verbatim-reuse behavior (no producer re-run, no repository diff).
    producer = _WritingProducer(
        "documentation.inventory", "docs/generated.md", "canonical\n"
    )
    _register_fakes(producer)
    store = _store(tmp_path)
    orchestrator.generate(
        tmp_path, revision=FULL_SHA, store=store,
        architecture=_fresh_architecture, semantic_indexer=_ok_indexer,
    )
    runs_after_first = producer.runs

    orchestrator.generate(
        tmp_path, revision=FULL_SHA, store=store,
        architecture=_fresh_architecture, semantic_indexer=_ok_indexer,
    )
    assert producer.runs == runs_after_first


def test_architecture_fallback_is_constructible_and_degrades(tmp_path):
    # Regression: ri-06 rejects any non-fresh ProducerResult without remediation,
    # so the un-remediated fallback raised RecordValidationError — aborting the
    # refresh in exactly the case it exists to survive.
    fallback = orchestrator._architecture_not_configured_fallback("owner missing")
    assert fallback.status is ProducerStatus.NOT_CONFIGURED
    assert fallback.remediation, "non-fresh result requires remediation"
    assert fallback.fallback is not None

    _register_fakes(_FakeProducer("documentation.inventory", ProducerStatus.FRESH))

    def _exploding_architecture(repo, rev, mode):  # noqa: ANN001
        raise RuntimeError("analyzer toolchain missing")

    res = orchestrator.generate(
        tmp_path, revision=FULL_SHA, store=_store(tmp_path),
        architecture=_exploding_architecture, semantic_indexer=_ok_indexer,
    )
    # Degrades, never raises, and the architecture entry stays in the manifest.
    assert res.outcome is OperationState.DEGRADED
    arch = [r for r in res.producer_results if r.producer_id == "architecture"]
    assert arch and arch[0].status is ProducerStatus.NOT_CONFIGURED


def test_record_tolerant_converges_on_terminal_operation():
    # Regression: OperationStore checks "not RUNNING" BEFORE the duplicate check,
    # so a concurrent finalize raises InvalidTransitionError — which the
    # duplicate-only handler let escape, crashing the slower refresh.
    from models import InvalidTransitionError

    sentinel = object()

    class _TerminalStore:
        def __init__(self):
            self.loaded = False

        def record_producer_result(self, op_id, result):  # noqa: ANN001
            raise InvalidTransitionError("producer results require a running operation")

        def load(self, op_id):  # noqa: ANN001
            self.loaded = True
            return sentinel

    class _Op:
        operation_id = "op-1"

    store = _TerminalStore()
    out = orchestrator._record_tolerant(
        store, _Op(), _result("documentation.inventory", ProducerStatus.FRESH)
    )
    assert out is sentinel
    assert store.loaded

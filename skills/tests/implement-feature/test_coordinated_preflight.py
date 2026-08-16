"""Regression coverage for the declared feature-HEAD completion barrier."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills/parallel-infrastructure/scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from dag_scheduler import DAGScheduler, FeatureHeadGateError, load_execution_gate
from integration_orchestrator import (
    FeatureHeadBarrierError,
    FeatureHeadCompletionBarrier,
)


CHANGE = ROOT / "openspec/changes/phase-scoped-worktree-lifecycle"
WORK_PACKAGES = CHANGE / "work-packages.yaml"
POINTER = (
    "openspec/changes/phase-scoped-worktree-lifecycle/contracts/prerequisites.yaml#execution_gate"
)
BARRIER_COMMIT = "a" * 40
EVIDENCE_COMMIT = "b" * 40


def test_exact_machine_declaration_controls_the_preflight_package() -> None:
    package_data = yaml.safe_load(WORK_PACKAGES.read_text())
    package = next(
        item for item in package_data["packages"] if item["package_id"] == "wp-baseline-preflight"
    )

    assert package["inputs"]["execution_gate_pointer"] == POINTER
    declaration = load_execution_gate(POINTER, ROOT)

    assert declaration["package_id"] == package["package_id"]
    assert declaration["completion_visibility"] == "feature-head"
    assert declaration["evidence_path"].endswith("baseline-gates.json")
    assert declaration["dependent_base_rule"] == "exact-verified-feature-head"
    assert (
        declaration["bootstrap"]["scheduler_runtime_requirement"]
        == "fresh-process-or-instance-after-barrier-commit"
    )
    assert declaration["bootstrap"]["pre_reload_evidence_satisfies_gate"] is False
    tasks_path = "openspec/changes/phase-scoped-worktree-lifecycle/tasks.md"
    assert tasks_path in package["locks"]["files"]
    assert tasks_path in package["scope"]["write_allow"]

    requirements = yaml.safe_load((CHANGE / "contracts/prerequisites.yaml").read_text())
    for prerequisite in requirements["prerequisites"]:
        surface = prerequisite["required_surface"]
        assert surface["id"]
        assert surface["files"]
        assert surface["verify_at"] == ["authoritative-merge-sha", "feature-head"]
        assert all(set(item) == {"path", "kind"} for item in surface["files"])


class RecordingLock:
    def __init__(self) -> None:
        self.held = False
        self.entries = 0

    @contextmanager
    def acquire(self):
        assert not self.held
        self.held = True
        self.entries += 1
        try:
            yield
        finally:
            self.held = False


class AdvanceOnSecondReleaseLock(RecordingLock):
    def __init__(self, current_head: list[str]) -> None:
        super().__init__()
        self.current_head = current_head

    @contextmanager
    def acquire(self):
        assert not self.held
        self.held = True
        self.entries += 1
        try:
            yield
        finally:
            self.held = False
            if self.entries == 2:
                self.current_head[0] = "c" * 40


def test_barrier_uses_committed_evidence_bytes_and_records_exact_head(
    tmp_path: Path,
) -> None:
    declaration = {
        **load_execution_gate(POINTER, ROOT),
        "evidence_path": "baseline-gates.json",
    }
    (tmp_path / "baseline-gates.json").write_bytes(b"mutable-worktree-bytes")
    lock = RecordingLock()
    observed: list[tuple[bytes, str]] = []
    runtime_sources = {
        "skills/parallel-infrastructure/scripts/dag_scheduler.py": b"dag-runtime",
        "skills/parallel-infrastructure/scripts/integration_orchestrator.py": b"integration-runtime",
    }

    def read_revision_file(revision: str, path: str) -> bytes:
        assert revision == EVIDENCE_COMMIT
        if path == declaration["evidence_path"]:
            return b"committed-evidence-bytes"
        return runtime_sources[path]

    barrier = FeatureHeadCompletionBarrier(
        declaration=declaration,
        repo_root=tmp_path,
        runtime_revision=EVIDENCE_COMMIT,
        runtime_sources=runtime_sources,
        resolve_feature_head=lambda: EVIDENCE_COMMIT,
        read_revision_file=read_revision_file,
        verify_evidence=lambda payload, head: observed.append((payload, head)),
        branch_lock=lock.acquire,
    )

    assert (
        barrier.verify_and_record(
            expected_feature_head=EVIDENCE_COMMIT,
        )
        == EVIDENCE_COMMIT
    )
    assert barrier.minimum_dependent_base == EVIDENCE_COMMIT
    assert observed == [(b"committed-evidence-bytes", EVIDENCE_COMMIT)]
    assert lock.entries == 1


def test_barrier_lost_head_cas_keeps_completion_blocked() -> None:
    declaration = load_execution_gate(POINTER, ROOT)
    heads = iter([EVIDENCE_COMMIT, "c" * 40])
    barrier = FeatureHeadCompletionBarrier(
        declaration=declaration,
        repo_root=ROOT,
        runtime_revision=EVIDENCE_COMMIT,
        runtime_sources={"runtime.py": b"runtime"},
        resolve_feature_head=lambda: next(heads),
        read_revision_file=lambda _revision, path: (
            b"runtime" if path == "runtime.py" else b"evidence"
        ),
        verify_evidence=lambda _payload, _head: None,
        branch_lock=RecordingLock().acquire,
    )

    with pytest.raises(FeatureHeadBarrierError, match="changed during verification"):
        barrier.verify_and_record(
            expected_feature_head=EVIDENCE_COMMIT,
        )
    assert barrier.minimum_dependent_base is None


def test_runtime_revision_must_equal_the_committed_gate_head() -> None:
    declaration = load_execution_gate(POINTER, ROOT)
    barrier = FeatureHeadCompletionBarrier(
        declaration=declaration,
        repo_root=ROOT,
        runtime_revision=BARRIER_COMMIT,
        runtime_sources={"runtime.py": b"runtime"},
        resolve_feature_head=lambda: EVIDENCE_COMMIT,
        read_revision_file=lambda _revision, _path: b"runtime",
        verify_evidence=lambda _payload, _head: None,
        branch_lock=RecordingLock().acquire,
    )

    with pytest.raises(FeatureHeadBarrierError, match="committed gate revision"):
        barrier.verify_and_record(
            expected_feature_head=EVIDENCE_COMMIT,
        )


def test_runtime_bytes_must_match_the_committed_gate_revision() -> None:
    declaration = load_execution_gate(POINTER, ROOT)
    barrier = FeatureHeadCompletionBarrier(
        declaration=declaration,
        repo_root=ROOT,
        runtime_revision=EVIDENCE_COMMIT,
        runtime_sources={"runtime.py": b"mutable-runtime"},
        resolve_feature_head=lambda: EVIDENCE_COMMIT,
        read_revision_file=lambda _revision, _path: b"committed-runtime",
        verify_evidence=lambda _payload, _head: None,
        branch_lock=RecordingLock().acquire,
    )

    with pytest.raises(FeatureHeadBarrierError, match="runtime bytes"):
        barrier.verify_and_record(expected_feature_head=EVIDENCE_COMMIT)


def test_gate_rejects_an_unbound_empty_runtime_surface() -> None:
    declaration = load_execution_gate(POINTER, ROOT)
    barrier = FeatureHeadCompletionBarrier(
        declaration=declaration,
        repo_root=ROOT,
        runtime_revision=EVIDENCE_COMMIT,
        runtime_sources={},
        resolve_feature_head=lambda: EVIDENCE_COMMIT,
        read_revision_file=lambda _revision, _path: b"evidence",
        verify_evidence=lambda _payload, _head: None,
        branch_lock=RecordingLock().acquire,
    )

    with pytest.raises(FeatureHeadBarrierError, match="runtime source"):
        barrier.verify_and_record(expected_feature_head=EVIDENCE_COMMIT)


def test_scheduler_rejects_plain_completion_and_holds_dependent_base() -> None:
    scheduler = DAGScheduler(
        WORK_PACKAGES,
        ROOT,
        runtime_revision=EVIDENCE_COMMIT,
    )
    result = scheduler.preflight()
    assert result["valid"], result["errors"]

    with pytest.raises(FeatureHeadGateError, match="feature-HEAD barrier"):
        scheduler.mark_completed("wp-baseline-preflight")
    with pytest.raises(FeatureHeadGateError, match="not verified"):
        scheduler.required_base_for("wp-pr-delivery")


def test_scheduler_records_gate_head_as_transitive_dependent_base() -> None:
    scheduler = DAGScheduler(
        WORK_PACKAGES,
        ROOT,
        runtime_revision=EVIDENCE_COMMIT,
    )
    assert scheduler.preflight()["valid"]
    lock = RecordingLock()

    recorded = scheduler.complete_feature_head_gate(
        "wp-baseline-preflight",
        expected_feature_head=EVIDENCE_COMMIT,
        resolve_feature_head=lambda: EVIDENCE_COMMIT,
        read_revision_file=lambda _revision, path: (
            scheduler.runtime_sources[path]
            if path in scheduler.runtime_sources
            else b"committed-evidence"
        ),
        verify_evidence=lambda _payload, _head: None,
        branch_lock=lock.acquire,
    )

    assert recorded == EVIDENCE_COMMIT
    assert scheduler.required_base_for("wp-pr-delivery") == EVIDENCE_COMMIT
    assert scheduler.required_base_for("wp-integration") == EVIDENCE_COMMIT
    assert scheduler.package_statuses["wp-baseline-preflight"].state.value == "completed"


def test_dependent_dispatch_carries_the_exact_verified_feature_base() -> None:
    scheduler = DAGScheduler(
        WORK_PACKAGES,
        ROOT,
        runtime_revision=EVIDENCE_COMMIT,
    )
    result = scheduler.preflight()
    assert result["valid"]
    exposed = {item["package_id"] for item in result["submissions"]}
    assert "wp-pr-delivery" not in exposed
    assert "wp-phase-lifecycle" not in exposed
    assert "wp-pr-delivery" not in {item["package_id"] for item in scheduler.submissions}

    with pytest.raises(FeatureHeadGateError, match="not ready"):
        scheduler.submission_for_dispatch("wp-pr-delivery")
    with pytest.raises(FeatureHeadGateError, match="not ready"):
        scheduler.mark_submitted("wp-pr-delivery", "unsafe-task")

    scheduler.complete_feature_head_gate(
        "wp-baseline-preflight",
        expected_feature_head=EVIDENCE_COMMIT,
        resolve_feature_head=lambda: EVIDENCE_COMMIT,
        read_revision_file=lambda _revision, path: (
            scheduler.runtime_sources[path]
            if path in scheduler.runtime_sources
            else b"committed-evidence"
        ),
        verify_evidence=lambda _payload, _head: None,
        branch_lock=RecordingLock().acquire,
    )
    scheduler.mark_completed("wp-registry")

    published: list[dict] = []
    scheduler.dispatch_with_handoff("wp-pr-delivery", published.append)
    submission = published[0]
    assert submission["input_data"]["package"]["minimum_base_sha"] == EVIDENCE_COMMIT


def test_dispatch_reverifies_committed_evidence_immediately_before_publication() -> None:
    scheduler = DAGScheduler(
        WORK_PACKAGES,
        ROOT,
        runtime_revision=EVIDENCE_COMMIT,
    )
    assert scheduler.preflight()["valid"]
    evidence_reads = 0

    def read_revision_file(_revision: str, path: str) -> bytes:
        nonlocal evidence_reads
        if path in scheduler.runtime_sources:
            return scheduler.runtime_sources[path]
        evidence_reads += 1
        return b"committed-evidence"

    scheduler.complete_feature_head_gate(
        "wp-baseline-preflight",
        expected_feature_head=EVIDENCE_COMMIT,
        resolve_feature_head=lambda: EVIDENCE_COMMIT,
        read_revision_file=read_revision_file,
        verify_evidence=lambda _payload, _head: None,
        branch_lock=RecordingLock().acquire,
    )
    scheduler.mark_completed("wp-registry")

    published: list[dict] = []
    scheduler.dispatch_with_handoff("wp-pr-delivery", published.append)
    submission = published[0]

    assert submission["input_data"]["package"]["minimum_base_sha"] == EVIDENCE_COMMIT
    assert evidence_reads == 2


def test_dispatch_rejects_stale_gate_completion_after_feature_head_advances() -> None:
    scheduler = DAGScheduler(
        WORK_PACKAGES,
        ROOT,
        runtime_revision=EVIDENCE_COMMIT,
    )
    assert scheduler.preflight()["valid"]
    current_head = [EVIDENCE_COMMIT]

    scheduler.complete_feature_head_gate(
        "wp-baseline-preflight",
        expected_feature_head=EVIDENCE_COMMIT,
        resolve_feature_head=lambda: current_head[0],
        read_revision_file=lambda _revision, path: (
            scheduler.runtime_sources[path]
            if path in scheduler.runtime_sources
            else b"committed-evidence"
        ),
        verify_evidence=lambda _payload, _head: None,
        branch_lock=RecordingLock().acquire,
    )
    scheduler.mark_completed("wp-registry")
    current_head[0] = "c" * 40

    published: list[dict] = []
    with pytest.raises(FeatureHeadBarrierError, match="differs"):
        scheduler.dispatch_with_handoff("wp-pr-delivery", published.append)
    assert published == []


def test_gated_dispatch_handoff_is_atomic_with_reverification_and_lock_release() -> None:
    scheduler = DAGScheduler(
        WORK_PACKAGES,
        ROOT,
        runtime_revision=EVIDENCE_COMMIT,
    )
    assert scheduler.preflight()["valid"]
    current_head = [EVIDENCE_COMMIT]
    lock = AdvanceOnSecondReleaseLock(current_head)
    published: list[dict] = []

    scheduler.complete_feature_head_gate(
        "wp-baseline-preflight",
        expected_feature_head=EVIDENCE_COMMIT,
        resolve_feature_head=lambda: current_head[0],
        read_revision_file=lambda _revision, path: (
            scheduler.runtime_sources[path]
            if path in scheduler.runtime_sources
            else b"committed-evidence"
        ),
        verify_evidence=lambda _payload, _head: None,
        branch_lock=lock.acquire,
    )
    scheduler.mark_completed("wp-registry")
    assert "wp-pr-delivery" not in {
        submission["package_id"] for submission in scheduler.submissions
    }

    def publish(submission: dict) -> None:
        assert lock.held
        assert current_head[0] == EVIDENCE_COMMIT
        assert submission["input_data"]["package"]["minimum_base_sha"] == current_head[0]
        published.append(submission)

    result = scheduler.dispatch_with_handoff("wp-pr-delivery", publish)

    assert result is None
    assert len(published) == 1
    assert current_head[0] == "c" * 40
    with pytest.raises(FeatureHeadGateError, match="atomic dispatch handoff"):
        scheduler.submission_for_dispatch("wp-pr-delivery")

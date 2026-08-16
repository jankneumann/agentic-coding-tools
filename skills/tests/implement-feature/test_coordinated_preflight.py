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


def test_barrier_reverifies_evidence_under_lock_and_records_exact_head() -> None:
    declaration = load_execution_gate(POINTER, ROOT)
    lock = RecordingLock()
    observed: list[tuple[Path, str]] = []

    barrier = FeatureHeadCompletionBarrier(
        declaration=declaration,
        repo_root=ROOT,
        resolve_feature_head=lambda: EVIDENCE_COMMIT,
        verify_evidence=lambda path, head: observed.append((path, head)),
        branch_lock=lock.acquire,
    )

    assert (
        barrier.verify_and_record(
            expected_feature_head=EVIDENCE_COMMIT,
            runtime_revision=BARRIER_COMMIT,
        )
        == EVIDENCE_COMMIT
    )
    assert barrier.minimum_dependent_base == EVIDENCE_COMMIT
    assert observed == [(ROOT / declaration["evidence_path"], EVIDENCE_COMMIT)]
    assert lock.entries == 1


def test_barrier_lost_head_cas_keeps_completion_blocked() -> None:
    declaration = load_execution_gate(POINTER, ROOT)
    heads = iter([EVIDENCE_COMMIT, "c" * 40])
    barrier = FeatureHeadCompletionBarrier(
        declaration=declaration,
        repo_root=ROOT,
        resolve_feature_head=lambda: next(heads),
        verify_evidence=lambda _path, _head: None,
        branch_lock=RecordingLock().acquire,
    )

    with pytest.raises(FeatureHeadBarrierError, match="changed during verification"):
        barrier.verify_and_record(
            expected_feature_head=EVIDENCE_COMMIT,
            runtime_revision=BARRIER_COMMIT,
        )
    assert barrier.minimum_dependent_base is None


def test_pre_reload_runtime_cannot_satisfy_declared_gate() -> None:
    declaration = load_execution_gate(POINTER, ROOT)
    barrier = FeatureHeadCompletionBarrier(
        declaration=declaration,
        repo_root=ROOT,
        resolve_feature_head=lambda: EVIDENCE_COMMIT,
        verify_evidence=lambda _path, _head: None,
        branch_lock=RecordingLock().acquire,
    )

    with pytest.raises(FeatureHeadBarrierError, match="fresh scheduler runtime"):
        barrier.verify_and_record(
            expected_feature_head=EVIDENCE_COMMIT,
            runtime_revision=None,
        )


def test_scheduler_rejects_plain_completion_and_holds_dependent_base() -> None:
    scheduler = DAGScheduler(
        WORK_PACKAGES,
        ROOT,
        runtime_revision=BARRIER_COMMIT,
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
        runtime_revision=BARRIER_COMMIT,
    )
    assert scheduler.preflight()["valid"]
    lock = RecordingLock()

    recorded = scheduler.complete_feature_head_gate(
        "wp-baseline-preflight",
        expected_feature_head=EVIDENCE_COMMIT,
        resolve_feature_head=lambda: EVIDENCE_COMMIT,
        verify_evidence=lambda _path, _head: None,
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
        runtime_revision=BARRIER_COMMIT,
    )
    assert scheduler.preflight()["valid"]

    with pytest.raises(FeatureHeadGateError, match="not ready"):
        scheduler.submission_for_dispatch("wp-pr-delivery")

    scheduler.complete_feature_head_gate(
        "wp-baseline-preflight",
        expected_feature_head=EVIDENCE_COMMIT,
        resolve_feature_head=lambda: EVIDENCE_COMMIT,
        verify_evidence=lambda _path, _head: None,
        branch_lock=RecordingLock().acquire,
    )
    scheduler.mark_completed("wp-registry")

    submission = scheduler.submission_for_dispatch("wp-pr-delivery")
    assert submission["input_data"]["package"]["minimum_base_sha"] == EVIDENCE_COMMIT

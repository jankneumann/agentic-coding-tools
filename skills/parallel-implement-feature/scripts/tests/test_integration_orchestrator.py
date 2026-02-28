"""Tests for integration_orchestrator module (Phase C3-C6)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_SKILL_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SKILL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS_DIR))

from integration_orchestrator import (
    IntegrationGateStatus,
    IntegrationOrchestrator,
)


def _make_packages() -> list[dict[str, Any]]:
    """Diamond DAG: contracts -> backend + frontend -> integration."""
    return [
        {"package_id": "wp-contracts", "task_type": "contracts"},
        {"package_id": "wp-backend", "task_type": "implement"},
        {"package_id": "wp-frontend", "task_type": "implement"},
        {"package_id": "wp-integration", "task_type": "integrate"},
    ]


def _make_result(
    package_id: str = "wp-backend",
    status: str = "completed",
    files_modified: list[str] | None = None,
    verification_passed: bool = True,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "feature_id": "test-feature",
        "package_id": package_id,
        "status": status,
        "files_modified": files_modified or ["src/api/users.py"],
        "verification": {"tier": "A", "passed": verification_passed, "steps": []},
        "timestamps": {"started_at": "2026-01-01T00:00:00Z", "finished_at": "2026-01-01T00:30:00Z"},
        "git": {"base": {"ref": "main"}, "head": {"commit": "abc1234"}},
    }


def _make_findings(
    package_id: str = "wp-backend",
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "review_type": "implementation",
        "target": package_id,
        "reviewer_vendor": "test",
        "findings": findings or [],
    }


def _make_finding(
    finding_id: int = 1,
    disposition: str = "accept",
    description: str = "Minor style issue",
) -> dict[str, Any]:
    return {
        "id": finding_id,
        "type": "style",
        "criticality": "low",
        "description": description,
        "resolution": "Optional fix",
        "disposition": disposition,
    }


@pytest.fixture
def orch() -> IntegrationOrchestrator:
    return IntegrationOrchestrator(
        feature_id="test-feature",
        packages=_make_packages(),
    )


class TestPackageClassification:
    def test_implementation_packages(self, orch: IntegrationOrchestrator) -> None:
        impl = orch.implementation_packages
        assert set(impl) == {"wp-contracts", "wp-backend", "wp-frontend"}

    def test_integration_package_id(self, orch: IntegrationOrchestrator) -> None:
        assert orch.integration_package_id == "wp-integration"

    def test_no_integration_package(self) -> None:
        o = IntegrationOrchestrator(
            feature_id="test",
            packages=[{"package_id": "wp-a", "task_type": "implement"}],
        )
        assert o.integration_package_id is None


class TestPendingReview:
    def test_no_results(self, orch: IntegrationOrchestrator) -> None:
        assert orch.get_packages_pending_review() == []

    def test_results_without_reviews(self, orch: IntegrationOrchestrator) -> None:
        orch.record_package_result("wp-backend", _make_result("wp-backend"))
        orch.record_package_result("wp-frontend", _make_result("wp-frontend"))
        pending = orch.get_packages_pending_review()
        assert pending == ["wp-backend", "wp-frontend"]

    def test_results_with_partial_reviews(self, orch: IntegrationOrchestrator) -> None:
        orch.record_package_result("wp-backend", _make_result("wp-backend"))
        orch.record_package_result("wp-frontend", _make_result("wp-frontend"))
        orch.record_review_findings("wp-backend", _make_findings("wp-backend"))
        pending = orch.get_packages_pending_review()
        assert pending == ["wp-frontend"]


class TestIntegrationGate:
    def test_gate_passes_all_reviewed_no_blocking(self, orch: IntegrationOrchestrator) -> None:
        for pid in orch.implementation_packages:
            orch.record_package_result(pid, _make_result(pid))
            orch.record_review_findings(pid, _make_findings(pid, [_make_finding(disposition="accept")]))

        gate = orch.check_integration_gate()
        assert gate["status"] == IntegrationGateStatus.PASS.value
        assert gate["blocking_findings"] == []
        assert gate["missing_reviews"] == []

    def test_gate_blocked_missing_results(self, orch: IntegrationOrchestrator) -> None:
        orch.record_package_result("wp-backend", _make_result("wp-backend"))
        gate = orch.check_integration_gate()
        assert gate["status"] == IntegrationGateStatus.BLOCKED_INCOMPLETE.value

    def test_gate_blocked_missing_reviews(self, orch: IntegrationOrchestrator) -> None:
        for pid in orch.implementation_packages:
            orch.record_package_result(pid, _make_result(pid))
        # Only review one
        orch.record_review_findings("wp-backend", _make_findings("wp-backend"))
        gate = orch.check_integration_gate()
        assert gate["status"] == IntegrationGateStatus.BLOCKED_INCOMPLETE.value
        assert "wp-contracts" in gate["missing_reviews"] or "wp-frontend" in gate["missing_reviews"]

    def test_gate_blocked_fix_findings(self, orch: IntegrationOrchestrator) -> None:
        for pid in orch.implementation_packages:
            orch.record_package_result(pid, _make_result(pid))
            findings = [] if pid != "wp-backend" else [_make_finding(disposition="fix", description="Bug found")]
            orch.record_review_findings(pid, _make_findings(pid, findings))

        gate = orch.check_integration_gate()
        assert gate["status"] == IntegrationGateStatus.BLOCKED_FIX.value
        assert len(gate["blocking_findings"]) == 1
        assert gate["blocking_findings"][0]["package_id"] == "wp-backend"

    def test_gate_blocked_escalate_findings(self, orch: IntegrationOrchestrator) -> None:
        for pid in orch.implementation_packages:
            orch.record_package_result(pid, _make_result(pid))
            findings = [] if pid != "wp-frontend" else [_make_finding(disposition="escalate")]
            orch.record_review_findings(pid, _make_findings(pid, findings))

        gate = orch.check_integration_gate()
        assert gate["status"] == IntegrationGateStatus.BLOCKED_ESCALATE.value

    def test_escalate_takes_priority_over_fix(self, orch: IntegrationOrchestrator) -> None:
        for pid in orch.implementation_packages:
            orch.record_package_result(pid, _make_result(pid))
        orch.record_review_findings("wp-backend", _make_findings("wp-backend", [_make_finding(disposition="fix")]))
        orch.record_review_findings("wp-frontend", _make_findings("wp-frontend", [_make_finding(disposition="escalate")]))
        orch.record_review_findings("wp-contracts", _make_findings("wp-contracts"))

        gate = orch.check_integration_gate()
        assert gate["status"] == IntegrationGateStatus.BLOCKED_ESCALATE.value

    def test_accept_and_regenerate_dont_block(self, orch: IntegrationOrchestrator) -> None:
        for pid in orch.implementation_packages:
            orch.record_package_result(pid, _make_result(pid))
            findings = [
                _make_finding(finding_id=1, disposition="accept"),
                _make_finding(finding_id=2, disposition="regenerate"),
            ]
            orch.record_review_findings(pid, _make_findings(pid, findings))

        gate = orch.check_integration_gate()
        assert gate["status"] == IntegrationGateStatus.PASS.value


class TestExecutionSummary:
    def _populate_all(self, orch: IntegrationOrchestrator) -> None:
        for pid in orch.implementation_packages:
            orch.record_package_result(pid, _make_result(pid))
            orch.record_review_findings(pid, _make_findings(pid, [_make_finding()]))

    def test_summary_structure(self, orch: IntegrationOrchestrator) -> None:
        self._populate_all(orch)
        summary = orch.generate_execution_summary()
        assert summary["feature_id"] == "test-feature"
        assert "generated_at" in summary
        assert "packages" in summary
        assert "gate" in summary
        assert "timeline" in summary
        assert "review" in summary
        assert "integration" in summary

    def test_package_counts(self, orch: IntegrationOrchestrator) -> None:
        self._populate_all(orch)
        summary = orch.generate_execution_summary()
        assert summary["packages"]["total"] == 4
        assert summary["packages"]["implementation"] == 3
        assert summary["packages"]["completed"] == 3

    def test_timeline_entries(self, orch: IntegrationOrchestrator) -> None:
        self._populate_all(orch)
        summary = orch.generate_execution_summary()
        assert len(summary["timeline"]) == 3
        for entry in summary["timeline"]:
            assert entry["status"] == "completed"
            assert entry["files_modified"] == 1

    def test_review_summary(self, orch: IntegrationOrchestrator) -> None:
        self._populate_all(orch)
        summary = orch.generate_execution_summary()
        assert summary["review"]["packages_reviewed"] == 3
        assert summary["review"]["total_findings"] == 3
        assert summary["review"]["findings_by_disposition"]["accept"] == 3

    def test_integration_not_started(self, orch: IntegrationOrchestrator) -> None:
        summary = orch.generate_execution_summary()
        assert summary["integration"]["status"] == "not_started"

    def test_integration_completed(self, orch: IntegrationOrchestrator) -> None:
        self._populate_all(orch)
        orch.record_integration_result({
            "status": "completed",
            "verification": {"passed": True},
            "git": {"base": {"ref": "main"}, "head": {"commit": "merge123"}},
        })
        summary = orch.generate_execution_summary()
        assert summary["integration"]["status"] == "completed"
        assert summary["integration"]["verification_passed"] is True
        assert summary["integration"]["merge_commit"] == "merge123"

    def test_incomplete_summary(self, orch: IntegrationOrchestrator) -> None:
        orch.record_package_result("wp-backend", _make_result("wp-backend"))
        summary = orch.generate_execution_summary()
        assert summary["packages"]["completed"] == 1
        timeline_statuses = {e["package_id"]: e["status"] for e in summary["timeline"]}
        assert timeline_statuses["wp-backend"] == "completed"
        assert timeline_statuses["wp-frontend"] == "not_started"

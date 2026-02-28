"""Integration orchestrator for Phase C3-C6 of parallel-implement-feature.

Manages the review and integration sequencing after all implementation
packages complete:

C3. Per-package review dispatch
C4. Integration gate (all packages reviewed, no blocking findings)
C5. wp-integration merge package execution
C6. Execution summary generation

Usage:
    from integration_orchestrator import IntegrationOrchestrator

    orch = IntegrationOrchestrator(
        feature_id="add-user-auth",
        packages=work_packages_data["packages"],
    )
    orch.record_package_result("wp-backend", result_data)
    orch.record_review_findings("wp-backend", findings_data)
    gate = orch.check_integration_gate()
    summary = orch.generate_execution_summary()
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ReviewDisposition(str, Enum):
    """Disposition from a review finding."""

    FIX = "fix"
    REGENERATE = "regenerate"
    ACCEPT = "accept"
    ESCALATE = "escalate"


class IntegrationGateStatus(str, Enum):
    """Status of the integration gate check."""

    PASS = "pass"
    BLOCKED_FIX = "blocked_fix"
    BLOCKED_ESCALATE = "blocked_escalate"
    BLOCKED_INCOMPLETE = "blocked_incomplete"


class IntegrationOrchestrator:
    """Orchestrates review dispatch, integration gate, and summary generation."""

    def __init__(
        self,
        feature_id: str,
        packages: list[dict[str, Any]],
    ):
        self.feature_id = feature_id
        self.packages = {p["package_id"]: p for p in packages}
        self._results: dict[str, dict[str, Any]] = {}
        self._review_findings: dict[str, dict[str, Any]] = {}
        self._integration_result: dict[str, Any] | None = None

    @property
    def implementation_packages(self) -> list[str]:
        """Package IDs excluding wp-integration."""
        return [
            pid for pid in self.packages
            if self.packages[pid].get("task_type") != "integrate"
        ]

    @property
    def integration_package_id(self) -> str | None:
        """The wp-integration package ID, if present."""
        for pid, pkg in self.packages.items():
            if pkg.get("task_type") == "integrate":
                return pid
        return None

    def record_package_result(
        self, package_id: str, result: dict[str, Any]
    ) -> None:
        """Record a completed package's work-queue result."""
        self._results[package_id] = result

    def record_review_findings(
        self, package_id: str, findings: dict[str, Any]
    ) -> None:
        """Record review findings for a package.

        Args:
            findings: Dict conforming to review-findings.schema.json
        """
        self._review_findings[package_id] = findings

    def get_packages_pending_review(self) -> list[str]:
        """Return package IDs that have results but no review findings."""
        return sorted(
            pid
            for pid in self.implementation_packages
            if pid in self._results and pid not in self._review_findings
        )

    def check_integration_gate(self) -> dict[str, Any]:
        """C4: Check if all packages are ready for integration.

        Returns:
            Dict with:
            - status: IntegrationGateStatus value
            - reason: human-readable explanation
            - blocking_findings: list of blocking finding summaries
            - missing_reviews: list of package_ids without reviews
        """
        impl_pkgs = self.implementation_packages

        # Check completeness
        missing_results = [pid for pid in impl_pkgs if pid not in self._results]
        if missing_results:
            return {
                "status": IntegrationGateStatus.BLOCKED_INCOMPLETE.value,
                "reason": f"Packages not completed: {missing_results}",
                "blocking_findings": [],
                "missing_reviews": missing_results,
            }

        missing_reviews = [pid for pid in impl_pkgs if pid not in self._review_findings]
        if missing_reviews:
            return {
                "status": IntegrationGateStatus.BLOCKED_INCOMPLETE.value,
                "reason": f"Packages not reviewed: {missing_reviews}",
                "blocking_findings": [],
                "missing_reviews": missing_reviews,
            }

        # Check for blocking findings
        blocking: list[dict[str, str]] = []
        escalations: list[dict[str, str]] = []

        for pid, findings in self._review_findings.items():
            for finding in findings.get("findings", []):
                disposition = finding.get("disposition", "")
                if disposition == ReviewDisposition.FIX.value:
                    blocking.append({
                        "package_id": pid,
                        "finding_id": str(finding.get("id", "")),
                        "description": finding.get("description", ""),
                        "disposition": disposition,
                    })
                elif disposition == ReviewDisposition.ESCALATE.value:
                    escalations.append({
                        "package_id": pid,
                        "finding_id": str(finding.get("id", "")),
                        "description": finding.get("description", ""),
                        "disposition": disposition,
                    })

        if escalations:
            return {
                "status": IntegrationGateStatus.BLOCKED_ESCALATE.value,
                "reason": f"{len(escalations)} finding(s) require escalation",
                "blocking_findings": escalations,
                "missing_reviews": [],
            }

        if blocking:
            return {
                "status": IntegrationGateStatus.BLOCKED_FIX.value,
                "reason": f"{len(blocking)} finding(s) require fix before integration",
                "blocking_findings": blocking,
                "missing_reviews": [],
            }

        return {
            "status": IntegrationGateStatus.PASS.value,
            "reason": "All packages completed and reviewed with no blocking findings",
            "blocking_findings": [],
            "missing_reviews": [],
        }

    def record_integration_result(self, result: dict[str, Any]) -> None:
        """Record the wp-integration package result."""
        self._integration_result = result

    def generate_execution_summary(self) -> dict[str, Any]:
        """C6: Generate the full execution summary.

        Returns a summary dict with DAG timeline, review findings,
        and integration outcome.
        """
        impl_pkgs = self.implementation_packages
        gate = self.check_integration_gate()

        # Package timeline
        timeline: list[dict[str, Any]] = []
        for pid in impl_pkgs:
            entry: dict[str, Any] = {"package_id": pid}
            result = self._results.get(pid)
            if result:
                entry["status"] = result.get("status", "unknown")
                entry["verification_passed"] = result.get("verification", {}).get("passed")
                entry["files_modified"] = len(result.get("files_modified", []))
                timestamps = result.get("timestamps", {})
                entry["started_at"] = timestamps.get("started_at")
                entry["finished_at"] = timestamps.get("finished_at")
            else:
                entry["status"] = "not_started"
            timeline.append(entry)

        # Review summary
        review_summary: dict[str, Any] = {"packages_reviewed": 0, "findings_by_disposition": {}}
        disposition_counts: dict[str, int] = defaultdict(int)
        total_findings = 0

        for pid, findings in self._review_findings.items():
            review_summary["packages_reviewed"] += 1
            for finding in findings.get("findings", []):
                total_findings += 1
                disposition_counts[finding.get("disposition", "unknown")] += 1

        review_summary["total_findings"] = total_findings
        review_summary["findings_by_disposition"] = dict(disposition_counts)

        # Integration outcome
        integration: dict[str, Any] = {"status": "not_started"}
        if self._integration_result:
            integration = {
                "status": self._integration_result.get("status", "unknown"),
                "verification_passed": self._integration_result.get("verification", {}).get("passed"),
                "merge_commit": self._integration_result.get("git", {}).get("head", {}).get("commit"),
            }

        return {
            "feature_id": self.feature_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "packages": {
                "total": len(self.packages),
                "implementation": len(impl_pkgs),
                "completed": len(self._results),
            },
            "gate": gate,
            "timeline": timeline,
            "review": review_summary,
            "integration": integration,
        }

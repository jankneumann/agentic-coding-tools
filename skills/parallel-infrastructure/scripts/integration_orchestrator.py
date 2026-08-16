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
from pathlib import Path
from typing import Any, Callable, ContextManager


class FeatureHeadBarrierError(RuntimeError):
    """Raised when a feature-HEAD completion barrier loses verification."""


class FeatureHeadCompletionBarrier:
    """Reverify committed evidence and fence dependent dispatch to one HEAD.

    The caller supplies the branch lock and feature-HEAD resolver so this
    primitive stays independent of the coordinator and worktree backends.
    """

    def __init__(
        self,
        *,
        declaration: dict[str, Any],
        repo_root: Path,
        runtime_revision: str | None,
        runtime_sources: dict[str, bytes],
        resolve_feature_head: Callable[[], str],
        read_revision_file: Callable[[str, str], bytes],
        verify_evidence: Callable[[bytes, str], None],
        branch_lock: Callable[[], ContextManager[None]],
    ) -> None:
        self.declaration = declaration
        self.repo_root = Path(repo_root)
        self.runtime_revision = runtime_revision
        self.runtime_sources = runtime_sources
        self.resolve_feature_head = resolve_feature_head
        self.read_revision_file = read_revision_file
        self.verify_evidence = verify_evidence
        self.branch_lock = branch_lock
        self.minimum_dependent_base: str | None = None

    def verify_and_record(
        self,
        *,
        expected_feature_head: str,
    ) -> str:
        """Verify evidence under lock and record the unchanged exact HEAD."""
        bootstrap = self.declaration.get("bootstrap", {})
        if (
            bootstrap.get("scheduler_runtime_requirement")
            == "fresh-process-or-instance-after-barrier-commit"
            and self.runtime_revision != expected_feature_head
        ):
            raise FeatureHeadBarrierError(
                "scheduler runtime is not bound to the committed gate revision"
            )
        if not self.runtime_sources:
            raise FeatureHeadBarrierError("feature-HEAD gate has no bound runtime source bytes")

        with self.branch_lock():
            observed = self.resolve_feature_head()
            if observed != expected_feature_head:
                raise FeatureHeadBarrierError(
                    "feature HEAD differs from the expected completion CAS"
                )
            for path, loaded_bytes in self.runtime_sources.items():
                committed_bytes = self.read_revision_file(observed, path)
                if committed_bytes != loaded_bytes:
                    raise FeatureHeadBarrierError(
                        f"loaded runtime bytes differ from committed gate revision: {path}"
                    )
            evidence_bytes = self.read_revision_file(observed, self.declaration["evidence_path"])
            self.verify_evidence(evidence_bytes, observed)
            after_verification = self.resolve_feature_head()
            if after_verification != observed:
                raise FeatureHeadBarrierError(
                    "feature HEAD changed during verification; completion CAS lost"
                )
            self.minimum_dependent_base = observed
            return observed

    def reverify_recorded_head(self) -> str:
        """Revalidate the recorded gate HEAD immediately before dependent use."""
        if self.minimum_dependent_base is None:
            raise FeatureHeadBarrierError("feature-HEAD gate has no recorded completion")
        return self.verify_and_record(
            expected_feature_head=self.minimum_dependent_base,
        )


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
        # Legacy single-vendor storage (backward compat)
        self._review_findings: dict[str, dict[str, Any]] = {}
        # Multi-vendor storage: package_id → vendor → findings
        self._vendor_findings: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        # Consensus reports: package_id → consensus dict
        self._consensus: dict[str, dict[str, Any]] = {}
        self._integration_result: dict[str, Any] | None = None

    @property
    def implementation_packages(self) -> list[str]:
        """Package IDs excluding wp-integration."""
        return [pid for pid in self.packages if self.packages[pid].get("task_type") != "integrate"]

    @property
    def integration_package_id(self) -> str | None:
        """The wp-integration package ID, if present."""
        for pid, pkg in self.packages.items():
            if pkg.get("task_type") == "integrate":
                return pid
        return None

    def record_package_result(self, package_id: str, result: dict[str, Any]) -> None:
        """Record a completed package's work-queue result."""
        self._results[package_id] = result

    def record_review_findings(
        self,
        package_id: str,
        findings: dict[str, Any],
        vendor: str | None = None,
    ) -> None:
        """Record review findings for a package.

        Args:
            findings: Dict conforming to review-findings.schema.json
            vendor: Vendor name (e.g., "codex"). If None, stores as
                single-vendor finding for backward compatibility.
        """
        if vendor:
            self._vendor_findings[package_id][vendor] = findings
        # Always update legacy storage (gate uses this as primary)
        self._review_findings[package_id] = findings

    def record_consensus(self, package_id: str, consensus: dict[str, Any]) -> None:
        """Record a multi-vendor consensus report for a package.

        Args:
            consensus: Dict conforming to consensus-report.schema.json
        """
        self._consensus[package_id] = consensus

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

        # Check for blocking findings — use consensus when available,
        # fall back to raw findings for single-vendor reviews.
        blocking: list[dict[str, str]] = []
        escalations: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []

        for pid in impl_pkgs:
            if pid in self._consensus:
                # Multi-vendor: use consensus findings
                consensus = self._consensus[pid]
                for cf in consensus.get("consensus_findings", []):
                    status = cf.get("status", "")
                    disposition = cf.get("recommended_disposition", "")
                    entry = {
                        "package_id": pid,
                        "finding_id": str(cf.get("id", "")),
                        "description": cf.get("description", ""),
                        "disposition": disposition,
                        "consensus_status": status,
                    }
                    if status == "confirmed" and disposition == ReviewDisposition.FIX.value:
                        blocking.append(entry)
                    elif status == "disagreement":
                        escalations.append(entry)
                    elif status == "unconfirmed":
                        warnings.append(entry)
            elif pid in self._review_findings:
                # Single-vendor fallback
                findings = self._review_findings[pid]
                for finding in findings.get("findings", []):
                    disposition = finding.get("disposition", "")
                    if disposition == ReviewDisposition.FIX.value:
                        blocking.append(
                            {
                                "package_id": pid,
                                "finding_id": str(finding.get("id", "")),
                                "description": finding.get("description", ""),
                                "disposition": disposition,
                            }
                        )
                    elif disposition == ReviewDisposition.ESCALATE.value:
                        escalations.append(
                            {
                                "package_id": pid,
                                "finding_id": str(finding.get("id", "")),
                                "description": finding.get("description", ""),
                                "disposition": disposition,
                            }
                        )

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
            "warnings": warnings,
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

        # Multi-vendor review info
        if self._consensus:
            consensus_summary: dict[str, Any] = {
                "packages_with_consensus": len(self._consensus),
                "confirmed": 0,
                "unconfirmed": 0,
                "disagreement": 0,
            }
            for consensus in self._consensus.values():
                summary = consensus.get("summary", {})
                consensus_summary["confirmed"] += summary.get("confirmed_count", 0)
                consensus_summary["unconfirmed"] += summary.get("unconfirmed_count", 0)
                consensus_summary["disagreement"] += summary.get("disagreement_count", 0)
            review_summary["consensus"] = consensus_summary

        if self._vendor_findings:
            vendors_used: set[str] = set()
            for vendor_map in self._vendor_findings.values():
                vendors_used.update(vendor_map.keys())
            review_summary["vendors"] = sorted(vendors_used)

        # Integration outcome
        integration: dict[str, Any] = {"status": "not_started"}
        if self._integration_result:
            integration = {
                "status": self._integration_result.get("status", "unknown"),
                "verification_passed": self._integration_result.get("verification", {}).get(
                    "passed"
                ),
                "merge_commit": self._integration_result.get("git", {})
                .get("head", {})
                .get("commit"),
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

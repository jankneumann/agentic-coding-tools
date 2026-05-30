"""Fidelity report generation for DTU scaffolds.

A fidelity report measures how well a doc-derived DTU represents the
actual external system. It determines whether the DTU is eligible for
holdout-backed validation.

Design Decision D3: DTUs start as DTU-lite scaffolds. Live probing is
optional and enhances the fidelity score but is never required. DTUs
from docs alone are eligible for public scenarios only. Holdout
eligibility requires live probes or explicit operator approval.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Score thresholds
HOLDOUT_ELIGIBLE_THRESHOLD = 0.7
LOW_CONFIDENCE_THRESHOLD = 0.4


@dataclass
class ProbeResult:
    """Result of probing a single endpoint against the live system."""

    endpoint: str
    method: str
    expected_status: int
    actual_status: int | None = None
    response_matches: bool = False
    error: str | None = None

    @property
    def success(self) -> bool:
        return (
            self.actual_status is not None
            and self.actual_status == self.expected_status
            and self.response_matches
        )


@dataclass
class FidelityReport:
    """Fidelity assessment for a DTU scaffold.

    Captures the confidence level of a doc-derived DTU and determines
    whether it's eligible for holdout-backed validation.
    """

    system_name: str
    sources_ingested: list[str] = field(default_factory=list)
    unsupported_surfaces: list[str] = field(default_factory=list)
    probe_results: list[ProbeResult] = field(default_factory=list)
    conformance_score: float = 0.0
    holdout_eligible: bool = False
    operator_approved: bool = False
    notes: str = ""

    @property
    def has_probes(self) -> bool:
        return len(self.probe_results) > 0

    @property
    def probe_pass_rate(self) -> float:
        if not self.probe_results:
            return 0.0
        passed = sum(1 for p in self.probe_results if p.success)
        return passed / len(self.probe_results)


def compute_fidelity(
    system_name: str,
    sources: list[str],
    unsupported_surfaces: list[str],
    total_endpoints: int,
    probe_results: list[ProbeResult] | None = None,
    operator_approved: bool = False,
) -> FidelityReport:
    """Compute a fidelity report for a DTU scaffold.

    The conformance score is computed from:
    - Documentation coverage: ratio of supported to total surfaces
    - Probe accuracy: pass rate of live probes (if any)
    - Combined score: weighted average favoring probes when available

    Args:
        system_name: Name of the external system.
        sources: List of documentation sources ingested.
        unsupported_surfaces: API surfaces that can't be simulated.
        total_endpoints: Total number of documented endpoints.
        probe_results: Optional live probe results.
        operator_approved: Whether operator explicitly approves holdout.

    Returns:
        FidelityReport with conformance score and holdout eligibility.
    """
    # Documentation coverage score (clamped to [0.0, 1.0])
    if total_endpoints > 0:
        doc_coverage = max(0.0, 1.0 - (len(unsupported_surfaces) / total_endpoints))
    else:
        doc_coverage = 0.0

    # Probe score (0.0 if no probes)
    probes = probe_results or []
    probe_score = 0.0
    if probes:
        probe_score = sum(1 for p in probes if p.success) / len(probes)

    # Combined score: probes weigh more when available
    if probes:
        conformance = 0.3 * doc_coverage + 0.7 * probe_score
    else:
        conformance = doc_coverage * 0.6  # Capped at 0.6 without probes

    # Holdout eligibility
    holdout_eligible = (
        operator_approved
        or (conformance >= HOLDOUT_ELIGIBLE_THRESHOLD and len(probes) > 0)
    )

    return FidelityReport(
        system_name=system_name,
        sources_ingested=sources,
        unsupported_surfaces=unsupported_surfaces,
        probe_results=probes,
        conformance_score=round(conformance, 3),
        holdout_eligible=holdout_eligible,
        operator_approved=operator_approved,
    )


def write_fidelity_report(report: FidelityReport, path: Path) -> None:
    """Write a fidelity report as JSON."""
    data: dict[str, Any] = {
        "system_name": report.system_name,
        "sources_ingested": report.sources_ingested,
        "unsupported_surfaces": report.unsupported_surfaces,
        "conformance_score": report.conformance_score,
        "holdout_eligible": report.holdout_eligible,
        "operator_approved": report.operator_approved,
        "has_probes": report.has_probes,
        "notes": report.notes,
    }

    if report.probe_results:
        data["probe_results"] = [
            {
                "endpoint": p.endpoint,
                "method": p.method,
                "expected_status": p.expected_status,
                "actual_status": p.actual_status,
                "response_matches": p.response_matches,
                "success": p.success,
                "error": p.error,
            }
            for p in report.probe_results
        ]
        data["probe_pass_rate"] = report.probe_pass_rate

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

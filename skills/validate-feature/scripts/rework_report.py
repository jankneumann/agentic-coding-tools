"""Rework report generation from validation results.

Produces a machine-readable rework-report.json that maps failed scenarios
to likely owners, requirement refs, files, and recommended next actions.

Design Decision D4: Validation emits a machine-readable rework report.
/iterate-on-implementation consumes it as primary input rather than
reparsing freeform validation prose.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Action constants
ACTION_ITERATE = "iterate"
ACTION_REVISE_SPEC = "revise-spec"
ACTION_DEFER = "defer"
ACTION_BLOCK_CLEANUP = "block-cleanup"
ACTION_NONE = "none"

VALID_ACTIONS = {ACTION_ITERATE, ACTION_REVISE_SPEC, ACTION_DEFER, ACTION_BLOCK_CLEANUP, ACTION_NONE}


@dataclass
class ReworkFailure:
    """A single failed scenario with routing metadata."""

    scenario_id: str
    visibility: str = "public"
    requirement_refs: list[str] = field(default_factory=list)
    implicated_interfaces: list[str] = field(default_factory=list)
    implicated_files: list[str] = field(default_factory=list)
    likely_owner: str = ""
    recommended_action: str = ACTION_ITERATE

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "visibility": self.visibility,
            "requirement_refs": self.requirement_refs,
            "implicated_interfaces": self.implicated_interfaces,
            "implicated_files": self.implicated_files,
            "likely_owner": self.likely_owner,
            "recommended_action": self.recommended_action,
        }


@dataclass
class ReworkReport:
    """Machine-readable rework report from validation."""

    failures: list[ReworkFailure] = field(default_factory=list)

    @property
    def total_failures(self) -> int:
        return len(self.failures)

    @property
    def public_failures(self) -> int:
        return sum(1 for f in self.failures if f.visibility == "public")

    @property
    def holdout_failures(self) -> int:
        return sum(1 for f in self.failures if f.visibility == "holdout")

    @property
    def has_blocking_holdout(self) -> bool:
        return any(
            f.visibility == "holdout" and f.recommended_action == ACTION_BLOCK_CLEANUP
            for f in self.failures
        )

    @property
    def summary_action(self) -> str:
        if not self.failures:
            return ACTION_NONE
        if self.has_blocking_holdout:
            return ACTION_BLOCK_CLEANUP
        actions = {f.recommended_action for f in self.failures}
        if ACTION_ITERATE in actions:
            return ACTION_ITERATE
        if ACTION_REVISE_SPEC in actions:
            return ACTION_REVISE_SPEC
        return ACTION_DEFER

    def to_dict(self) -> dict[str, Any]:
        return {
            "failures": [f.to_dict() for f in self.failures],
            "summary": {
                "total_failures": self.total_failures,
                "public_failures": self.public_failures,
                "holdout_failures": self.holdout_failures,
                "has_blocking_holdout": self.has_blocking_holdout,
                "recommended_action": self.summary_action,
            },
        }


def generate_rework_report(
    failed_scenarios: list[dict[str, Any]],
    manifest_entries: dict[str, dict[str, Any]] | None = None,
) -> ReworkReport:
    """Generate a rework report from failed scenario data.

    Args:
        failed_scenarios: List of dicts with at minimum 'scenario_id' and 'status'.
            May also include 'interfaces_tested', 'category', 'failure_summary'.
        manifest_entries: Optional map of scenario_id -> manifest entry dict
            for visibility classification.

    Returns:
        ReworkReport with failure routing metadata.
    """
    manifest = manifest_entries or {}
    failures: list[ReworkFailure] = []

    for scenario in failed_scenarios:
        scenario_id = scenario.get("scenario_id", "unknown")
        manifest_entry = manifest.get(scenario_id, {})

        visibility = manifest_entry.get("visibility", "public")
        action = _determine_action(visibility, scenario)

        failures.append(
            ReworkFailure(
                scenario_id=scenario_id,
                visibility=visibility,
                requirement_refs=scenario.get("requirement_refs", []),
                implicated_interfaces=scenario.get("interfaces_tested", []),
                implicated_files=scenario.get("implicated_files", []),
                likely_owner=scenario.get("likely_owner", ""),
                recommended_action=action,
            )
        )

    return ReworkReport(failures=failures)


def write_rework_report(report: ReworkReport, path: Path) -> None:
    """Write rework report as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)


def load_rework_report(path: Path) -> ReworkReport:
    """Load a rework report from JSON.

    Args:
        path: Path to rework-report.json.

    Returns:
        Parsed ReworkReport.

    Raises:
        FileNotFoundError: If file doesn't exist.
        ValueError: If JSON is malformed.
    """
    if not path.exists():
        raise FileNotFoundError(f"Rework report not found: {path}")

    with open(path) as f:
        data = json.load(f)

    failures = []
    for f_data in data.get("failures", []):
        if not isinstance(f_data, dict):
            logger.warning("Skipping malformed failure entry: %s", f_data)
            continue
        failures.append(
            ReworkFailure(
                scenario_id=f_data.get("scenario_id", "unknown"),
                visibility=f_data.get("visibility", "public"),
                requirement_refs=f_data.get("requirement_refs", []),
                implicated_interfaces=f_data.get("implicated_interfaces", []),
                implicated_files=f_data.get("implicated_files", []),
                likely_owner=f_data.get("likely_owner", ""),
                recommended_action=f_data.get("recommended_action", ACTION_ITERATE),
            )
        )

    return ReworkReport(failures=failures)


def check_holdout_gate(report: ReworkReport) -> tuple[str, str]:
    """Check whether holdout failures block cleanup/merge.

    Returns:
        Tuple of (action, reason). action is 'continue' or 'halt'.
    """
    if not report.failures:
        return ("continue", "No scenario failures. Rework report clean.")

    if report.has_blocking_holdout:
        holdout_ids = [
            f.scenario_id
            for f in report.failures
            if f.visibility == "holdout" and f.recommended_action == ACTION_BLOCK_CLEANUP
        ]
        return (
            "halt",
            f"Holdout scenario failures block cleanup: {', '.join(holdout_ids)}",
        )

    return (
        "continue",
        f"{report.total_failures} failure(s) found but none block cleanup.",
    )


def _determine_action(visibility: str, scenario: dict[str, Any]) -> str:
    """Determine the recommended rework action for a failure."""
    if visibility == "holdout":
        return ACTION_BLOCK_CLEANUP
    # Public failures are iterative by default
    return ACTION_ITERATE

"""Project ranked capability gaps into canonical candidate-work stubs."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from candidate_work import derive_suggested_change_id, write_candidate_work

_PRIORITY = {"critical": 1, "high": 2, "medium": 3, "low": 4}


def _entry_ids(finding: dict[str, Any]) -> list[str]:
    return [
        str(entry["id"])
        for entry in finding.get("entries", [])
        if isinstance(entry, dict) and entry.get("id")
    ]


def _effort(finding: dict[str, Any]) -> tuple[str, bool]:
    skills = finding.get("affected_skills")
    if skills is None:
        return "M", True
    count = len(skills)
    if count == 1:
        return "S", False
    if count in {2, 3}:
        return "M", False
    if count >= 4:
        return "L", False
    return "M", True


def project_candidate_work(
    ranked: list[dict[str, Any]], source_artifact: str
) -> list[dict[str, Any]]:
    """Convert ranked gaps without using mutable rank or report text for IDs."""
    candidates: list[dict[str, Any]] = []
    for rank, finding in enumerate(ranked, 1):
        gap = str(finding["capability_gap"])
        effort, defaulted = _effort(finding)
        severity = str(finding.get("max_severity", "low"))
        tags = [f"source-rank-{min(rank, 99)}"]
        if defaulted:
            tags.append("effort-estimate-default")
        candidates.append(
            {
                "schema_version": 1,
                "title": gap,
                "description": f"Improve the harness capability: {gap}.",
                "rationale": (
                    f"Observed {finding.get('frequency', 0)} occurrence(s), with "
                    f"maximum severity {severity}."
                ),
                "provenance": {
                    "source_artifact": source_artifact,
                    "finding_ids": _entry_ids(finding),
                    "generator": "improve-harness",
                },
                "effort": effort,
                "priority": _PRIORITY[severity],
                "suggested_change_id": derive_suggested_change_id(
                    "improve-harness", gap, finding.get("suggested_change_id")
                ),
                "tags": tags,
            }
        )
    return candidates


def write_projection(
    ranked: list[dict[str, Any]], destination: Path, source_artifact: str
) -> Path:
    """Validate the complete projection, then atomically replace its sidecar."""
    return write_candidate_work(
        destination,
        project_candidate_work(ranked, source_artifact),
        generator="improve-harness",
    )

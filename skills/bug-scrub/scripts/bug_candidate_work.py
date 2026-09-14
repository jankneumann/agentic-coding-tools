"""Project bug-scrub findings into canonical candidate-work stubs."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from candidate_work import derive_suggested_change_id, write_candidate_work
from models import BugScrubReport, Finding

_PRIORITY = {"critical": 1, "high": 2, "medium": 3, "low": 4, "info": 5}
_EFFORT = {
    "lint": "XS",
    "type-error": "XS",
    "code-marker": "XS",
    "test-failure": "S",
    "deferred-issue": "S",
    "architecture": "M",
    "security": "M",
    "spec-violation": "M",
}


def _candidate(finding: Finding, source_artifact: str) -> dict[str, Any]:
    try:
        effort = _EFFORT[finding.category]
    except KeyError as exc:
        raise ValueError(
            f"unsupported bug-scrub category: {finding.category!r}"
        ) from exc
    detail = finding.detail.strip() or (
        f"Resolve the {finding.category} finding reported by {finding.source}."
    )
    location = finding.file_path or "the project"
    return {
        "schema_version": 1,
        "title": finding.title,
        "description": detail,
        "rationale": (
            f"Bug-scrub classified finding {finding.id} as {finding.severity} "
            f"at {location}."
        ),
        "provenance": {
            "source_artifact": source_artifact,
            "finding_ids": [finding.id],
            "generator": "bug-scrub",
        },
        "effort": effort,
        "priority": _PRIORITY[finding.severity],
        "suggested_change_id": derive_suggested_change_id(
            "bug-scrub", finding.id
        ),
        "tags": [finding.category, f"severity-{finding.severity}"],
    }


def project_candidate_work(
    report: BugScrubReport, source_artifact: str
) -> list[dict[str, Any]]:
    """Return one candidate for every finding retained in the rich report."""
    return [_candidate(finding, source_artifact) for finding in report.findings]


def write_projection(
    report: BugScrubReport, destination: Path, source_artifact: str
) -> Path:
    """Validate the complete projection, then atomically replace its sidecar."""
    return write_candidate_work(
        destination,
        project_candidate_work(report, source_artifact),
        generator="bug-scrub",
    )

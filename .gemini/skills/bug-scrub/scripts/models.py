#!/usr/bin/env python3
"""Shared data models for bug-scrub and fix-scrub skills.

These models define the unified finding schema consumed by both skills.
fix-scrub imports from this module via sys.path insertion.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Severity = Literal["critical", "high", "medium", "low", "info"]
Category = Literal[
    "test-failure",
    "lint",
    "type-error",
    "spec-violation",
    "architecture",
    "security",
    "deferred-issue",
    "code-marker",
]

SEVERITY_ORDER: dict[str, int] = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def severity_rank(severity: str) -> int:
    """Return sortable severity rank; unknown severities map to info (0)."""
    return SEVERITY_ORDER.get(severity.lower(), 0)


@dataclass(slots=True)
class FindingOrigin:
    """Provenance metadata for findings harvested from OpenSpec artifacts.

    Carries enough info for fix-scrub to locate and update the source.
    """

    change_id: str
    artifact_path: str
    task_number: str | None = None
    line_in_artifact: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Finding:
    """Canonical finding representation across all signal sources."""

    id: str
    source: str
    severity: Severity
    category: Category
    title: str
    detail: str = ""
    file_path: str = ""
    line: int | None = None
    age_days: int | None = None
    origin: FindingOrigin | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.origin is not None:
            data["origin"] = self.origin.to_dict()
        else:
            data["origin"] = None
        return data


@dataclass(slots=True)
class SourceResult:
    """Normalized result from a single signal source."""

    source: str
    status: Literal["ok", "skipped", "error"]
    findings: list[Finding] = field(default_factory=list)
    duration_ms: int = 0
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "source": self.source,
            "status": self.status,
            "findings": [f.to_dict() for f in self.findings],
            "duration_ms": self.duration_ms,
            "messages": self.messages,
        }
        return data


@dataclass(slots=True)
class BugScrubReport:
    """Aggregated bug-scrub report output."""

    timestamp: str
    sources_used: list[str]
    severity_filter: str
    findings: list[Finding] = field(default_factory=list)
    filtered_out_count: int = 0
    staleness_warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    source_results: list[SourceResult] = field(default_factory=list)

    def summary_by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts

    def summary_by_source(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.source] = counts.get(f.source, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "sources_used": self.sources_used,
            "severity_filter": self.severity_filter,
            "findings": [f.to_dict() for f in self.findings],
            "filtered_out_count": self.filtered_out_count,
            "staleness_warnings": self.staleness_warnings,
            "recommendations": self.recommendations,
            "source_results": [sr.to_dict() for sr in self.source_results],
            "summary": {
                "by_severity": self.summary_by_severity(),
                "by_source": self.summary_by_source(),
                "total": len(self.findings),
            },
        }

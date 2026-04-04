#!/usr/bin/env python3
"""Shared data models for the tech-debt-analysis skill.

Defines a unified finding schema inspired by Martin Fowler's refactoring
catalog and the AWS Builders' Library principle of minimizing blast radius.

Debt categories map to well-known code smells:
- **long-method**: Functions exceeding a complexity/size threshold (Fowler: Long Method)
- **large-file**: Modules with too many responsibilities (Fowler: Large Class / God Class)
- **complex-function**: High cyclomatic complexity (McCabe metric)
- **high-coupling**: Modules with excessive fan-in/fan-out (AWS: blast radius)
- **deep-nesting**: Deeply nested control flow (readability / cognitive complexity)
- **duplicate-code**: Near-duplicate logic across files (Fowler: Duplicated Code)
- **import-complexity**: Circular or overly tangled import graphs
- **parameter-excess**: Functions taking too many parameters (Fowler: Long Parameter List)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Severity = Literal["critical", "high", "medium", "low", "info"]
DebtCategory = Literal[
    "long-method",
    "large-file",
    "complex-function",
    "high-coupling",
    "deep-nesting",
    "duplicate-code",
    "import-complexity",
    "parameter-excess",
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
class TechDebtFinding:
    """A single tech-debt finding with location, metrics, and remediation hint."""

    id: str
    analyzer: str
    severity: Severity
    category: DebtCategory
    title: str
    detail: str = ""
    file_path: str = ""
    line: int | None = None
    end_line: int | None = None
    metric_name: str = ""
    metric_value: float = 0.0
    threshold: float = 0.0
    smell: str = ""
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AnalyzerResult:
    """Normalized result from a single analyzer pass."""

    analyzer: str
    status: Literal["ok", "skipped", "error"]
    findings: list[TechDebtFinding] = field(default_factory=list)
    duration_ms: int = 0
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "analyzer": self.analyzer,
            "status": self.status,
            "findings": [f.to_dict() for f in self.findings],
            "duration_ms": self.duration_ms,
            "messages": self.messages,
        }


@dataclass(slots=True)
class TechDebtReport:
    """Aggregated tech-debt analysis report."""

    timestamp: str
    analyzers_used: list[str]
    severity_filter: str
    findings: list[TechDebtFinding] = field(default_factory=list)
    filtered_out_count: int = 0
    recommendations: list[str] = field(default_factory=list)
    analyzer_results: list[AnalyzerResult] = field(default_factory=list)

    # ── Summary helpers ──────────────────────────────────────────────

    def summary_by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts

    def summary_by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.category] = counts.get(f.category, 0) + 1
        return counts

    def summary_by_analyzer(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.analyzer] = counts.get(f.analyzer, 0) + 1
        return counts

    def hotspot_files(self, top_n: int = 10) -> list[tuple[str, int]]:
        """Return the top-N files with the most findings (hotspots)."""
        counts: dict[str, int] = {}
        for f in self.findings:
            if f.file_path:
                counts[f.file_path] = counts.get(f.file_path, 0) + 1
        return sorted(counts.items(), key=lambda x: -x[1])[:top_n]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "analyzers_used": self.analyzers_used,
            "severity_filter": self.severity_filter,
            "findings": [f.to_dict() for f in self.findings],
            "filtered_out_count": self.filtered_out_count,
            "recommendations": self.recommendations,
            "analyzer_results": [ar.to_dict() for ar in self.analyzer_results],
            "summary": {
                "by_severity": self.summary_by_severity(),
                "by_category": self.summary_by_category(),
                "by_analyzer": self.summary_by_analyzer(),
                "hotspot_files": self.hotspot_files(),
                "total": len(self.findings),
            },
        }

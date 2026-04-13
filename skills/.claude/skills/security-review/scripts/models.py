#!/usr/bin/env python3
"""Shared data models for security-review scripts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Severity = Literal["info", "low", "medium", "high", "critical"]
ScannerStatus = Literal["ok", "skipped", "unavailable", "error"]
GateDecision = Literal["PASS", "FAIL", "INCONCLUSIVE"]


@dataclass(slots=True)
class Finding:
    """Canonical finding representation across scanners."""

    scanner: str
    finding_id: str
    title: str
    severity: Severity
    description: str = ""
    location: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScannerResult:
    """Normalized scanner execution result."""

    scanner: str
    status: ScannerStatus
    findings: list[Finding] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["findings"] = [finding.to_dict() for finding in self.findings]
        return data


@dataclass(slots=True)
class GateResult:
    """Gate decision output for risk thresholds."""

    decision: GateDecision
    fail_on: Severity
    triggered_count: int
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def severity_rank(severity: str) -> int:
    """Return sortable severity rank; unknown severities map to info."""
    order = {
        "info": 0,
        "low": 1,
        "medium": 2,
        "high": 3,
        "critical": 4,
    }
    return order.get(severity.lower(), 0)


def normalize_severity(value: str | None) -> Severity:
    """Normalize scanner severity values into canonical levels."""
    if not value:
        return "info"
    cleaned = value.strip().lower()
    mapping = {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "moderate": "medium",
        "med": "medium",
        "low": "low",
        "info": "info",
        "informational": "info",
        "none": "info",
    }
    return mapping.get(cleaned, "info")

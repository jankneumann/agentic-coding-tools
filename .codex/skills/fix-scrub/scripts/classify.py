#!/usr/bin/env python3
"""Finding fixability classifier: assign each finding to auto/agent/manual tier."""

from __future__ import annotations

import sys
from pathlib import Path

# Add fix-scrub scripts to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fix_models import ClassifiedFinding, Finding, FixTier, severity_rank  # noqa: E402

# Ruff rules known to support --fix
_RUFF_FIXABLE_PREFIXES = {
    "F", "E", "W", "I", "UP", "B", "SIM", "RUF",
    "D", "C4", "PT", "RSE", "RET", "TCH", "TID",
}


def _is_ruff_fixable(finding: Finding) -> bool:
    """Check if a ruff finding's rule likely supports --fix."""
    # Extract rule code from finding ID (e.g., "ruff-E501-file.py:10")
    parts = finding.id.split("-", 2)
    if len(parts) >= 2:
        code = parts[1]
        for prefix in _RUFF_FIXABLE_PREFIXES:
            if code.startswith(prefix):
                return True
    return False


def _marker_has_sufficient_context(finding: Finding) -> bool:
    """Check if a marker finding has >=10 chars after the keyword."""
    detail = finding.detail.strip()
    # The detail should be the text after the marker keyword (TODO:, FIXME:, etc.)
    # Strip leading colon/whitespace
    for prefix in (":", " "):
        if detail.startswith(prefix):
            detail = detail[len(prefix):]
    return len(detail.strip()) >= 10


def _deferred_has_proposed_fix(finding: Finding) -> bool:
    """Check if a deferred finding has a non-empty proposed fix."""
    detail_lower = finding.detail.lower()
    return "proposed fix" in detail_lower or "resolution" in detail_lower


def classify_finding(finding: Finding) -> ClassifiedFinding:
    """Classify a single finding into a fixability tier."""
    source = finding.source
    category = finding.category

    # Auto tier: ruff with fixable rules
    if source == "ruff" and _is_ruff_fixable(finding):
        return ClassifiedFinding(
            finding=finding,
            tier="auto",
            fix_strategy="ruff check --fix",
        )

    # Agent tier: mypy type errors
    if source == "mypy":
        return ClassifiedFinding(
            finding=finding,
            tier="agent",
            fix_strategy="Add or fix type annotations",
        )

    # Agent tier: markers with sufficient context
    if source == "markers" and _marker_has_sufficient_context(finding):
        return ClassifiedFinding(
            finding=finding,
            tier="agent",
            fix_strategy="Resolve marker based on context",
        )

    # Agent tier: deferred with proposed fix
    if source.startswith("deferred:") and _deferred_has_proposed_fix(finding):
        return ClassifiedFinding(
            finding=finding,
            tier="agent",
            fix_strategy="Apply proposed fix from deferred finding",
        )

    # Manual tier: markers with insufficient context
    if source == "markers":
        return ClassifiedFinding(
            finding=finding,
            tier="manual",
            fix_strategy="Insufficient context for automated fix",
        )

    # Manual tier: architecture, security, deferred without fix
    if source in ("architecture", "security") or category in (
        "architecture",
        "security",
    ):
        return ClassifiedFinding(
            finding=finding,
            tier="manual",
            fix_strategy="Requires design decision or manual review",
        )

    if source.startswith("deferred:"):
        return ClassifiedFinding(
            finding=finding,
            tier="manual",
            fix_strategy="No clear proposed fix — requires investigation",
        )

    # Default: manual for unknown sources
    return ClassifiedFinding(
        finding=finding,
        tier="manual",
        fix_strategy="Unknown source — manual review required",
    )


def classify(
    findings: list[Finding],
    severity_filter: str = "medium",
) -> list[ClassifiedFinding]:
    """Classify all findings into fixability tiers.

    Args:
        findings: List of findings from bug-scrub report.
        severity_filter: Minimum severity to include.

    Returns:
        List of classified findings.
    """
    min_rank = severity_rank(severity_filter)
    classified: list[ClassifiedFinding] = []
    for f in findings:
        if severity_rank(f.severity) >= min_rank:
            classified.append(classify_finding(f))
    return classified

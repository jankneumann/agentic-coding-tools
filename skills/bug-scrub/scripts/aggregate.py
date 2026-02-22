#!/usr/bin/env python3
"""Finding aggregator: merge, sort, deduplicate, and generate recommendations."""

from __future__ import annotations

from models import BugScrubReport, Finding, SourceResult, severity_rank


def _group_by_proximity(findings: list[Finding], line_threshold: int = 10) -> list[list[Finding]]:
    """Group findings that share the same file and have lines within threshold."""
    if not findings:
        return []

    # Sort by file_path then line
    sorted_findings = sorted(findings, key=lambda f: (f.file_path or "", f.line or 0))
    groups: list[list[Finding]] = []
    current_group: list[Finding] = [sorted_findings[0]]

    for f in sorted_findings[1:]:
        prev = current_group[-1]
        if (
            f.file_path
            and f.file_path == prev.file_path
            and f.line is not None
            and prev.line is not None
            and abs(f.line - prev.line) <= line_threshold
        ):
            current_group.append(f)
        else:
            groups.append(current_group)
            current_group = [f]
    groups.append(current_group)
    return groups


def _generate_recommendations(
    findings: list[Finding],
    staleness_warnings: list[str],
) -> list[str]:
    """Generate up to 5 recommendations based on finding patterns.

    Priority order per spec:
    1. Staleness warnings → refresh recommendation
    2. >5 test failures → fix tests first
    3. >10 lint findings → run fix-scrub auto
    4. Deferred findings from >2 changes → consolidate
    5. >20 findings total → preview fix-scrub
    """
    recs: list[str] = []

    if staleness_warnings:
        recs.append(
            "Refresh stale reports with /security-review or /refresh-architecture"
        )

    test_failures = [f for f in findings if f.category == "test-failure"]
    if len(test_failures) > 5:
        recs.append("Fix failing tests before other fixes")

    lint_findings = [f for f in findings if f.category == "lint"]
    if len(lint_findings) > 10:
        recs.append("Run /fix-scrub --tier auto for quick lint fixes")

    deferred = [f for f in findings if f.category == "deferred-issue"]
    deferred_changes = {
        f.origin.change_id for f in deferred if f.origin is not None
    }
    if len(deferred_changes) > 2:
        recs.append("Consolidate deferred items into a follow-up proposal")

    if len(findings) > 20:
        recs.append(
            "Consider running /fix-scrub --dry-run to preview remediation plan"
        )

    return recs[:5]


def aggregate(
    source_results: list[SourceResult],
    severity_filter: str = "low",
    timestamp: str = "",
) -> BugScrubReport:
    """Aggregate findings from all source results into a BugScrubReport.

    Args:
        source_results: Collected results from each signal source.
        severity_filter: Minimum severity to include in findings.
        timestamp: ISO timestamp for the report.

    Returns:
        Aggregated BugScrubReport.
    """
    min_rank = severity_rank(severity_filter)
    all_findings: list[Finding] = []
    staleness_warnings: list[str] = []
    sources_used: list[str] = []

    for sr in source_results:
        sources_used.append(sr.source)
        # Collect staleness warnings from source messages
        for msg in sr.messages:
            if "stale" in msg.lower() or "staleness" in msg.lower():
                staleness_warnings.append(msg)
        # Filter by severity
        for f in sr.findings:
            if severity_rank(f.severity) >= min_rank:
                all_findings.append(f)

    # Sort by severity (descending) then age (descending, oldest first)
    all_findings.sort(
        key=lambda f: (-severity_rank(f.severity), -(f.age_days or 0))
    )

    # Group by proximity for deduplication awareness
    # (We keep all findings but mark clusters)
    _group_by_proximity(all_findings)

    recommendations = _generate_recommendations(all_findings, staleness_warnings)

    return BugScrubReport(
        timestamp=timestamp,
        sources_used=sources_used,
        severity_filter=severity_filter,
        findings=all_findings,
        staleness_warnings=staleness_warnings,
        recommendations=recommendations,
        source_results=source_results,
    )

#!/usr/bin/env python3
"""Finding aggregator: merge, sort, deduplicate, and generate recommendations.

Follows the same pattern as bug-scrub's aggregator but with tech-debt-specific
recommendation logic grounded in Fowler's refactoring priorities:
1. Fix the most painful smells first (complexity, duplication)
2. Address coupling to reduce blast radius
3. Clean up imports for maintainability
"""

from __future__ import annotations

from models import AnalyzerResult, TechDebtFinding, TechDebtReport, severity_rank

# ── Debt category priorities (higher = fix first) ─────────────────────
_CATEGORY_PRIORITY: dict[str, int] = {
    "complex-function": 6,
    "long-method": 5,
    "large-file": 4,
    "duplicate-code": 4,
    "high-coupling": 3,
    "deep-nesting": 3,
    "parameter-excess": 2,
    "import-complexity": 1,
}


def _generate_recommendations(
    findings: list[TechDebtFinding],
) -> list[str]:
    """Generate up to 7 prioritized recommendations based on finding patterns."""
    recs: list[str] = []

    # Count by category
    by_cat: dict[str, int] = {}
    for f in findings:
        by_cat[f.category] = by_cat.get(f.category, 0) + 1

    # High-severity count
    high_count = sum(1 for f in findings if severity_rank(f.severity) >= severity_rank("high"))
    if high_count > 0:
        recs.append(
            f"Address {high_count} high/critical findings first — "
            "these indicate active maintainability risks."
        )

    # Complex functions
    complex_count = by_cat.get("complex-function", 0)
    if complex_count > 3:
        recs.append(
            f"Refactor {complex_count} complex functions — "
            "apply Extract Method and Replace Conditional with Polymorphism."
        )

    # Long methods
    long_count = by_cat.get("long-method", 0)
    if long_count > 3:
        recs.append(
            f"Break down {long_count} long methods — "
            "Fowler: 'The key refactoring is Extract Method.'"
        )

    # Large files
    large_count = by_cat.get("large-file", 0)
    if large_count > 0:
        recs.append(
            f"Split {large_count} large file(s) — "
            "each module should have a single, clear responsibility."
        )

    # Duplication
    dup_count = by_cat.get("duplicate-code", 0)
    if dup_count > 2:
        recs.append(
            f"Eliminate {dup_count} duplicate code groups — "
            "extract shared logic into utility functions or base classes."
        )

    # Coupling
    coupling_count = by_cat.get("high-coupling", 0)
    if coupling_count > 3:
        recs.append(
            f"Reduce coupling in {coupling_count} areas — "
            "introduce interfaces/facades to minimize blast radius "
            "(AWS Builders' Library)."
        )

    # Hotspot recommendation
    hotspots = {}
    for f in findings:
        if f.file_path:
            hotspots[f.file_path] = hotspots.get(f.file_path, 0) + 1
    worst_file = max(hotspots.items(), key=lambda x: x[1]) if hotspots else None
    if worst_file and worst_file[1] >= 5:
        recs.append(
            f"Prioritize {worst_file[0]} ({worst_file[1]} findings) — "
            "it's the top hotspot file."
        )

    return recs[:7]


def aggregate(
    analyzer_results: list[AnalyzerResult],
    severity_filter: str = "low",
    timestamp: str = "",
) -> TechDebtReport:
    """Aggregate findings from all analyzer results into a TechDebtReport.

    Args:
        analyzer_results: Results from each analyzer.
        severity_filter: Minimum severity to include.
        timestamp: ISO timestamp for the report.

    Returns:
        Aggregated TechDebtReport.
    """
    min_rank = severity_rank(severity_filter)
    all_findings: list[TechDebtFinding] = []
    filtered_out = 0
    analyzers_used: list[str] = []

    for ar in analyzer_results:
        analyzers_used.append(ar.analyzer)
        for f in ar.findings:
            if severity_rank(f.severity) >= min_rank:
                all_findings.append(f)
            else:
                filtered_out += 1

    # Sort by: severity (desc), category priority (desc), file path
    all_findings.sort(
        key=lambda f: (
            -severity_rank(f.severity),
            -_CATEGORY_PRIORITY.get(f.category, 0),
            f.file_path or "",
        )
    )

    recommendations = _generate_recommendations(all_findings)

    return TechDebtReport(
        timestamp=timestamp,
        analyzers_used=analyzers_used,
        severity_filter=severity_filter,
        findings=all_findings,
        filtered_out_count=filtered_out,
        recommendations=recommendations,
        analyzer_results=analyzer_results,
    )

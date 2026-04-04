#!/usr/bin/env python3
"""Report renderer: produce markdown and JSON outputs from TechDebtReport.

The markdown report is structured for quick triage:
1. Executive summary with severity breakdown
2. Hotspot files (most findings)
3. Critical/High findings with full detail and recommendations
4. Medium findings in table format
5. Category breakdown with refactoring guidance
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from models import TechDebtReport, severity_rank

# ── Smell reference links ─────────────────────────────────────────────
_SMELL_REFERENCES: dict[str, str] = {
    "Long Method": "Fowler: Extract Method",
    "Large Class / God File": "Fowler: Extract Class, Move Method",
    "Complex Function": "Fowler: Replace Conditional with Polymorphism",
    "Deep Nesting": "Fowler: Decompose Conditional, Guard Clauses",
    "Long Parameter List": "Fowler: Introduce Parameter Object",
    "Duplicated Code": "Fowler: Extract Method, Pull Up Method",
    "Shotgun Surgery / Feature Envy": "Fowler: Move Method, Inline Class",
    "Change Amplifier": "Stabilize interfaces, version APIs",
    "God Object / Blob": "Fowler: Extract Class, SRP",
    "Circular Dependency": "Extract shared types, lazy imports",
    "Divergent Change": "Fowler: Extract Class (split responsibilities)",
    "Namespace Pollution": "Use explicit named imports",
    "High Blast Radius (AWS Builders' Library)": "Isolate, version, test thoroughly",
}


def render_markdown(report: TechDebtReport) -> str:
    """Render TechDebtReport as markdown."""
    lines: list[str] = []

    # ── Header ────────────────────────────────────────────────────
    lines.append("# Tech Debt Analysis Report")
    lines.append("")
    lines.append(f"**Timestamp**: {report.timestamp}")
    lines.append(f"**Analyzers**: {', '.join(report.analyzers_used)}")
    lines.append(f"**Severity filter**: {report.severity_filter}")
    lines.append(f"**Total findings**: {len(report.findings)}")
    if report.filtered_out_count > 0:
        lines.append(
            f"**Filtered out**: {report.filtered_out_count} findings "
            f"below '{report.severity_filter}' severity"
        )
    lines.append("")

    # ── Summary tables ────────────────────────────────────────────
    by_severity = report.summary_by_severity()
    by_category = report.summary_by_category()

    lines.append("## Summary")
    lines.append("")

    lines.append("### By Severity")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    for sev in ["critical", "high", "medium", "low", "info"]:
        count = by_severity.get(sev, 0)
        if count > 0:
            lines.append(f"| {sev} | {count} |")
    lines.append("")

    lines.append("### By Category (Code Smell)")
    lines.append("")
    lines.append("| Category | Count | Refactoring Reference |")
    lines.append("|----------|-------|-----------------------|")
    for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
        # Map category to a reference
        ref = ""
        if cat == "long-method":
            ref = "Fowler: Extract Method"
        elif cat == "large-file":
            ref = "Fowler: Extract Class / Move Method"
        elif cat == "complex-function":
            ref = "Fowler: Decompose Conditional"
        elif cat == "high-coupling":
            ref = "AWS Builders' Library: Minimize Blast Radius"
        elif cat == "deep-nesting":
            ref = "Fowler: Guard Clauses"
        elif cat == "duplicate-code":
            ref = "Fowler: Extract Method / Pull Up Method"
        elif cat == "import-complexity":
            ref = "Extract shared types module"
        elif cat == "parameter-excess":
            ref = "Fowler: Introduce Parameter Object"
        lines.append(f"| {cat} | {count} | {ref} |")
    lines.append("")

    # ── Hotspot files ─────────────────────────────────────────────
    hotspots = report.hotspot_files(top_n=10)
    if hotspots:
        lines.append("### Hotspot Files (most findings)")
        lines.append("")
        lines.append("| File | Findings |")
        lines.append("|------|----------|")
        for file_path, count in hotspots:
            lines.append(f"| {file_path} | {count} |")
        lines.append("")

    # ── Critical / High findings ──────────────────────────────────
    critical_high = [
        f for f in report.findings
        if severity_rank(f.severity) >= severity_rank("high")
    ]
    if critical_high:
        lines.append("## Critical / High Findings")
        lines.append("")
        for f in critical_high:
            loc = f"{f.file_path}:{f.line}" if f.file_path and f.line else f.file_path or "N/A"
            lines.append(f"### [{f.severity.upper()}] {f.title}")
            lines.append("")
            lines.append(f"- **Category**: {f.category}")
            lines.append(f"- **Location**: `{loc}`")
            if f.end_line:
                lines.append(f"- **Span**: lines {f.line}-{f.end_line}")
            lines.append(f"- **Metric**: {f.metric_name} = {f.metric_value} (threshold: {f.threshold})")
            if f.smell:
                ref = _SMELL_REFERENCES.get(f.smell, "")
                smell_str = f"{f.smell}"
                if ref:
                    smell_str += f" — {ref}"
                lines.append(f"- **Smell**: {smell_str}")
            if f.detail:
                lines.append(f"- **Detail**: {f.detail}")
            if f.recommendation:
                lines.append(f"- **Recommendation**: {f.recommendation}")
            lines.append("")

    # ── Medium findings ───────────────────────────────────────────
    medium = [f for f in report.findings if f.severity == "medium"]
    if medium:
        lines.append("## Medium Findings")
        lines.append("")
        lines.append("| Category | Location | Title | Metric |")
        lines.append("|----------|----------|-------|--------|")
        for f in medium:
            loc = f"{f.file_path}:{f.line}" if f.file_path and f.line else f.file_path or "N/A"
            metric = f"{f.metric_name}={f.metric_value}" if f.metric_name else ""
            lines.append(f"| {f.category} | `{loc}` | {f.title} | {metric} |")
        lines.append("")

    # ── Low / Info ────────────────────────────────────────────────
    low_info = [
        f for f in report.findings
        if severity_rank(f.severity) < severity_rank("medium")
    ]
    if low_info:
        lines.append("## Low / Info Findings")
        lines.append("")
        low_count = sum(1 for f in low_info if f.severity == "low")
        info_count = sum(1 for f in low_info if f.severity == "info")
        if low_count:
            lines.append(f"- **Low**: {low_count} findings")
        if info_count:
            lines.append(f"- **Info**: {info_count} findings")
        lines.append("")
        lines.append("_(See JSON report for full details)_")
        lines.append("")

    # ── Recommendations ───────────────────────────────────────────
    if report.recommendations:
        lines.append("## Recommendations")
        lines.append("")
        for i, rec in enumerate(report.recommendations, 1):
            lines.append(f"{i}. {rec}")
        lines.append("")

    # ── Analyzer performance ──────────────────────────────────────
    if report.analyzer_results:
        lines.append("## Analyzer Performance")
        lines.append("")
        lines.append("| Analyzer | Status | Findings | Duration |")
        lines.append("|----------|--------|----------|----------|")
        for ar in report.analyzer_results:
            lines.append(
                f"| {ar.analyzer} | {ar.status} | {len(ar.findings)} | {ar.duration_ms}ms |"
            )
        lines.append("")

    # ── Empty report ──────────────────────────────────────────────
    if not report.findings:
        lines.append("## Result")
        lines.append("")
        lines.append(
            "No tech debt findings above the severity threshold. "
            "The codebase is in good shape!"
        )
        lines.append("")

    return "\n".join(lines)


def render_json(report: TechDebtReport) -> str:
    """Render TechDebtReport as JSON."""
    return json.dumps(report.to_dict(), indent=2)


def write_report(
    report: TechDebtReport,
    out_dir: str,
    fmt: str = "both",
) -> list[str]:
    """Write report files.

    Args:
        report: The aggregated report.
        out_dir: Output directory path.
        fmt: "md", "json", or "both".

    Returns:
        List of file paths written.
    """
    os.makedirs(out_dir, exist_ok=True)
    written: list[str] = []

    if fmt in ("md", "both"):
        md_path = str(Path(out_dir) / "tech-debt-report.md")
        with open(md_path, "w") as f:
            f.write(render_markdown(report))
        written.append(md_path)

    if fmt in ("json", "both"):
        json_path = str(Path(out_dir) / "tech-debt-report.json")
        with open(json_path, "w") as f:
            f.write(render_json(report))
        written.append(json_path)

    return written

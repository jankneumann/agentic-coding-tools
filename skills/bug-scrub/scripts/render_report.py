#!/usr/bin/env python3
"""Report renderer: produce markdown and JSON outputs from BugScrubReport."""

from __future__ import annotations

import json
import os
from pathlib import Path

from models import BugScrubReport, severity_rank


def render_markdown(report: BugScrubReport) -> str:
    """Render BugScrubReport as markdown."""
    lines: list[str] = []

    # Header
    lines.append("# Bug Scrub Report")
    lines.append("")
    lines.append(f"**Timestamp**: {report.timestamp}")
    lines.append(f"**Sources**: {', '.join(report.sources_used)}")
    lines.append(f"**Severity filter**: {report.severity_filter}")
    lines.append(f"**Total findings**: {len(report.findings)}")
    lines.append("")

    # Summary table
    by_severity = report.summary_by_severity()
    by_source = report.summary_by_source()

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

    lines.append("### By Source")
    lines.append("")
    lines.append("| Source | Count |")
    lines.append("|--------|-------|")
    for source, count in sorted(by_source.items()):
        lines.append(f"| {source} | {count} |")
    lines.append("")

    # Critical/High findings — full detail
    critical_high = [
        f for f in report.findings if severity_rank(f.severity) >= severity_rank("high")
    ]
    if critical_high:
        lines.append("## Critical / High Findings")
        lines.append("")
        for f in critical_high:
            loc = f"{f.file_path}:{f.line}" if f.file_path and f.line else f.file_path or "N/A"
            lines.append(f"### [{f.severity.upper()}] {f.title}")
            lines.append("")
            lines.append(f"- **Source**: {f.source}")
            lines.append(f"- **Category**: {f.category}")
            lines.append(f"- **Location**: {loc}")
            if f.age_days is not None:
                lines.append(f"- **Age**: {f.age_days} days")
            if f.detail:
                lines.append(f"- **Detail**: {f.detail}")
            lines.append("")

    # Medium findings — condensed
    medium = [f for f in report.findings if f.severity == "medium"]
    if medium:
        lines.append("## Medium Findings")
        lines.append("")
        lines.append("| Source | Location | Title |")
        lines.append("|--------|----------|-------|")
        for f in medium:
            loc = f"{f.file_path}:{f.line}" if f.file_path and f.line else f.file_path or "N/A"
            lines.append(f"| {f.source} | {loc} | {f.title} |")
        lines.append("")

    # Low/Info — counts only
    low_info = [
        f for f in report.findings if severity_rank(f.severity) < severity_rank("medium")
    ]
    if low_info:
        lines.append("## Low / Info Findings")
        lines.append("")
        low_count = sum(1 for f in low_info if f.severity == "low")
        info_count = sum(1 for f in low_info if f.severity == "info")
        lines.append(f"- **Low**: {low_count} findings")
        lines.append(f"- **Info**: {info_count} findings")
        lines.append("")
        lines.append("_(See JSON report for full details)_")
        lines.append("")

    # Staleness warnings
    if report.staleness_warnings:
        lines.append("## Staleness Warnings")
        lines.append("")
        for w in report.staleness_warnings:
            lines.append(f"- {w}")
        lines.append("")

    # Recommendations
    if report.recommendations:
        lines.append("## Recommendations")
        lines.append("")
        for i, rec in enumerate(report.recommendations, 1):
            lines.append(f"{i}. {rec}")
        lines.append("")

    # Empty report
    if not report.findings:
        if not report.staleness_warnings:
            lines.append("## Result")
            lines.append("")
            lines.append("Clean bill of health — no findings discovered.")
            lines.append("")
        else:
            lines.append("## Result")
            lines.append("")
            lines.append("No findings at or above the severity threshold.")
            lines.append("")

    return "\n".join(lines)


def render_json(report: BugScrubReport) -> str:
    """Render BugScrubReport as JSON."""
    return json.dumps(report.to_dict(), indent=2)


def write_report(
    report: BugScrubReport,
    out_dir: str,
    fmt: str = "both",
) -> list[str]:
    """Write report to files.

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
        md_path = str(Path(out_dir) / "bug-scrub-report.md")
        with open(md_path, "w") as f:
            f.write(render_markdown(report))
        written.append(md_path)

    if fmt in ("json", "both"):
        json_path = str(Path(out_dir) / "bug-scrub-report.json")
        with open(json_path, "w") as f:
            f.write(render_json(report))
        written.append(json_path)

    return written

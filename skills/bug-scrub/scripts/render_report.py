#!/usr/bin/env python3
"""Report renderer: produce markdown and JSON outputs from BugScrubReport."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
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
    if report.filtered_out_count > 0:
        lines.append(f"**Filtered out**: {report.filtered_out_count} findings below '{report.severity_filter}' severity")
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


def _report_date(timestamp: str) -> str:
    """Return the UTC calendar date encoded by a report timestamp."""
    try:
        generated_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid bug-scrub report timestamp: {timestamp!r}") from exc

    if generated_at.tzinfo is not None:
        generated_at = generated_at.astimezone(timezone.utc)
    return generated_at.date().isoformat()


def _write_with_latest(dated_path: Path, latest_path: Path, content: str) -> None:
    """Write a dated artifact and refresh its regular-file latest mirror."""
    dated_path.write_text(content, encoding="utf-8")
    if latest_path.is_symlink():
        latest_path.unlink()
    shutil.copyfile(dated_path, latest_path)


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
    output_dir = Path(out_dir)
    report_date = _report_date(report.timestamp)
    written: list[str] = []

    if fmt in ("md", "both"):
        md_path = output_dir / f"bug-scrub-report-{report_date}.md"
        latest_md = output_dir / "latest.md"
        _write_with_latest(md_path, latest_md, render_markdown(report))
        written.extend((str(md_path), str(latest_md)))

    if fmt in ("json", "both"):
        json_path = output_dir / f"bug-scrub-report-{report_date}.json"
        latest_json = output_dir / "latest.json"
        _write_with_latest(json_path, latest_json, render_json(report))
        written.extend((str(json_path), str(latest_json)))

    return written

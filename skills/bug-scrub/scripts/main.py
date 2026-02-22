#!/usr/bin/env python3
"""Bug-scrub orchestrator: collect signals, aggregate, and report."""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure scripts directory is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from aggregate import aggregate
from collect_architecture import collect as collect_architecture
from collect_deferred import collect as collect_deferred
from collect_markers import collect as collect_markers
from collect_mypy import collect as collect_mypy
from collect_openspec import collect as collect_openspec
from collect_pytest import collect as collect_pytest
from collect_ruff import collect as collect_ruff
from collect_security import collect as collect_security
from models import SourceResult
from render_report import write_report

ALL_SOURCES = {
    "pytest": collect_pytest,
    "ruff": collect_ruff,
    "mypy": collect_mypy,
    "openspec": collect_openspec,
    "architecture": collect_architecture,
    "security": collect_security,
    "deferred": collect_deferred,
    "markers": collect_markers,
}


def _detect_project_dir() -> str:
    """Auto-detect project directory by walking up from cwd looking for pyproject.toml."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return str(parent)
    return str(current)


def run(
    sources: list[str] | None = None,
    severity: str = "low",
    project_dir: str | None = None,
    out_dir: str | None = None,
    fmt: str = "both",
) -> int:
    """Run bug-scrub collection, aggregation, and reporting.

    Returns:
        0 for clean (no findings at/above severity), 1 for findings found.
    """
    if project_dir is None:
        project_dir = _detect_project_dir()

    if out_dir is None:
        out_dir = os.path.join(project_dir, "docs", "bug-scrub")

    selected_sources = sources if sources else list(ALL_SOURCES.keys())

    # Collect from each source
    results: list[SourceResult] = []
    for source_name in selected_sources:
        collector = ALL_SOURCES.get(source_name)
        if collector is None:
            print(f"Warning: Unknown source '{source_name}', skipping")
            continue
        print(f"Collecting from {source_name}...")
        result = collector(project_dir)
        results.append(result)
        status_icon = "ok" if result.status == "ok" else result.status
        finding_count = len(result.findings)
        print(f"  {status_icon}: {finding_count} findings ({result.duration_ms}ms)")

    # Aggregate
    timestamp = datetime.now(timezone.utc).isoformat()
    report = aggregate(results, severity_filter=severity, timestamp=timestamp)

    # Report
    written = write_report(report, out_dir, fmt)
    for path in written:
        print(f"Report written: {path}")

    # Summary
    total = len(report.findings)
    by_sev = report.summary_by_severity()
    print(f"\nTotal findings: {total}")
    for sev in ["critical", "high", "medium", "low", "info"]:
        count = by_sev.get(sev, 0)
        if count:
            print(f"  {sev}: {count}")

    if report.recommendations:
        print("\nRecommendations:")
        for rec in report.recommendations:
            print(f"  - {rec}")

    return 1 if total > 0 else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Bug-scrub: project health diagnostic")
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Comma-separated signal sources (default: all)",
    )
    parser.add_argument(
        "--severity",
        type=str,
        default="low",
        choices=["critical", "high", "medium", "low", "info"],
        help="Minimum severity to report (default: low)",
    )
    parser.add_argument(
        "--project-dir",
        type=str,
        default=None,
        help="Project root directory (default: auto-detect)",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="Output directory (default: docs/bug-scrub)",
    )
    parser.add_argument(
        "--format",
        type=str,
        default="both",
        choices=["md", "json", "both"],
        help="Output format (default: both)",
    )
    args = parser.parse_args()

    sources = args.source.split(",") if args.source else None
    exit_code = run(
        sources=sources,
        severity=args.severity,
        project_dir=args.project_dir,
        out_dir=args.out_dir,
        fmt=args.format,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

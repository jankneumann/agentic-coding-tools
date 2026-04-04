#!/usr/bin/env python3
"""Tech-debt analysis orchestrator: run analyzers, aggregate, and report.

Modelled after the bug-scrub orchestrator but focused on structural code
quality rather than CI/linter signals. Analyzers are independent and can
run in parallel.
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# Ensure scripts directory is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from aggregate import aggregate
from analyze_complexity import analyze as analyze_complexity
from analyze_coupling import analyze as analyze_coupling
from analyze_duplication import analyze as analyze_duplication
from analyze_imports import analyze as analyze_imports
from models import AnalyzerResult
from render_report import write_report

ALL_ANALYZERS = {
    "complexity": analyze_complexity,
    "coupling": analyze_coupling,
    "duplication": analyze_duplication,
    "imports": analyze_imports,
}


def _detect_project_dir() -> str:
    """Auto-detect project directory by walking up from cwd."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return str(parent)
    return str(current)


def _run_analyzers_parallel(
    analyzers: dict[str, object],
    project_dir: str,
    max_workers: int = 4,
) -> list[AnalyzerResult]:
    """Run analyzers concurrently using ThreadPoolExecutor."""
    results: list[AnalyzerResult] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(func, project_dir): name  # type: ignore[operator]
            for name, func in analyzers.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as exc:
                results.append(
                    AnalyzerResult(
                        analyzer=name,
                        status="error",
                        messages=[f"Analyzer crashed: {exc}"],
                    )
                )
    return results


def run(
    analyzers: list[str] | None = None,
    severity: str = "low",
    project_dir: str | None = None,
    out_dir: str | None = None,
    fmt: str = "both",
    parallel: bool = True,
    max_workers: int = 4,
) -> int:
    """Run tech-debt analysis, aggregation, and reporting.

    Returns:
        0 for clean (no findings at/above severity), 1 for findings found.
    """
    if project_dir is None:
        project_dir = _detect_project_dir()

    if out_dir is None:
        out_dir = os.path.join(project_dir, "docs", "tech-debt")

    selected = analyzers if analyzers else list(ALL_ANALYZERS.keys())

    # Build analyzer dict
    active_analyzers = {}
    for name in selected:
        func = ALL_ANALYZERS.get(name)
        if func is None:
            print(f"Warning: Unknown analyzer '{name}', skipping")
            continue
        active_analyzers[name] = func

    # Run analyzers
    if parallel and len(active_analyzers) > 1:
        workers = min(max_workers, len(active_analyzers))
        print(f"Running {len(active_analyzers)} analyzers in parallel (max_workers={workers})...")
        results = _run_analyzers_parallel(active_analyzers, project_dir, max_workers=workers)
    else:
        results: list[AnalyzerResult] = []
        for name, func in active_analyzers.items():
            print(f"Running {name} analyzer...")
            result = func(project_dir)
            results.append(result)

    # Print per-analyzer summary
    for result in results:
        finding_count = len(result.findings)
        print(f"  {result.analyzer}: {result.status}, {finding_count} findings ({result.duration_ms}ms)")

    # Aggregate
    timestamp = datetime.now(timezone.utc).isoformat()
    report = aggregate(results, severity_filter=severity, timestamp=timestamp)

    # Write report
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

    # Hotspots
    hotspots = report.hotspot_files(top_n=5)
    if hotspots:
        print("\nTop hotspot files:")
        for file_path, count in hotspots:
            print(f"  {file_path}: {count} findings")

    if report.recommendations:
        print("\nRecommendations:")
        for rec in report.recommendations:
            print(f"  - {rec}")

    return 1 if total > 0 else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tech-debt analysis: structural code quality diagnostic"
    )
    parser.add_argument(
        "--analyzer",
        type=str,
        default=None,
        help="Comma-separated analyzers (default: all). Options: complexity, coupling, duplication, imports",
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
        help="Output directory (default: docs/tech-debt)",
    )
    parser.add_argument(
        "--format",
        type=str,
        default="both",
        choices=["md", "json", "both"],
        help="Output format (default: both)",
    )
    parser.add_argument(
        "--no-parallel",
        action="store_true",
        help="Run analyzers sequentially instead of in parallel",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Max concurrent analyzers (default: 4)",
    )
    args = parser.parse_args()

    analyzer_list = args.analyzer.split(",") if args.analyzer else None
    exit_code = run(
        analyzers=analyzer_list,
        severity=args.severity,
        project_dir=args.project_dir,
        out_dir=args.out_dir,
        fmt=args.format,
        parallel=not args.no_parallel,
        max_workers=args.max_workers,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

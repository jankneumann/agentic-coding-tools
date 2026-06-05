"""Generate markdown dashboard reports from agent metrics.

Formats throughput metrics, failure rates, and capability gap frequency
into structured markdown reports.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Throughput report
# ---------------------------------------------------------------------------

def generate_throughput_report(
    metrics: dict[str, Any],
    *,
    time_range_days: int = 30,
) -> str:
    """Generate a markdown throughput report.

    Parameters
    ----------
    metrics:
        Output from ``query_metrics.compute_throughput()``.
    time_range_days:
        The time range used for the query (for display).
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines: list[str] = []
    lines.append("# Agent Throughput Report")
    lines.append("")
    lines.append(f"**Generated**: {today}  ")
    lines.append(f"**Time range**: {time_range_days} days")
    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Tasks completed | {metrics.get('tasks_completed', 0)} |")
    lines.append(f"| Tasks failed | {metrics.get('tasks_failed', 0)} |")
    lines.append(f"| PRs opened | {metrics.get('prs_opened', 0)} |")
    lines.append(
        f"| Avg review cycles/PR | "
        f"{metrics.get('avg_review_cycles_per_pr', 0):.1f} |"
    )
    lines.append(
        f"| Avg time to merge | "
        f"{metrics.get('avg_time_to_merge_hours', 0):.1f}h |"
    )
    lines.append("")

    # Success rate
    total = metrics.get("tasks_completed", 0) + metrics.get("tasks_failed", 0)
    if total > 0:
        rate = metrics["tasks_completed"] / total * 100
        lines.append(f"**Success rate**: {rate:.1f}%")
    else:
        lines.append("**Success rate**: N/A (no tasks recorded)")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Failure report
# ---------------------------------------------------------------------------

def generate_failure_report(
    rates: dict[str, Any],
    *,
    time_range_days: int = 30,
) -> str:
    """Generate a markdown failure rate analysis report.

    Parameters
    ----------
    rates:
        Output from ``query_metrics.compute_failure_rates()``.
    time_range_days:
        The time range used for the query.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines: list[str] = []
    lines.append("# Failure Rate Analysis")
    lines.append("")
    lines.append(f"**Generated**: {today}  ")
    lines.append(f"**Time range**: {time_range_days} days  ")
    lines.append(f"**Total failures**: {rates.get('total', 0)}")
    lines.append("")

    # By failure type
    by_type = rates.get("by_failure_type", {})
    if by_type:
        lines.append("## By Failure Type")
        lines.append("")
        lines.append("| Failure Type | Count |")
        lines.append("|-------------|-------|")
        for ft, count in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"| {ft} | {count} |")
        lines.append("")

    # By skill
    by_skill = rates.get("by_skill", {})
    if by_skill:
        lines.append("## By Affected Skill")
        lines.append("")
        lines.append("| Skill | Count |")
        lines.append("|-------|-------|")
        for skill, count in sorted(by_skill.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"| {skill} | {count} |")
        lines.append("")

    if not by_type and not by_skill:
        lines.append("No failures recorded in the last "
                      f"{time_range_days} days.")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Gap frequency report
# ---------------------------------------------------------------------------

def generate_gap_report(
    freq: list[dict[str, Any]],
    *,
    time_range_days: int = 30,
) -> str:
    """Generate a markdown capability gap frequency report.

    Parameters
    ----------
    freq:
        Output from ``query_metrics.compute_gap_frequency()``.
    time_range_days:
        The time range used for the query.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines: list[str] = []
    lines.append("# Capability Gap Frequency")
    lines.append("")
    lines.append(f"**Generated**: {today}  ")
    lines.append(f"**Time range**: {time_range_days} days")
    lines.append("")

    if freq:
        lines.append("| Rank | Capability Gap | Count | Max Severity |")
        lines.append("|------|---------------|-------|-------------|")
        for i, item in enumerate(freq, 1):
            lines.append(
                f"| {i} | {item['capability_gap']} "
                f"| {item['count']} "
                f"| {item.get('max_severity', 'unknown')} |"
            )
        lines.append("")
    else:
        lines.append("No capability gaps recorded in the last "
                      f"{time_range_days} days.")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point — generate dashboard report."""
    import argparse
    import os
    import sys

    sys.path.insert(0, os.path.dirname(__file__))
    from query_metrics import (
        compute_failure_rates,
        compute_gap_frequency,
        compute_throughput,
        query_audit,
        query_memory,
    )

    parser = argparse.ArgumentParser(description="Generate agent metrics dashboard")
    parser.add_argument(
        "--time-range", type=int, default=30,
        help="Time range in days (default: 30)",
    )
    parser.add_argument(
        "--failures", action="store_true",
        help="Generate failure rate analysis",
    )
    parser.add_argument(
        "--gaps", action="store_true",
        help="Generate capability gap frequency report",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output file path (default: stdout)",
    )
    args = parser.parse_args()

    if args.failures:
        entries = query_memory(time_range_days=args.time_range)
        rates = compute_failure_rates(entries)
        report = generate_failure_report(rates, time_range_days=args.time_range)
    elif args.gaps:
        entries = query_memory(time_range_days=args.time_range)
        freq = compute_gap_frequency(entries)
        report = generate_gap_report(freq, time_range_days=args.time_range)
    else:
        entries = query_audit(time_range_days=args.time_range)
        metrics = compute_throughput(entries)
        report = generate_throughput_report(metrics, time_range_days=args.time_range)

    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"Report written to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()

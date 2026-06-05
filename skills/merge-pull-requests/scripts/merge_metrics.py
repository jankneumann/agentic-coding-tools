"""Merge throughput metrics aggregation and reporting.

Reads JSONL events and computes aggregated metrics for the merge summary.

Design decisions: D6 (metrics schema and storage)
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from merge_events import DEFAULT_LOG_PATH, load_events


def compute_metrics_summary(
    *,
    log_path: Path = DEFAULT_LOG_PATH,
) -> dict[str, Any]:
    events = load_events(log_path=log_path)

    merges = [e for e in events if e.get("event_type") == "merge"]
    reverts = [e for e in events if e.get("event_type") == "revert"]
    rebases = [e for e in events if e.get("event_type") == "rebase"]
    ejects = [e for e in events if e.get("event_type") == "eject"]
    composes = [e for e in events if e.get("event_type") == "train_compose"]

    merge_count = len(merges)
    revert_count = len(reverts)

    successful_merges = sum(1 for m in merges if m.get("success"))
    merge_success_rate = successful_merges / merge_count if merge_count else 0.0
    revert_rate = revert_count / merge_count if merge_count else 0.0

    backend_counts = Counter(m.get("backend", "unknown") for m in merges)

    durations = [
        m["duration_seconds"]
        for m in merges
        if m.get("duration_seconds") is not None
    ]
    median_duration = _median(durations) if durations else None

    return {
        "total_events": len(events),
        "merge_count": merge_count,
        "revert_count": revert_count,
        "rebase_count": len(rebases),
        "eject_count": len(ejects),
        "compose_count": len(composes),
        "merge_success_rate": merge_success_rate,
        "revert_rate": revert_rate,
        "backend_counts": dict(backend_counts),
        "median_duration_seconds": median_duration,
    }


def _median(values: list[float]) -> float:
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 0:
        return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
    return sorted_vals[mid]


def format_metrics_table(
    *,
    log_path: Path = DEFAULT_LOG_PATH,
) -> str:
    summary = compute_metrics_summary(log_path=log_path)

    lines = [
        "| Metric | Value |",
        "|--------|-------|",
        f"| Merges | {summary['merge_count']} |",
        f"| Reverts | {summary['revert_count']} |",
        f"| Rebases | {summary['rebase_count']} |",
        f"| Success Rate | {summary['merge_success_rate']:.0%} |",
        f"| Revert Rate | {summary['revert_rate']:.0%} |",
    ]

    if summary["median_duration_seconds"] is not None:
        lines.append(
            f"| Median Duration | {summary['median_duration_seconds']:.1f}s |",
        )

    if summary["backend_counts"]:
        backends = ", ".join(
            f"{k}: {v}" for k, v in sorted(summary["backend_counts"].items())
        )
        lines.append(f"| Backends | {backends} |")

    return "\n".join(lines)

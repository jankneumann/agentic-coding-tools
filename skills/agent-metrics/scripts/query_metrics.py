"""Query coordinator audit trail and episodic memory for agent metrics.

Supports three modes:
- Throughput: tasks completed/failed, PRs opened, review cycles, time-to-merge
- Failures: failure rate analysis by agent type, skill, failure_type
- Gaps: capability gap frequency ranked report

Environment:
    COORDINATOR_URL  — base URL of the coordinator (default: http://localhost:8000)
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Query building
# ---------------------------------------------------------------------------

def build_audit_query(
    time_range_days: int = 30,
    operations: list[str] | None = None,
) -> dict[str, Any]:
    """Build a query payload for the coordinator audit API.

    Returns a dict suitable for POST /audit/query.
    """
    query: dict[str, Any] = {
        "time_range": {"days": time_range_days},
    }
    if operations:
        query["operations"] = operations
    return query


def query_audit(
    time_range_days: int = 30,
    operations: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Query the coordinator audit trail.

    Falls back to an empty list with a warning if unreachable.
    """
    payload = build_audit_query(
        time_range_days=time_range_days,
        operations=operations,
    )
    url = f"{COORDINATOR_URL}/audit/query"
    try:
        req = Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data if isinstance(data, list) else data.get("entries", [])
    except (URLError, OSError, json.JSONDecodeError) as exc:
        print(
            f"WARNING: Coordinator unreachable at {url} — {exc}. "
            "Returning empty result set.",
            file=sys.stderr,
        )
        return []


def query_memory(
    time_range_days: int = 30,
    tags: list[str] | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Query the coordinator episodic memory.

    Falls back to an empty list with a warning if unreachable.
    """
    payload: dict[str, Any] = {
        "tags": tags or ["capability_gap"],
        "time_window_days": time_range_days,
        "limit": limit,
    }
    url = f"{COORDINATOR_URL}/memory/query"
    try:
        req = Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data if isinstance(data, list) else data.get("entries", [])
    except (URLError, OSError, json.JSONDecodeError) as exc:
        print(
            f"WARNING: Coordinator unreachable at {url} — {exc}. "
            "Returning empty result set.",
            file=sys.stderr,
        )
        return []


# ---------------------------------------------------------------------------
# Tag extraction helper
# ---------------------------------------------------------------------------

def _extract_tag(tags: list[str], prefix: str) -> str | None:
    """Extract the value of the first tag matching *prefix:*."""
    for tag in tags:
        if tag.startswith(f"{prefix}:"):
            return tag[len(prefix) + 1:]
    return None


# ---------------------------------------------------------------------------
# Throughput computation
# ---------------------------------------------------------------------------

def compute_throughput(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute throughput metrics from audit trail entries.

    Returns a dict with:
        tasks_completed, tasks_failed, prs_opened,
        avg_review_cycles_per_pr, avg_time_to_merge_hours
    """
    tasks_completed = 0
    tasks_failed = 0
    prs_opened = 0
    review_cycles: dict[str, int] = defaultdict(int)
    merge_times: list[float] = []

    for entry in entries:
        op = entry.get("operation", "")
        success = entry.get("success", False)
        params = entry.get("parameters", {})
        result = entry.get("result", {})

        if op == "task_complete":
            if success:
                tasks_completed += 1
            else:
                tasks_failed += 1
        elif op == "pr_open" and success:
            prs_opened += 1
        elif op == "review_cycle" and success:
            pr_id = params.get("pr_id", "unknown")
            review_cycles[pr_id] += 1
        elif op == "pr_merge" and success:
            ttm = result.get("time_to_merge_hours")
            if ttm is not None:
                merge_times.append(float(ttm))

    # Calculate averages
    avg_review_cycles = 0.0
    if review_cycles:
        avg_review_cycles = sum(review_cycles.values()) / len(review_cycles)

    avg_time_to_merge = 0.0
    if merge_times:
        avg_time_to_merge = sum(merge_times) / len(merge_times)

    return {
        "tasks_completed": tasks_completed,
        "tasks_failed": tasks_failed,
        "prs_opened": prs_opened,
        "avg_review_cycles_per_pr": avg_review_cycles,
        "avg_time_to_merge_hours": avg_time_to_merge,
    }


# ---------------------------------------------------------------------------
# Failure rate computation
# ---------------------------------------------------------------------------

def compute_failure_rates(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute failure rates by failure_type and affected_skill.

    Parameters
    ----------
    entries:
        Episodic memory entries with capability-gap tags.

    Returns
    -------
    dict with: total, by_failure_type, by_skill
    """
    by_failure_type: dict[str, int] = defaultdict(int)
    by_skill: dict[str, int] = defaultdict(int)
    total = 0

    for entry in entries:
        tags = entry.get("tags", [])
        ft = _extract_tag(tags, "failure_type")
        skill = _extract_tag(tags, "affected_skill")

        if ft:
            by_failure_type[ft] += 1
            total += 1
        if skill:
            by_skill[skill] += 1

    return {
        "total": total,
        "by_failure_type": dict(by_failure_type),
        "by_skill": dict(by_skill),
    }


# ---------------------------------------------------------------------------
# Capability gap frequency
# ---------------------------------------------------------------------------

def compute_gap_frequency(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compute capability gap frequency, ranked descending.

    Returns a list of dicts: capability_gap, count, max_severity
    """
    gaps: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "severities": []}
    )

    for entry in entries:
        tags = entry.get("tags", [])
        gap = _extract_tag(tags, "capability_gap")
        sev = _extract_tag(tags, "severity") or "low"
        if gap:
            gaps[gap]["count"] += 1
            gaps[gap]["severities"].append(sev)

    result: list[dict[str, Any]] = []
    for gap_name, data in gaps.items():
        max_severity = "low"
        for level in ("critical", "high", "medium", "low"):
            if level in data["severities"]:
                max_severity = level
                break
        result.append({
            "capability_gap": gap_name,
            "count": data["count"],
            "max_severity": max_severity,
        })

    result.sort(key=lambda r: r["count"], reverse=True)
    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Query agent metrics")
    parser.add_argument(
        "--time-range", type=int, default=30,
        help="Time range in days (default: 30)",
    )
    parser.add_argument(
        "--failures", action="store_true",
        help="Show failure rate analysis",
    )
    parser.add_argument(
        "--gaps", action="store_true",
        help="Show capability gap frequency",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON",
    )
    args = parser.parse_args()

    if args.failures:
        entries = query_memory(time_range_days=args.time_range)
        result = compute_failure_rates(entries)
    elif args.gaps:
        entries = query_memory(time_range_days=args.time_range)
        result = compute_gap_frequency(entries)
    else:
        entries = query_audit(time_range_days=args.time_range)
        result = compute_throughput(entries)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

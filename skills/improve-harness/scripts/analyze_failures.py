"""Analyze capability-gap failure patterns from episodic memory.

Queries the coordinator HTTP API for episodic memory entries tagged with
the D4 shared tag schema (failure_type, capability_gap, affected_skill,
severity, source).  Groups by capability_gap, ranks by frequency × severity
weight, and returns structured findings for report generation.

Environment:
    COORDINATOR_URL  — base URL of the coordinator (default: http://localhost:8000)
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Severity weights — used for ranking findings
# ---------------------------------------------------------------------------

SEVERITY_WEIGHTS: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}

COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Query building
# ---------------------------------------------------------------------------

def build_memory_query(
    time_window_days: int = 30,
    limit: int = 500,
) -> dict[str, Any]:
    """Build the query payload for the coordinator memory API.

    Returns a dict suitable for POST /memory/query.
    """
    return {
        "tags": ["capability_gap"],
        "time_window_days": time_window_days,
        "limit": limit,
    }


def query_memory(
    time_window_days: int = 30,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Query the coordinator episodic memory for capability-gap entries.

    Returns a list of memory entry dicts.  Falls back to an empty list with
    a warning if the coordinator is unreachable.
    """
    payload = build_memory_query(time_window_days=time_window_days, limit=limit)
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
# Tag extraction helpers
# ---------------------------------------------------------------------------

def _extract_tag(tags: list[str], prefix: str) -> str | None:
    """Extract the value of the first tag matching *prefix:*."""
    for tag in tags:
        if tag.startswith(f"{prefix}:"):
            return tag[len(prefix) + 1:]
    return None


def _extract_all_tags(tags: list[str], prefix: str) -> list[str]:
    """Extract all values for tags matching *prefix:*."""
    values: list[str] = []
    for tag in tags:
        if tag.startswith(f"{prefix}:"):
            values.append(tag[len(prefix) + 1:])
    return values


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

def group_by_capability_gap(
    entries: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group memory entries by their capability_gap tag value."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        gap = _extract_tag(entry.get("tags", []), "capability_gap")
        if gap:
            groups[gap].append(entry)
    return dict(groups)


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def rank_findings(
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rank grouped findings by (frequency × severity_weight), descending.

    Returns a list of finding dicts with keys:
        capability_gap, frequency, max_severity, score, affected_skills,
        sources, entries
    """
    grouped = group_by_capability_gap(entries)
    findings: list[dict[str, Any]] = []

    for gap, gap_entries in grouped.items():
        score = 0
        severities: list[str] = []
        affected_skills: set[str] = set()
        sources: set[str] = set()

        for entry in gap_entries:
            tags = entry.get("tags", [])
            sev = _extract_tag(tags, "severity") or "low"
            severities.append(sev)
            score += SEVERITY_WEIGHTS.get(sev, 1)

            skill = _extract_tag(tags, "affected_skill")
            if skill:
                affected_skills.add(skill)

            source = _extract_tag(tags, "source")
            if source:
                sources.add(source)

        # Determine the highest severity seen
        max_severity = "low"
        for level in ("critical", "high", "medium", "low"):
            if level in severities:
                max_severity = level
                break

        findings.append({
            "capability_gap": gap,
            "frequency": len(gap_entries),
            "max_severity": max_severity,
            "score": score,
            "affected_skills": sorted(affected_skills),
            "sources": sorted(sources),
            "entries": gap_entries,
        })

    findings.sort(key=lambda f: f["score"], reverse=True)
    return findings


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point — query memory and print ranked findings as JSON."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze capability-gap failure patterns from episodic memory"
    )
    parser.add_argument(
        "--time-window", type=int, default=30,
        help="Time window in days (default: 30)",
    )
    parser.add_argument(
        "--limit", type=int, default=500,
        help="Maximum entries to fetch (default: 500)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output raw ranked findings as JSON",
    )
    args = parser.parse_args()

    entries = query_memory(
        time_window_days=args.time_window,
        limit=args.limit,
    )

    ranked = rank_findings(entries)

    if args.json:
        # Strip raw entries from JSON output for readability
        output = [{k: v for k, v in f.items() if k != "entries"} for f in ranked]
        print(json.dumps(output, indent=2))
    else:
        for i, finding in enumerate(ranked, 1):
            print(
                f"{i}. [{finding['max_severity'].upper()}] "
                f"{finding['capability_gap']} "
                f"(freq={finding['frequency']}, score={finding['score']}, "
                f"skills={finding['affected_skills']})"
            )


if __name__ == "__main__":
    main()

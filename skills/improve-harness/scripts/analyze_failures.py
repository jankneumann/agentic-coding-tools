"""Analyze capability-gap failure patterns from episodic memory and session logs.

Queries the coordinator HTTP API for episodic memory entries tagged with
the D4 shared tag schema (failure_type, capability_gap, affected_skill,
severity, source).  Also scans ``openspec/changes/**/session-log.md`` for
``### Capability Gaps Observed`` sections.  Groups by capability_gap, ranks
by frequency x severity weight, and returns structured findings for report
generation.

Environment:
    COORDINATOR_URL  — base URL of the coordinator (default: http://localhost:8000)
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
# Session-log parsing (multi-source: D10)
# ---------------------------------------------------------------------------

# Regex matching the capability gap line format produced by session-log:
# - **<failure_type>**: <gap> (skill: <skill>, severity: <severity>)
_CAPABILITY_GAP_LINE_RE = re.compile(
    r"^-\s+\*\*(.+?)\*\*:\s+(.+?)\s+\(skill:\s+(.+?),\s+severity:\s+(.+?)\)$"
)


def parse_session_log_gaps(
    content: str,
    *,
    session_id: str = "unknown",
) -> list[dict[str, Any]]:
    """Parse ``### Capability Gaps Observed`` sections from session-log markdown.

    Returns a list of flat dicts with keys: failure_type, capability_gap,
    affected_skill, severity, source, session_id.
    """
    gaps: list[dict[str, Any]] = []
    in_section = False

    for line in content.splitlines():
        stripped = line.strip()

        # Detect section boundaries
        if stripped.startswith("### Capability Gaps Observed"):
            in_section = True
            continue
        if in_section and stripped.startswith("### "):
            in_section = False
            continue

        if in_section:
            m = _CAPABILITY_GAP_LINE_RE.match(stripped)
            if m:
                gaps.append({
                    "failure_type": m.group(1).strip(),
                    "capability_gap": m.group(2).strip(),
                    "affected_skill": m.group(3).strip(),
                    "severity": m.group(4).strip(),
                    "source": "session-log",
                    "session_id": session_id,
                })

    return gaps


def scan_session_logs(
    repo_root: str | None = None,
) -> list[dict[str, Any]]:
    """Scan ``openspec/changes/**/session-log.md`` for capability gaps.

    Parameters
    ----------
    repo_root:
        Repository root directory.  Defaults to the current working directory.

    Returns
    -------
    list of flat finding dicts (same shape as ``parse_session_log_gaps``).
    """
    if repo_root is None:
        repo_root = os.getcwd()

    pattern = os.path.join(repo_root, "openspec", "changes", "**", "session-log.md")
    all_gaps: list[dict[str, Any]] = []

    for log_path in glob.glob(pattern, recursive=True):
        # Derive a pseudo session_id from the change-id directory name
        parts = Path(log_path).parts
        try:
            idx = parts.index("changes")
            change_id = parts[idx + 1]
        except (ValueError, IndexError):
            change_id = "unknown"

        try:
            content = Path(log_path).read_text(encoding="utf-8")
        except OSError:
            continue

        gaps = parse_session_log_gaps(content, session_id=change_id)
        all_gaps.extend(gaps)

    return all_gaps


# ---------------------------------------------------------------------------
# Deduplication (multi-source)
# ---------------------------------------------------------------------------

def deduplicate_findings(
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deduplicate findings on ``(capability_gap, affected_skill, session_id)``.

    When the same finding appears from multiple sources, all sources are
    merged into a ``sources`` list on the surviving entry.

    Parameters
    ----------
    findings:
        Flat finding dicts, each with at least: capability_gap, affected_skill,
        session_id, source (single string) or sources (list).

    Returns
    -------
    Deduplicated list preserving multi-source attribution.
    """
    key_map: dict[tuple[str, str, str], dict[str, Any]] = {}

    for f in findings:
        key = (
            f.get("capability_gap", ""),
            f.get("affected_skill", ""),
            f.get("session_id", ""),
        )

        # Normalize source → sources list
        if "sources" in f:
            new_sources = set(f["sources"])
        elif "source" in f:
            new_sources = {f["source"]}
        else:
            new_sources = set()

        if key in key_map:
            existing = key_map[key]
            existing["sources"] = sorted(
                set(existing["sources"]) | new_sources
            )
        else:
            entry = dict(f)
            entry["sources"] = sorted(new_sources)
            key_map[key] = entry

    return list(key_map.values())


# ---------------------------------------------------------------------------
# Normalize memory entries to flat finding dicts
# ---------------------------------------------------------------------------

def normalize_memory_entries(
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert raw memory entries (with ``tags`` lists) to flat finding dicts.

    Each output dict has: failure_type, capability_gap, affected_skill,
    severity, source, session_id, sources.
    """
    out: list[dict[str, Any]] = []
    for entry in entries:
        tags = entry.get("tags", [])
        out.append({
            "failure_type": _extract_tag(tags, "failure_type") or "unknown",
            "capability_gap": _extract_tag(tags, "capability_gap") or "unknown",
            "affected_skill": _extract_tag(tags, "affected_skill") or "unknown",
            "severity": _extract_tag(tags, "severity") or "low",
            "source": _extract_tag(tags, "source") or "unknown",
            "session_id": entry.get("session_id", "unknown"),
        })
    return out


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
    parser.add_argument(
        "--repo-root", type=str, default=None,
        help="Repository root for session-log scanning (default: cwd)",
    )
    args = parser.parse_args()

    # Collect from both sources
    memory_entries = query_memory(
        time_window_days=args.time_window,
        limit=args.limit,
    )
    memory_findings = normalize_memory_entries(memory_entries)
    session_log_findings = scan_session_logs(repo_root=args.repo_root)

    # Merge and deduplicate
    all_findings = deduplicate_findings(memory_findings + session_log_findings)

    # Rank using the standard pipeline (convert back to tag-based format)
    ranked = rank_findings(memory_entries)

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

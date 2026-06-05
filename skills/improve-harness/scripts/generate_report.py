"""Generate structured markdown reports from capability-gap findings.

Formats the output of ``analyze_failures.rank_findings()`` into a
human-readable markdown report with summary statistics, a ranked findings
table, and recommendations.  Optionally creates OpenSpec proposal stubs
from high-priority findings.
"""

from __future__ import annotations

import json
import os
import textwrap
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    entries: list[dict[str, Any]],
    *,
    time_window_days: int = 30,
) -> str:
    """Generate a markdown report from raw memory entries.

    Parameters
    ----------
    entries:
        Raw memory entries (each with ``tags`` and ``summary`` fields).
    time_window_days:
        The time window used for the query (for display in the report).

    Returns
    -------
    str
        A complete markdown report.
    """
    from analyze_failures import rank_findings

    if not entries:
        return (
            f"# Capability Gap Report\n\n"
            f"No capability gaps recorded in the last {time_window_days} days.\n\n"
            f"Verify that emitters (self-report, coordinator, session-log, "
            f"transcript) are configured and active.\n"
        )

    ranked = rank_findings(entries)
    total_entries = len(entries)
    unique_gaps = len(ranked)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines: list[str] = []
    lines.append("# Capability Gap Report")
    lines.append("")
    lines.append(f"**Generated**: {today}  ")
    lines.append(f"**Time window**: {time_window_days} days  ")
    lines.append(f"**Total findings**: {total_entries}  ")
    lines.append(f"**Unique gaps**: {unique_gaps}")
    lines.append("")

    # --- Summary ---
    lines.append("## Summary")
    lines.append("")
    severity_counts: dict[str, int] = {}
    for finding in ranked:
        sev = finding["max_severity"]
        severity_counts[sev] = severity_counts.get(sev, 0) + finding["frequency"]
    for sev in ("critical", "high", "medium", "low"):
        count = severity_counts.get(sev, 0)
        if count:
            lines.append(f"- **{sev.capitalize()}**: {count} occurrences")
    lines.append("")

    # --- Ranked findings table ---
    lines.append("## Ranked Findings")
    lines.append("")
    lines.append("| Rank | Capability Gap | Frequency | Max Severity | Score | Affected Skills |")
    lines.append("|------|---------------|-----------|-------------|-------|-----------------|")
    for i, finding in enumerate(ranked, 1):
        skills_str = ", ".join(finding["affected_skills"]) or "—"
        lines.append(
            f"| {i} | {finding['capability_gap']} "
            f"| {finding['frequency']} "
            f"| {finding['max_severity']} "
            f"| {finding['score']} "
            f"| {skills_str} |"
        )
    lines.append("")

    # --- Recommendations ---
    lines.append("## Recommendations")
    lines.append("")
    for i, finding in enumerate(ranked[:5], 1):
        lines.append(f"### {i}. {finding['capability_gap']}")
        lines.append("")
        lines.append(
            f"- **Impact**: {finding['frequency']} occurrences, "
            f"max severity {finding['max_severity']}, "
            f"score {finding['score']}"
        )
        lines.append(f"- **Affected skills**: {', '.join(finding['affected_skills']) or '—'}")
        lines.append(
            f"- **Action**: Investigate root cause and consider creating an "
            f"OpenSpec proposal to address this gap."
        )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Proposal stub generation
# ---------------------------------------------------------------------------

def create_proposal_stub(finding: dict[str, Any]) -> str:
    """Create an OpenSpec proposal stub from a ranked finding.

    Parameters
    ----------
    finding:
        A ranked finding dict from ``rank_findings()`` containing:
        capability_gap, frequency, max_severity, affected_skills, score, sources.

    Returns
    -------
    str
        A markdown proposal stub ready for human refinement.
    """
    gap = finding["capability_gap"]
    freq = finding["frequency"]
    severity = finding["max_severity"]
    skills = finding.get("affected_skills", [])
    score = finding.get("score", 0)
    sources = finding.get("sources", [])

    skills_str = ", ".join(skills) if skills else "unknown"
    sources_str = ", ".join(sources) if sources else "unknown"

    return textwrap.dedent(f"""\
        # Proposal: Address capability gap — {gap}

        **Status**: Draft
        **Created**: {datetime.now(timezone.utc).strftime("%Y-%m-%d")}
        **Origin**: /improve-harness report (auto-generated stub)

        ## Why

        This capability gap was observed {freq} time(s) with max severity
        **{severity}** (score: {score}). It affects: {skills_str}.

        Sources: {sources_str}.

        Addressing this gap will reduce agent failures and improve harness
        reliability.

        ## What Changes

        <!-- Describe the proposed fix or enhancement -->

        TODO: Detail the specific changes needed to address "{gap}".

        ## Success Criteria

        1. The capability gap "{gap}" no longer appears in /improve-harness reports
        2. Affected skills ({skills_str}) handle the previously-failing scenario correctly
        3. Tests cover the fix
    """)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point — generate report from memory entries."""
    import argparse
    import sys

    sys.path.insert(0, os.path.dirname(__file__))
    from analyze_failures import query_memory, rank_findings

    parser = argparse.ArgumentParser(
        description="Generate capability-gap analysis report"
    )
    parser.add_argument(
        "--time-window", type=int, default=30,
        help="Time window in days (default: 30)",
    )
    parser.add_argument(
        "--create-proposal", action="store_true",
        help="Create an OpenSpec proposal stub from the top finding",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output file path (default: stdout)",
    )
    args = parser.parse_args()

    entries = query_memory(time_window_days=args.time_window)
    report = generate_report(entries, time_window_days=args.time_window)

    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"Report written to {args.output}")
    else:
        print(report)

    if args.create_proposal and entries:
        ranked = rank_findings(entries)
        if ranked:
            stub = create_proposal_stub(ranked[0])
            proposal_path = args.output.replace(".md", "-proposal.md") if args.output else None
            if proposal_path:
                with open(proposal_path, "w") as f:
                    f.write(stub)
                print(f"Proposal stub written to {proposal_path}")
            else:
                print("\n---\n")
                print(stub)


if __name__ == "__main__":
    main()

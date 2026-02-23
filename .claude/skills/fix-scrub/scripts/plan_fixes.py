#!/usr/bin/env python3
"""Fix planner: group classified findings by file scope and prepare execution plan."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fix_models import ClassifiedFinding, FixGroup, FixPlan, severity_rank  # noqa: E402


def plan(
    classified: list[ClassifiedFinding],
    max_agent_fixes: int = 10,
    dry_run: bool = False,
) -> FixPlan:
    """Create a fix execution plan from classified findings.

    Groups findings by file_path, separates auto/agent/manual,
    and enforces max_agent_fixes limit (highest severity first).

    Args:
        classified: List of classified findings.
        max_agent_fixes: Maximum number of agent-tier findings to process.
        dry_run: If True, the plan is for preview only.

    Returns:
        FixPlan with grouped findings.
    """
    auto_by_file: dict[str, list[ClassifiedFinding]] = {}
    agent_by_file: dict[str, list[ClassifiedFinding]] = {}
    manual: list[ClassifiedFinding] = []

    for cf in classified:
        if cf.tier == "auto":
            key = cf.finding.file_path or "__no_file__"
            auto_by_file.setdefault(key, []).append(cf)
        elif cf.tier == "agent":
            key = cf.finding.file_path or "__no_file__"
            agent_by_file.setdefault(key, []).append(cf)
        else:
            manual.append(cf)

    # Build auto groups
    auto_groups = [
        FixGroup(file_path=fp, classified_findings=cfs)
        for fp, cfs in sorted(auto_by_file.items())
    ]

    # Build agent groups with max limit
    # Sort all agent findings by severity (descending), take top N
    all_agent_cfs = []
    for cfs in agent_by_file.values():
        all_agent_cfs.extend(cfs)
    all_agent_cfs.sort(
        key=lambda cf: -severity_rank(cf.finding.severity)
    )

    # Take top max_agent_fixes
    selected_agent_cfs = all_agent_cfs[:max_agent_fixes]
    deferred_agent_cfs = all_agent_cfs[max_agent_fixes:]

    # Re-group selected agent findings by file
    selected_by_file: dict[str, list[ClassifiedFinding]] = {}
    for cf in selected_agent_cfs:
        key = cf.finding.file_path or "__no_file__"
        selected_by_file.setdefault(key, []).append(cf)

    agent_groups = [
        FixGroup(file_path=fp, classified_findings=cfs)
        for fp, cfs in sorted(selected_by_file.items())
    ]

    # Add deferred agent findings to manual (reported but not fixed this run)
    for cf in deferred_agent_cfs:
        manual.append(
            ClassifiedFinding(
                finding=cf.finding,
                tier="manual",
                fix_strategy=f"Deferred: exceeded max-agent-fixes ({max_agent_fixes})",
            )
        )

    auto_count = sum(len(g.classified_findings) for g in auto_groups)
    agent_count = sum(len(g.classified_findings) for g in agent_groups)

    return FixPlan(
        auto_groups=auto_groups,
        agent_groups=agent_groups,
        manual_findings=manual,
        summary={
            "auto": auto_count,
            "agent": agent_count,
            "manual": len(manual),
            "total": auto_count + agent_count + len(manual),
        },
    )

#!/usr/bin/env python3
"""Fix-scrub report renderer: produce summary of actions taken."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fix_models import ClassifiedFinding  # noqa: E402
from verify import VerificationResult  # noqa: E402


def render_fix_report(
    auto_resolved: list[ClassifiedFinding],
    agent_resolved: list[ClassifiedFinding],
    manual_remaining: list[ClassifiedFinding],
    tasks_completed: list[str],
    verification: VerificationResult,
    regressions: list[str] | None = None,
) -> str:
    """Render fix-scrub summary as markdown.

    Args:
        auto_resolved: Auto-tier findings that were fixed.
        agent_resolved: Agent-tier findings that were fixed.
        manual_remaining: Manual-tier findings not fixed.
        tasks_completed: List of OpenSpec task file paths updated.
        verification: Quality verification result.
        regressions: Regression details if any.

    Returns:
        Markdown string.
    """
    lines: list[str] = []

    lines.append("# Fix Scrub Report")
    lines.append("")

    # Tier breakdown
    lines.append("## Fixes Applied")
    lines.append("")
    lines.append(f"- **Auto-fixes**: {len(auto_resolved)} (ruff --fix)")
    lines.append(f"- **Agent-fixes**: {len(agent_resolved)}")
    lines.append(f"- **Manual-only**: {len(manual_remaining)} (reported, not fixed)")
    lines.append("")

    # Files changed
    auto_files = {cf.finding.file_path for cf in auto_resolved if cf.finding.file_path}
    agent_files = {cf.finding.file_path for cf in agent_resolved if cf.finding.file_path}
    all_files = auto_files | agent_files
    if all_files:
        lines.append("## Files Changed")
        lines.append("")
        for fp in sorted(all_files):
            lines.append(f"- `{fp}`")
        lines.append("")

    # OpenSpec tasks completed
    if tasks_completed:
        lines.append("## OpenSpec Tasks Completed")
        lines.append("")
        for tp in tasks_completed:
            lines.append(f"- `{tp}`")
        lines.append("")

    # Quality checks
    lines.append("## Quality Checks")
    lines.append("")
    lines.append("| Tool | Result |")
    lines.append("|------|--------|")
    for tool, result in verification.checks.items():
        icon = "pass" if result == "pass" else "FAIL"
        lines.append(f"| {tool} | {icon} |")
    lines.append("")

    # Regressions
    if verification.regressions:
        lines.append("## Regressions Detected")
        lines.append("")
        for reg in verification.regressions:
            lines.append(f"- {reg}")
        lines.append("")

    # Manual items
    if manual_remaining:
        lines.append("## Manual Action Items")
        lines.append("")
        for cf in manual_remaining:
            f = cf.finding
            loc = f"{f.file_path}:{f.line}" if f.file_path and f.line else f.file_path or "N/A"
            lines.append(f"- [{f.severity.upper()}] {f.title} ({loc}) — {cf.fix_strategy}")
        lines.append("")

    return "\n".join(lines)


def write_fix_report(
    content: str,
    out_dir: str,
) -> str:
    """Write fix-scrub report to file.

    Returns:
        Path to written file.
    """
    os.makedirs(out_dir, exist_ok=True)
    path = str(Path(out_dir) / "fix-scrub-report.md")
    with open(path, "w") as f:
        f.write(content)
    return path

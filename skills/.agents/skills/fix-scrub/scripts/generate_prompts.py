#!/usr/bin/env python3
"""Agent-fix prompt generator: create Task() prompts for agent-tier findings."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fix_models import FixGroup  # noqa: E402


def generate_prompts(
    agent_groups: list[FixGroup],
) -> list[tuple[str, str]]:
    """Generate Task(general-purpose) prompts for each agent fix group.

    Each group targets a single file. The prompt includes finding details
    and explicit file scope restriction.

    Args:
        agent_groups: Groups of agent-tier findings, one per file.

    Returns:
        List of (file_path, prompt_text) tuples.
    """
    prompts: list[tuple[str, str]] = []

    for group in agent_groups:
        file_path = group.file_path
        findings_detail: list[str] = []

        for cf in group.classified_findings:
            f = cf.finding
            loc = f"{f.file_path}:{f.line}" if f.line else f.file_path
            findings_detail.append(
                f"- [{f.severity.upper()}] {f.title}\n"
                f"  Location: {loc}\n"
                f"  Source: {f.source}\n"
                f"  Detail: {f.detail}\n"
                f"  Strategy: {cf.fix_strategy}"
            )

        findings_text = "\n".join(findings_detail)

        prompt = f"""You are fixing code quality issues in a single file.

## File Scope (CRITICAL)
You MAY ONLY modify: `{file_path}`
You must NOT modify any other files.

## Findings to Fix

{findings_text}

## Instructions
1. Read the file `{file_path}`
2. Apply the fixes described above
3. Ensure no new issues are introduced
4. Report what you changed

Do NOT commit — the orchestrator handles commits."""

        prompts.append((file_path, prompt))

    return prompts

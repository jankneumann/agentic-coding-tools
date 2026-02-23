#!/usr/bin/env python3
"""Task completion tracker: update OpenSpec tasks.md when findings are resolved."""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fix_models import ClassifiedFinding, Finding  # noqa: E402


def _is_partial_task(line: str) -> bool:
    """Check if a task line contains numbered sub-items or semicolons indicating multi-part."""
    # e.g., "1. foo; 2. bar" or "a) foo b) bar"
    return bool(
        re.search(r"\d+\.\s", line)
        or ";" in line
        or re.search(r"[a-z]\)\s", line)
    )


def _update_tasks_md(
    file_path: str,
    task_line_text: str,
    today: str,
) -> bool:
    """Update a specific unchecked task to checked in a tasks.md file.

    Returns True if the update was applied.
    """
    path = Path(file_path)
    if not path.exists():
        return False

    content = path.read_text()
    lines = content.split("\n")
    updated = False

    for i, line in enumerate(lines):
        # Match unchecked items that contain the task text
        if re.match(r"\s*- \[ \]", line) and task_line_text in line:
            if _is_partial_task(line):
                # Skip partial tasks
                continue
            lines[i] = line.replace(
                "- [ ]",
                f"- [x]",
            ) + f" (completed by fix-scrub {today})"
            updated = True
            break

    if updated:
        path.write_text("\n".join(lines))
    return updated


def _update_deferred_tasks_md(
    file_path: str,
    task_description: str,
    today: str,
) -> bool:
    """Annotate a deferred-tasks.md entry as resolved.

    Returns True if the update was applied.
    """
    path = Path(file_path)
    if not path.exists():
        return False

    content = path.read_text()
    if task_description not in content:
        return False

    # Append resolution note to the matching line
    lines = content.split("\n")
    updated = False
    for i, line in enumerate(lines):
        if task_description in line and "(resolved by fix-scrub" not in line:
            lines[i] = line.rstrip() + f" (resolved by fix-scrub {today})"
            updated = True
            break

    if updated:
        path.write_text("\n".join(lines))
    return updated


def track_completions(
    resolved_findings: list[ClassifiedFinding],
    project_dir: str,
) -> list[str]:
    """Update OpenSpec task artifacts for resolved findings.

    Args:
        resolved_findings: Findings that were successfully fixed.
        project_dir: Project root directory.

    Returns:
        List of file paths that were updated (for staging in commit).
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    updated_files: list[str] = []

    for cf in resolved_findings:
        f = cf.finding
        if f.origin is None:
            continue

        source = f.source
        artifact_path = str(Path(project_dir) / f.origin.artifact_path)

        if source == "deferred:open-tasks":
            # Update tasks.md checkbox
            if _update_tasks_md(artifact_path, f.title, today):
                if artifact_path not in updated_files:
                    updated_files.append(artifact_path)

        elif source == "deferred:tasks":
            # Update deferred-tasks.md
            if _update_deferred_tasks_md(artifact_path, f.title, today):
                if artifact_path not in updated_files:
                    updated_files.append(artifact_path)

        elif source == "deferred:impl-findings":
            # Update deferred-tasks.md or impl-findings.md
            if _update_deferred_tasks_md(artifact_path, f.title, today):
                if artifact_path not in updated_files:
                    updated_files.append(artifact_path)

    return updated_files

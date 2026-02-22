#!/usr/bin/env python3
"""Auto-fix executor: apply tool-native fixes for auto-tier findings."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fix_models import ClassifiedFinding, FixGroup  # noqa: E402


def execute_auto_fixes(
    auto_groups: list[FixGroup],
    project_dir: str,
) -> tuple[list[ClassifiedFinding], list[ClassifiedFinding]]:
    """Apply auto-fixes using ruff --fix and verify results.

    Args:
        auto_groups: Groups of auto-tier findings.
        project_dir: Project root directory.

    Returns:
        Tuple of (resolved findings, persisting findings).
    """
    if not auto_groups:
        return [], []

    # Collect all unique file paths
    files: set[str] = set()
    all_findings: list[ClassifiedFinding] = []
    for group in auto_groups:
        if group.file_path != "__no_file__":
            files.add(group.file_path)
        all_findings.extend(group.classified_findings)

    if not files:
        return [], all_findings

    # Run ruff check --fix on affected files
    file_list = sorted(files)
    try:
        subprocess.run(
            ["ruff", "check", "--fix", *file_list],
            capture_output=True,
            text=True,
            cwd=project_dir,
        )
    except FileNotFoundError:
        # ruff not available — all findings persist
        return [], all_findings

    # Re-run ruff to verify which findings were resolved
    try:
        result = subprocess.run(
            ["ruff", "check", "--output-format=json", *file_list],
            capture_output=True,
            text=True,
            cwd=project_dir,
        )
        remaining_violations = set()
        if result.stdout.strip():
            project_path = Path(project_dir).resolve()
            for item in json.loads(result.stdout):
                filename = item.get("filename", "")
                row = item.get("location", {}).get("row", 0)
                code = item.get("code", "")
                # Normalize to relative path to match finding IDs
                try:
                    filename = str(Path(filename).relative_to(project_path))
                except ValueError:
                    pass
                remaining_violations.add(f"{code}-{filename}:{row}")
    except (FileNotFoundError, json.JSONDecodeError):
        remaining_violations = set()

    resolved: list[ClassifiedFinding] = []
    persisting: list[ClassifiedFinding] = []

    for cf in all_findings:
        # Extract the identifying part from finding ID
        # Finding IDs are like "ruff-E501-file.py:10"
        parts = cf.finding.id.split("-", 1)
        check_key = parts[1] if len(parts) > 1 else cf.finding.id
        if check_key in remaining_violations:
            persisting.append(cf)
        else:
            resolved.append(cf)

    return resolved, persisting

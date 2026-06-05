"""Structural architecture linters for the validate-feature pipeline.

Exports a run_all_linters() function that orchestrates all structural linters
and produces findings in the review-findings schema format.

Linters:
- dependency_direction: validates import direction between architectural layers
- file_size: checks file line counts against a configurable maximum
- naming_conventions: validates naming patterns for skills, scripts, and schemas
"""

from __future__ import annotations

from typing import Any

from .dependency_direction import check_dependency_direction
from .file_size import check_file_size
from .naming_conventions import check_naming_conventions

__all__ = [
    "run_all_linters",
    "check_dependency_direction",
    "check_file_size",
    "check_naming_conventions",
]

_DEFAULT_TARGET = "wp-architecture-linters"


def run_all_linters(
    changed_files: list[str],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run all structural linters and return combined findings.

    Args:
        changed_files: List of file paths to check (from git diff or passed list).
        config: Optional configuration dict. Supported keys:
            - max_lines (int): Maximum file line count (default: 500).
            - target (str): Target identifier for the review-findings output.

    Returns:
        A review-findings document with combined findings from all linters.
        Findings have unique sequential integer IDs.
    """
    if config is None:
        config = {}

    target = config.get("target", _DEFAULT_TARGET)
    max_lines = config.get("max_lines", 500)

    # Run each linter
    dep_findings = check_dependency_direction(changed_files)
    size_findings = check_file_size(changed_files, max_lines=max_lines)
    naming_findings = check_naming_conventions(changed_files)

    # Combine and re-number findings with unique sequential IDs
    all_findings = dep_findings + size_findings + naming_findings
    for idx, finding in enumerate(all_findings, start=1):
        finding["id"] = idx

    return {
        "review_type": "implementation",
        "target": target,
        "reviewer_vendor": "structural-linter",
        "findings": all_findings,
    }

"""File size linter — checks file line counts against a configurable maximum.

Default maximum: 500 lines. Files exceeding the limit get a finding
with a decomposition suggestion.

Produces findings in the review-findings schema format with agent-readable remediation.
"""

from __future__ import annotations

from pathlib import Path

_DEFAULT_MAX_LINES = 500

_REMEDIATION_TEMPLATE = (
    "File has {actual} lines, exceeding the {max} line limit. "
    "Consider splitting into smaller, focused modules. "
    "Extract cohesive groups of functions or classes into separate files "
    "and import them from a package __init__.py."
)


def check_file_size(
    changed_files: list[str],
    max_lines: int = _DEFAULT_MAX_LINES,
) -> list[dict]:
    """Check that files do not exceed the configured maximum line count.

    Args:
        changed_files: List of file paths to check.
        max_lines: Maximum allowed line count (default: 500).

    Returns:
        List of finding dicts in review-findings schema format.
    """
    findings: list[dict] = []
    finding_id = 1

    for file_path in changed_files:
        path = Path(file_path)

        if not path.exists():
            continue

        try:
            line_count = len(path.read_text().splitlines())
        except (OSError, UnicodeDecodeError):
            continue

        if line_count > max_lines:
            findings.append({
                "id": finding_id,
                "type": "architecture",
                "criticality": "medium",
                "disposition": "fix",
                "description": (
                    f"{file_path} has {line_count} lines, "
                    f"exceeding the {max_lines} line limit"
                ),
                "resolution": _REMEDIATION_TEMPLATE.format(
                    actual=line_count, max=max_lines,
                ),
                "file_path": str(file_path),
                "line_range": {"start": 1, "end": line_count},
            })
            finding_id += 1

    return findings

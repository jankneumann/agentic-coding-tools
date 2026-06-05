"""Dependency direction linter — validates import direction between layers.

Skills must NOT import from agent-coordinator internals (agent-coordinator/src/**).
Allowed: importing from skills/shared/, using coordinator HTTP API or MCP tools.

Produces findings in the review-findings schema format with agent-readable remediation.
"""

from __future__ import annotations

import re
from pathlib import Path

# Import patterns that indicate a dependency direction violation.
# These match inside Python files under skills/.
_VIOLATION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"^\s*from\s+agent_coordinator\b"),
        "imports from agent_coordinator package",
    ),
    (
        re.compile(r"^\s*import\s+agent_coordinator\b"),
        "imports agent_coordinator package",
    ),
    (
        re.compile(r"^\s*from\s+src\.\w"),
        "imports from coordinator src.* directly",
    ),
]

_REMEDIATION = (
    "Use coordinator MCP tools or HTTP API instead of direct imports. "
    "Skills should interact with the coordinator through its public interface, "
    "not by importing internal modules. "
    "See docs/agent-coordinator.md for the API reference."
)


def _is_skills_file(file_path: str) -> bool:
    """Check if a file is under a skills/ directory."""
    parts = Path(file_path).parts
    return "skills" in parts


def check_dependency_direction(
    changed_files: list[str],
) -> list[dict]:
    """Check that skills files do not import from agent-coordinator internals.

    Args:
        changed_files: List of file paths to check.

    Returns:
        List of finding dicts in review-findings schema format.
    """
    findings: list[dict] = []
    finding_id = 1

    for file_path in changed_files:
        path = Path(file_path)

        # Only check Python files under skills/
        if not _is_skills_file(file_path):
            continue
        if path.suffix != ".py":
            continue
        if not path.exists():
            continue

        try:
            lines = path.read_text().splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        for line_num, line in enumerate(lines, start=1):
            for pattern, reason in _VIOLATION_PATTERNS:
                if pattern.search(line):
                    findings.append({
                        "id": finding_id,
                        "type": "architecture",
                        "criticality": "high",
                        "disposition": "fix",
                        "description": (
                            f"{file_path} {reason} "
                            f"(line {line_num}: {line.strip()})"
                        ),
                        "resolution": _REMEDIATION,
                        "file_path": str(file_path),
                        "line_range": {"start": line_num, "end": line_num},
                    })
                    finding_id += 1
                    break  # One finding per line

    return findings

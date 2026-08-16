"""Dependency direction linter — validates import direction between layers.

Skills must NOT import from agent-coordinator internals (agent-coordinator/src/**).
Allowed: importing from skills/shared/, using coordinator HTTP API or MCP tools.

Produces findings in the review-findings schema format with agent-readable remediation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from .severity import severity_for_criticality
except ImportError:  # executed directly as a script (install-payload check in CI)
    from severity import severity_for_criticality  # type: ignore[no-redef]

# A layering/boundary violation is an architecture-axis concern: it is about
# module boundaries and dependency direction, not about local code quality.
_AXIS = "architecture"
_CRITICALITY = "high"

# Runtime reference patterns that indicate an installed-payload boundary
# violation. They intentionally operate line-by-line so findings point to the
# exact executable snippet, hook, or import that must be repaired.
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
        re.compile(r"\bfrom\s+src\.\w"),
        "imports from coordinator src.* directly",
    ),
    (
        re.compile(r"\bimport\s+src(?:\.|\b)"),
        "imports coordinator src.* directly",
    ),
    (
        re.compile(
            r"(?:sys\.path|parents?\[[^]]+\]|Path\()[^\n]*agent-coordinator"
            r"|agent-coordinator[^\n]*(?:sys\.path|parents?\[[^]]+\])"
        ),
        "injects or derives an agent-coordinator source path",
    ),
    (
        re.compile(r"(?<!\.claude/)(?<!\.agents/)skills/\.venv(?:/|\b)"),
        "uses skills/.venv, which is not installed in consumer repositories",
    ),
    (
        re.compile(
            r"(?<!\.claude/)(?<!\.agents/)skills/(?:install\.sh\b|"
            r"shared/[A-Za-z0-9_.-]+|[a-z0-9][a-z0-9-]*/scripts(?:/|\b))"
        ),
        "uses a canonical skills/ runtime path instead of the installed skill base",
    ),
]

_RUNTIME_SUFFIXES = {".py", ".sh", ".bash", ".zsh", ".md", ".json", ".yaml", ".yml"}

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


def _pattern_applies(path: Path, line: str, reason: str) -> bool:
    """Distinguish executable references from examples and narrative prose."""
    if "source-contribution-only" in line:
        return False
    if reason.startswith(("imports", "injects")):
        return True
    suffix = path.suffix.lower()
    stripped = line.strip()
    if suffix == ".py":
        return bool(re.search(r"\b(?:subprocess|command|cmd|runner|hook)\b", line, re.IGNORECASE))
    if suffix in {".sh", ".bash", ".zsh"}:
        return bool(stripped and not stripped.startswith("#"))
    if suffix in {".json", ".yaml", ".yml"}:
        return bool(re.search(r"\b(?:command|cmd|runner|hook)\b", line, re.IGNORECASE))
    if suffix == ".md":
        if re.search(r"\b(?:must not|do not|never)\b", line, re.IGNORECASE):
            return False
        return bool(
            re.match(r"^\s*(?:[$>]\s*)?(?:python3?|bash|sh|eval|skills/)", line)
            or re.search(r"\b(?:run|invoke|execute|command|via|use)\b", line, re.IGNORECASE)
        )
    return False


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

        # Check executable source, hook/config payloads, and skill instructions.
        if not _is_skills_file(file_path):
            continue
        if path.suffix.lower() not in _RUNTIME_SUFFIXES:
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        if not path.exists():
            continue

        try:
            lines = path.read_text().splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        for line_num, line in enumerate(lines, start=1):
            for pattern, reason in _VIOLATION_PATTERNS:
                if pattern.search(line) and _pattern_applies(path, line, reason):
                    findings.append({
                        "id": finding_id,
                        "type": "architecture",
                        "axis": _AXIS,
                        "severity": severity_for_criticality(_CRITICALITY),
                        "criticality": _CRITICALITY,
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


def _installed_payload_files(skills_root: Path) -> list[str]:
    files: list[str] = []
    for path in skills_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _RUNTIME_SUFFIXES:
            continue
        rel_parts = path.relative_to(skills_root).parts
        if "tests" in rel_parts or "__pycache__" in rel_parts or ".venv" in rel_parts:
            continue
        files.append(str(path))
    return sorted(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-root", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    findings = check_dependency_direction(_installed_payload_files(args.skills_root.resolve()))
    if args.json:
        print(json.dumps({"findings": findings}, indent=2))
    elif findings:
        print("Dependency-direction validation failed:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding['description']}", file=sys.stderr)
    else:
        print("Dependency-direction validation passed")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

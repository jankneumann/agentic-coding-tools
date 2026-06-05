"""Naming conventions linter — validates naming patterns for skills, scripts, and schemas.

Rules:
- Skill directories: kebab-case (e.g., improve-harness, not improve_harness)
- Script files under skills/: snake_case .py (e.g., analyze_failures.py)
- Schema files: kebab-case .json or .yaml

Produces findings in the review-findings schema format with agent-readable remediation.
"""

from __future__ import annotations

import re
from pathlib import Path

# kebab-case: lowercase letters, digits, and hyphens only
_KEBAB_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

# snake_case: lowercase letters, digits, and underscores only
_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")

# Special Python files that don't follow normal naming conventions
_SPECIAL_PY_FILES = frozenset({
    "__init__",
    "__main__",
    "conftest",
    "setup",
})


def _is_skills_file(file_path: str) -> bool:
    """Check if a file is under a skills/ directory."""
    parts = Path(file_path).parts
    return "skills" in parts


def _is_schema_file(file_path: str) -> bool:
    """Check if a file is a schema file (under schemas/ or openspec/schemas/)."""
    parts = Path(file_path).parts
    return "schemas" in parts


def _get_skill_dir_name(file_path: str) -> str | None:
    """Extract the skill directory name from a file path under skills/.

    For a path like 'skills/my-skill/scripts/helper.py', returns 'my-skill'.
    Returns None if not a direct child of skills/.
    """
    parts = Path(file_path).parts
    try:
        skills_idx = list(parts).index("skills")
        if skills_idx + 1 < len(parts):
            candidate = parts[skills_idx + 1]
            # Skip non-directory entries (e.g., direct files in skills/)
            if skills_idx + 2 < len(parts):
                return candidate
        return None
    except ValueError:
        return None


def check_naming_conventions(
    changed_files: list[str],
) -> list[dict]:
    """Check naming conventions for skill directories, script files, and schema files.

    Args:
        changed_files: List of file paths to check.

    Returns:
        List of finding dicts in review-findings schema format.
    """
    findings: list[dict] = []
    finding_id = 1

    # Track which skill dirs we've already reported on
    checked_skill_dirs: set[str] = set()

    for file_path in changed_files:
        path = Path(file_path)

        # Check skill directory naming (kebab-case)
        if _is_skills_file(file_path):
            skill_dir = _get_skill_dir_name(file_path)
            if skill_dir and skill_dir not in checked_skill_dirs:
                checked_skill_dirs.add(skill_dir)
                if not _KEBAB_CASE_RE.match(skill_dir):
                    findings.append({
                        "id": finding_id,
                        "type": "architecture",
                        "criticality": "low",
                        "disposition": "fix",
                        "description": (
                            f"Skill directory '{skill_dir}' does not follow "
                            f"kebab-case naming convention"
                        ),
                        "resolution": (
                            f"Rename the skill directory to kebab-case "
                            f"(e.g., '{skill_dir.replace('_', '-')}' instead of "
                            f"'{skill_dir}'). Skill directories must use "
                            f"lowercase letters, digits, and hyphens only."
                        ),
                        "file_path": str(file_path),
                        "line_range": {"start": 1, "end": 1},
                    })
                    finding_id += 1

        # Check script file naming (snake_case .py)
        if _is_skills_file(file_path) and path.suffix == ".py":
            stem = path.stem
            if stem not in _SPECIAL_PY_FILES:
                if not _SNAKE_CASE_RE.match(stem):
                    findings.append({
                        "id": finding_id,
                        "type": "architecture",
                        "criticality": "low",
                        "disposition": "fix",
                        "description": (
                            f"Script file '{path.name}' does not follow "
                            f"snake_case naming convention"
                        ),
                        "resolution": (
                            f"Rename the script file to snake_case "
                            f"(e.g., '{stem.replace('-', '_')}.py' instead of "
                            f"'{path.name}'). Python script files under skills/ "
                            f"must use lowercase letters, digits, and underscores only."
                        ),
                        "file_path": str(file_path),
                        "line_range": {"start": 1, "end": 1},
                    })
                    finding_id += 1

        # Check schema file naming (kebab-case .json or .yaml/.yml)
        if _is_schema_file(file_path) and path.suffix in (".json", ".yaml", ".yml"):
            # For schema files, strip multi-part extensions like .schema.json
            stem = path.name
            for ext in (".json", ".yaml", ".yml", ".schema"):
                stem = stem.removesuffix(ext)

            if stem and not _KEBAB_CASE_RE.match(stem):
                findings.append({
                    "id": finding_id,
                    "type": "architecture",
                    "criticality": "low",
                    "disposition": "fix",
                    "description": (
                        f"Schema file '{path.name}' does not follow "
                        f"kebab-case naming convention"
                    ),
                    "resolution": (
                        f"Rename the schema file to kebab-case "
                        f"(e.g., '{stem.replace('_', '-')}{path.suffix}' instead of "
                        f"'{path.name}'). Schema files must use "
                        f"lowercase letters, digits, and hyphens only."
                    ),
                    "file_path": str(file_path),
                    "line_range": {"start": 1, "end": 1},
                })
                finding_id += 1

    return findings

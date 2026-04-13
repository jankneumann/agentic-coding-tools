"""Scope enforcement for work package execution.

Validates that files modified by a package are within its declared scope
(write_allow globs) and not in denied areas (deny globs). Uses git diff
for deterministic post-hoc checking per Design Decision #6.

Usage:
    from scope_checker import check_scope_compliance

    result = check_scope_compliance(
        files_modified=["src/api/users.py", "src/api/routes.py"],
        write_allow=["src/api/**", "tests/api/**"],
        deny=["src/frontend/**"],
    )
    assert result["compliant"] is True
"""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Any


def check_scope_compliance(
    files_modified: list[str],
    write_allow: list[str],
    deny: list[str] | None = None,
) -> dict[str, Any]:
    """Check that all modified files comply with scope constraints.

    Args:
        files_modified: List of repo-relative file paths modified by the package.
        write_allow: Glob patterns of files the package is allowed to modify.
        deny: Glob patterns of files explicitly forbidden.

    Returns:
        Dict with keys:
        - compliant: bool — True if all files are within scope
        - violations: list of dicts with file, reason, and matched pattern
        - summary: human-readable summary string
    """
    deny = deny or []
    violations: list[dict[str, str]] = []

    for file_path in files_modified:
        # Check deny first (deny overrides allow)
        denied = False
        for pattern in deny:
            if fnmatch(file_path, pattern):
                violations.append({
                    "file": file_path,
                    "reason": "denied",
                    "pattern": pattern,
                })
                denied = True
                break

        if denied:
            continue

        # Check write_allow
        allowed = False
        for pattern in write_allow:
            if fnmatch(file_path, pattern):
                allowed = True
                break

        if not allowed:
            violations.append({
                "file": file_path,
                "reason": "not_in_write_allow",
                "pattern": "",
            })

    compliant = len(violations) == 0

    if compliant:
        summary = f"Scope check passed: {len(files_modified)} files within scope"
    else:
        denied_count = sum(1 for v in violations if v["reason"] == "denied")
        outside_count = sum(1 for v in violations if v["reason"] == "not_in_write_allow")
        parts = []
        if denied_count:
            parts.append(f"{denied_count} in deny list")
        if outside_count:
            parts.append(f"{outside_count} outside write_allow")
        summary = f"Scope violation: {', '.join(parts)}"

    return {
        "compliant": compliant,
        "violations": violations,
        "summary": summary,
        "files_checked": len(files_modified),
    }


def get_modified_files_from_diff(diff_output: str) -> list[str]:
    """Parse git diff --name-only output into a list of file paths.

    Args:
        diff_output: Output of `git diff --name-only <base>...<head>`

    Returns:
        List of repo-relative file paths.
    """
    return [line.strip() for line in diff_output.strip().splitlines() if line.strip()]

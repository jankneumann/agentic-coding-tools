#!/usr/bin/env python3
"""Quality verifier: run checks after fixes and detect regressions."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))


@dataclass(slots=True)
class VerificationResult:
    """Result of post-fix quality verification."""

    passed: bool
    checks: dict[str, str] = field(default_factory=dict)  # tool -> "pass"/"fail"
    regressions: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": self.checks,
            "regressions": self.regressions,
            "messages": self.messages,
        }


def _run_check(cmd: list[str], cwd: str) -> tuple[bool, str]:
    """Run a check command and return (success, output)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=300,
        )
        return result.returncode == 0, result.stdout + result.stderr
    except FileNotFoundError:
        return True, f"{cmd[0]} not available — skipped"
    except subprocess.TimeoutExpired:
        return False, f"{cmd[0]} timed out after 300s"


def _count_failures(output: str, tool: str) -> set[str]:
    """Extract failure identifiers from tool output for regression detection."""
    failures: set[str] = set()
    if tool == "pytest":
        for line in output.split("\n"):
            if "FAILED" in line:
                failures.add(line.strip())
    elif tool == "mypy":
        for line in output.split("\n"):
            if ": error:" in line:
                failures.add(line.strip())
    elif tool == "ruff":
        try:
            items = json.loads(output)
            for item in items:
                code = item.get("code", "")
                filename = item.get("filename", "")
                row = item.get("location", {}).get("row", 0)
                failures.add(f"{code}:{filename}:{row}")
        except (json.JSONDecodeError, TypeError):
            for line in output.split("\n"):
                if line.strip():
                    failures.add(line.strip())
    return failures


def verify(
    project_dir: str,
    original_failures: dict[str, set[str]] | None = None,
) -> VerificationResult:
    """Run quality checks and detect regressions.

    Args:
        project_dir: Project root directory.
        original_failures: Optional dict of tool -> set of failure IDs from
            the original bug-scrub run, used for regression detection.

    Returns:
        VerificationResult with check outcomes and regressions.
    """
    if original_failures is None:
        original_failures = {}

    checks: dict[str, str] = {}
    regressions: list[str] = []
    messages: list[str] = []

    tools = [
        ("pytest", ["pytest", "-m", "not e2e and not integration", "--tb=line", "-q"]),
        ("mypy", ["mypy", "src/", "--no-error-summary"]),
        ("ruff", ["ruff", "check", "--output-format=json"]),
        ("openspec", ["openspec", "validate", "--strict", "--all"]),
    ]

    for tool_name, cmd in tools:
        success, output = _run_check(cmd, project_dir)
        checks[tool_name] = "pass" if success else "fail"

        if not success and tool_name in original_failures:
            current_failures = _count_failures(output, tool_name)
            new_failures = current_failures - original_failures[tool_name]
            if new_failures:
                regressions.extend(
                    f"[{tool_name}] NEW: {failure}" for failure in sorted(new_failures)
                )

        if "not available" in output or "skipped" in output:
            messages.append(f"{tool_name}: skipped (not available)")

    passed = all(v == "pass" for v in checks.values()) and not regressions

    return VerificationResult(
        passed=passed,
        checks=checks,
        regressions=regressions,
        messages=messages,
    )

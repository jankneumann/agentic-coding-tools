#!/usr/bin/env python3
"""Parallel quality verifier: run checks concurrently after fixes."""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify import VerificationResult, _count_failures, _run_check


def verify_parallel(
    project_dir: str,
    original_failures: dict[str, set[str]] | None = None,
) -> VerificationResult:
    """Run quality checks (pytest, mypy, ruff, openspec) concurrently.

    Returns unified VerificationResult. Matches existing verify() signature
    including original_failures type for regression detection.

    Args:
        project_dir: Project root directory.
        original_failures: Optional dict of tool -> set of failure IDs from
            the original bug-scrub run, used for regression detection.

    Returns:
        VerificationResult with check outcomes and regressions.
    """
    if original_failures is None:
        original_failures = {}

    tools = [
        ("pytest", ["pytest", "-m", "not e2e and not integration", "--tb=line", "-q"]),
        ("mypy", ["mypy", ".", "--no-error-summary"]),
        ("ruff", ["ruff", "check", "--output-format=json"]),
        ("openspec", ["openspec", "validate", "--strict", "--all"]),
    ]

    # Run all checks concurrently and collect results keyed by tool name.
    # Each future maps to (tool_name, success, output).
    results: dict[str, tuple[bool, str]] = {}

    with ThreadPoolExecutor(max_workers=len(tools)) as executor:
        future_to_tool = {
            executor.submit(_run_check, cmd, project_dir): tool_name
            for tool_name, cmd in tools
        }
        for future in as_completed(future_to_tool):
            tool_name = future_to_tool[future]
            results[tool_name] = future.result()

    # Assemble VerificationResult in deterministic tool order.
    checks: dict[str, str] = {}
    regressions: list[str] = []
    messages: list[str] = []

    for tool_name, _ in tools:
        success, output = results[tool_name]
        checks[tool_name] = "pass" if success else "fail"

        if not success and tool_name in original_failures:
            current_failures = _count_failures(output, tool_name)
            new_failures = current_failures - original_failures[tool_name]
            if new_failures:
                regressions.extend(
                    f"[{tool_name}] NEW: {failure}"
                    for failure in sorted(new_failures)
                )

        if "not available" in output:
            messages.append(f"{tool_name}: skipped (not available)")

    passed = all(v == "pass" for v in checks.values()) and not regressions

    return VerificationResult(
        passed=passed,
        checks=checks,
        regressions=regressions,
        messages=messages,
    )

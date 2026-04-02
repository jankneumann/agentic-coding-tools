#!/usr/bin/env python3
"""Smoke test phase runner — run smoke tests and update validation-report.md.

Usage:
    python3 phase_smoke.py [--test-env PATH] [--report PATH]

Design decisions:
- D2: Reads .test-env written by phase_deploy.py
- D7: Appends/replaces ## Smoke Tests section in validation-report.md
- LST.7: On missing .test-env, exit 1 with JSON error to stderr
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def load_test_env(path: str) -> dict[str, str]:
    """Load a .test-env file and return a dict of key=value pairs.

    Args:
        path: Path to the .test-env file

    Returns:
        Dict of environment variable key-value pairs

    Raises:
        FileNotFoundError: If the file doesn't exist
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f".test-env file not found: {path}")

    result: dict[str, str] = {}
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        result[key] = value
    return result


def run_smoke_tests(env_vars: dict[str, str]) -> tuple[int, str, str]:
    """Run pytest on the smoke test suite with given env vars.

    Args:
        env_vars: Environment variables to set for the pytest process

    Returns:
        Tuple of (returncode, stdout, stderr)
    """
    # Merge with current env, overlaying test env vars
    test_env = {**os.environ, **env_vars}

    # Find the smoke_tests directory relative to this script
    scripts_dir = Path(__file__).resolve().parent
    smoke_tests_dir = scripts_dir / "smoke_tests"

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(smoke_tests_dir),
        "-v",
        "--tb=short",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        env=test_env,
    )

    return result.returncode, result.stdout, result.stderr


def parse_pytest_output(output: str) -> list[dict[str, str]]:
    """Parse pytest verbose output for per-test results.

    Args:
        output: pytest stdout

    Returns:
        List of dicts with 'test', 'status', 'duration' keys
    """
    results: list[dict[str, str]] = []

    # Match lines like: test_health.py::test_health_endpoint PASSED [50%]
    pattern = re.compile(r"^(\S+::\S+)\s+(PASSED|FAILED|ERROR|SKIPPED)", re.MULTILINE)

    for match in pattern.finditer(output):
        test_name = match.group(1)
        raw_status = match.group(2)

        status_map = {
            "PASSED": "pass",
            "FAILED": "fail",
            "ERROR": "fail",
            "SKIPPED": "skipped",
        }

        results.append({
            "test": test_name,
            "status": status_map.get(raw_status, "fail"),
            "duration": "—",
        })

    return results


def append_smoke_section(
    report_path: str,
    status: str,
    env_type: str,
    duration_seconds: float,
    results: list[dict[str, str]],
    failure_output: str = "",
) -> None:
    """Append or replace ## Smoke Tests section in validation-report.md.

    Args:
        report_path: Path to validation-report.md
        status: "pass", "fail", or "skipped"
        env_type: "docker" or "neon"
        duration_seconds: Total test duration
        results: Per-test results from parse_pytest_output()
        failure_output: Raw pytest output for failures (optional)
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build the smoke section
    section_lines = [
        "## Smoke Tests",
        "",
        f"- **Status**: {status}",
        f"- **Environment**: {env_type}",
        f"- **Timestamp**: {timestamp}",
        f"- **Duration**: {duration_seconds}s",
        "",
    ]

    if results:
        section_lines.extend([
            "### Results",
            "",
            "| Test | Status | Duration |",
            "|------|--------|----------|",
        ])
        for r in results:
            section_lines.append(
                f"| {r['test']} | {r['status']} | {r.get('duration', '—')} |"
            )
        section_lines.append("")

    if failure_output:
        section_lines.extend([
            "### Failures",
            "",
            "```",
            failure_output.strip(),
            "```",
            "",
        ])

    smoke_section = "\n".join(section_lines)

    # Read existing report content (if any)
    report = Path(report_path)
    if report.exists():
        content = report.read_text()
    else:
        content = ""

    # Remove existing ## Smoke Tests section if present
    if "## Smoke Tests" in content:
        # Find the section boundaries
        # Split on ## headings to find and replace the Smoke Tests section
        parts = re.split(r"(^## )", content, flags=re.MULTILINE)

        new_parts: list[str] = []
        skip = False
        for i, part in enumerate(parts):
            if part == "## ":
                # Check the next part to see if it starts with "Smoke Tests"
                if i + 1 < len(parts) and parts[i + 1].startswith("Smoke Tests"):
                    skip = True
                    continue
                else:
                    skip = False
                    new_parts.append(part)
            elif skip:
                skip = False
                continue
            else:
                new_parts.append(part)

        content = "".join(new_parts).rstrip()
        if content:
            content += "\n\n"
        content += smoke_section
    else:
        # Append to end
        if content and not content.endswith("\n"):
            content += "\n"
        if content:
            content += "\n"
        content += smoke_section

    report.write_text(content)
    logger.info("Wrote smoke test results to %s (status=%s)", report_path, status)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="phase_smoke",
        description="Smoke phase: run smoke tests and update validation-report.md",
    )
    parser.add_argument(
        "--test-env",
        default=".test-env",
        help="Path to .test-env file (default: .test-env)",
    )
    parser.add_argument(
        "--report",
        default="validation-report.md",
        help="Path to validation-report.md (default: validation-report.md)",
    )
    return parser


def main() -> None:
    """CLI entry point for phase_smoke."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = build_parser()
    args = parser.parse_args()

    # Load .test-env
    try:
        env_vars = load_test_env(args.test_env)
    except FileNotFoundError as exc:
        error_payload = {
            "error": str(exc),
            "phase": "smoke",
        }
        print(json.dumps(error_payload), file=sys.stderr)
        sys.exit(1)

    env_type = env_vars.get("TEST_ENV_TYPE", "unknown")

    # Run smoke tests
    start_time = time.monotonic()
    returncode, stdout, stderr = run_smoke_tests(env_vars)
    duration = round(time.monotonic() - start_time, 1)

    # Parse results
    results = parse_pytest_output(stdout)

    # Determine overall status
    if returncode == 0:
        status = "pass"
    else:
        status = "fail"

    # Write report
    append_smoke_section(
        report_path=args.report,
        status=status,
        env_type=env_type,
        duration_seconds=duration,
        results=results,
        failure_output=stderr if status == "fail" else "",
    )

    logger.info("Smoke phase complete: status=%s", status)


if __name__ == "__main__":
    main()

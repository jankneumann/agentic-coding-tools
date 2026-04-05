"""Gate logic for validation pipeline — soft and hard gates.

Parses validation-report.md for phase sections and determines
whether the pipeline should continue or halt.

Design decision D7: Gates check validation-report.md for
phase sections with **Status**: pass/fail/skipped.

Functions:
    check_phase_status(report_path, section) -> 'pass' | 'fail' | 'skipped' | 'missing'
    check_smoke_status(report_path) -> 'pass' | 'fail' | 'skipped' | 'missing'
    soft_gate(report_path) -> (action, reason)   # action always 'continue'
    hard_gate(report_path) -> (action, reason)   # action 'continue' or 'halt'
    pre_merge_gate(report_path, force=False) -> (action, reason, details)
"""

from __future__ import annotations

import re
from pathlib import Path

# Phases that must pass before merge is allowed.
# Maps section heading -> human-readable name.
REQUIRED_PHASES: dict[str, str] = {
    "Smoke Tests": "Smoke tests",
    "Security": "Security scan",
    "E2E Tests": "E2E tests",
}


def check_phase_status(report_path: str, section_heading: str) -> str:
    """Parse validation-report.md for a phase's status.

    Args:
        report_path: Path to validation-report.md
        section_heading: The ## heading to look for (e.g. "Smoke Tests")

    Returns:
        'pass', 'fail', 'skipped', or 'missing'
    """
    p = Path(report_path)
    if not p.exists():
        return "missing"

    content = p.read_text()

    if f"## {section_heading}" not in content:
        return "missing"

    # Extract section content between ## heading and next ## heading (or EOF)
    pattern = rf"## {re.escape(section_heading)}\s*\n(.*?)(?=\n## |\Z)"
    section_match = re.search(pattern, content, re.DOTALL)

    if not section_match:
        return "missing"

    section_content = section_match.group(1)

    # Look for **Status**: line
    status_match = re.search(
        r"\*\*Status\*\*:\s*(pass|fail|skipped)",
        section_content,
    )

    if not status_match:
        return "missing"

    return status_match.group(1)


def check_smoke_status(report_path: str) -> str:
    """Parse validation-report.md for smoke test status.

    Convenience wrapper around check_phase_status for backward compatibility.

    Args:
        report_path: Path to validation-report.md

    Returns:
        'pass', 'fail', 'skipped', or 'missing'
    """
    return check_phase_status(report_path, "Smoke Tests")


def soft_gate(report_path: str) -> tuple[str, str]:
    """Soft gate for /implement-feature — always continues.

    Args:
        report_path: Path to validation-report.md

    Returns:
        Tuple of (action, reason).
        action is always 'continue'.
    """
    status = check_smoke_status(report_path)

    if status == "pass":
        return ("continue", "Smoke tests passed.")
    elif status == "fail":
        return ("continue", "WARNING: Smoke tests failed. Continuing (soft gate).")
    elif status == "skipped":
        return ("continue", "WARNING: Smoke tests skipped. Continuing (soft gate).")
    else:  # missing
        return ("continue", "Smoke tests not yet run. Will trigger deploy+smoke.")


def hard_gate(report_path: str) -> tuple[str, str]:
    """Hard gate for /cleanup-feature — blocks on non-pass status.

    Args:
        report_path: Path to validation-report.md

    Returns:
        Tuple of (action, reason).
        action is 'continue' only if status is 'pass', otherwise 'halt'.
    """
    status = check_smoke_status(report_path)

    if status == "pass":
        return ("continue", "Smoke tests passed. Proceeding to merge.")
    elif status == "fail":
        return ("halt", "Smoke tests failed. Re-run required before merge.")
    elif status == "skipped":
        return ("halt", "Smoke tests were skipped. Re-run required before merge.")
    else:  # missing
        return ("halt", "Smoke tests missing. Run deploy+smoke before merge.")


def pre_merge_gate(
    report_path: str,
    *,
    force: bool = False,
) -> tuple[str, str, dict[str, str]]:
    """Full pre-merge gate — checks all required phases.

    Returns exit-code-compatible result: 'continue' means merge is allowed,
    'halt' means merge is blocked.

    Args:
        report_path: Path to validation-report.md
        force: If True, override the gate (explicit user bypass).

    Returns:
        Tuple of (action, reason, phase_statuses).
        phase_statuses maps phase name -> status string.
    """
    phase_statuses: dict[str, str] = {}
    failures: list[str] = []

    for heading, label in REQUIRED_PHASES.items():
        status = check_phase_status(report_path, heading)
        phase_statuses[heading] = status

        if status != "pass":
            failures.append(f"{label}: {status}")

    if not failures:
        return (
            "continue",
            "All required phases passed. Proceeding to merge.",
            phase_statuses,
        )

    failure_summary = "; ".join(failures)

    if force:
        return (
            "continue",
            f"FORCED OVERRIDE — merging despite failures: {failure_summary}",
            phase_statuses,
        )

    return (
        "halt",
        f"Pre-merge gate failed. {failure_summary}. "
        "Re-run failed phases or use --force to override.",
        phase_statuses,
    )


def main() -> None:
    """CLI entry point for pre-merge gate check.

    Usage:
        python gate_logic.py <report_path> [--force]

    Exit codes:
        0 — merge allowed
        1 — merge blocked
    """
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description="Pre-merge gate: check all required validation phases.",
    )
    parser.add_argument("report_path", help="Path to validation-report.md")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Override gate (explicit user bypass)",
    )
    args = parser.parse_args()

    action, reason, statuses = pre_merge_gate(
        args.report_path, force=args.force,
    )

    result = {
        "action": action,
        "reason": reason,
        "phase_statuses": statuses,
        "force": args.force,
    }
    print(json.dumps(result, indent=2))
    sys.exit(0 if action == "continue" else 1)


if __name__ == "__main__":
    main()

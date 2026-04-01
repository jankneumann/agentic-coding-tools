"""Gate logic for validation pipeline — soft and hard gates.

Parses validation-report.md for ## Smoke Tests section and determines
whether the pipeline should continue or halt.

Design decision D7: Gates check validation-report.md for a
## Smoke Tests section with Status: pass/fail/skipped.

Functions:
    check_smoke_status(report_path) -> 'pass' | 'fail' | 'skipped' | 'missing'
    soft_gate(report_path) -> (action, reason)   # action always 'continue'
    hard_gate(report_path) -> (action, reason)   # action 'continue' or 'halt'
"""

from __future__ import annotations

import re
from pathlib import Path


def check_smoke_status(report_path: str) -> str:
    """Parse validation-report.md for smoke test status.

    Args:
        report_path: Path to validation-report.md

    Returns:
        'pass', 'fail', 'skipped', or 'missing'
    """
    p = Path(report_path)
    if not p.exists():
        return "missing"

    content = p.read_text()

    # Check for ## Smoke Tests section
    if "## Smoke Tests" not in content:
        return "missing"

    # Extract the Smoke Tests section content
    # Find content between ## Smoke Tests and the next ## heading (or EOF)
    smoke_match = re.search(
        r"## Smoke Tests\s*\n(.*?)(?=\n## |\Z)",
        content,
        re.DOTALL,
    )

    if not smoke_match:
        return "missing"

    section_content = smoke_match.group(1)

    # Look for Status: line
    status_match = re.search(
        r"\*\*Status\*\*:\s*(pass|fail|skipped)",
        section_content,
    )

    if not status_match:
        return "missing"

    return status_match.group(1)


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

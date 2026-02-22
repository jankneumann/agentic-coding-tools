#!/usr/bin/env python3
"""Signal collector: ruff linter.

Runs ``ruff check --output-format=json`` against a project directory and
parses the JSON output into Finding objects for the bug-scrub report.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from models import Finding, SourceResult

SOURCE = "ruff"
CATEGORY = "lint"


def _map_severity(code: str) -> str:
    """Map a ruff rule code to a finding severity.

    Rules prefixed with ``E`` (pycodestyle errors) or those flagged as actual
    errors by ruff are mapped to ``"high"``; ``W`` prefixes (warnings) and
    everything else map to ``"medium"``.
    """
    if code.upper().startswith("E"):
        return "high"
    if code.upper().startswith("W"):
        return "medium"
    return "medium"


def collect(project_dir: str) -> SourceResult:
    """Run ruff and return a :class:`SourceResult` with parsed findings.

    Parameters
    ----------
    project_dir:
        Absolute or relative path to the project root to lint.

    Returns
    -------
    SourceResult
        ``status`` is ``"ok"`` on success (even if findings exist),
        ``"skipped"`` when ruff is not installed, or ``"error"`` on
        unexpected failures.
    """
    start = time.monotonic()

    # ------------------------------------------------------------------
    # Guard: is ruff available?
    # ------------------------------------------------------------------
    try:
        subprocess.run(
            ["ruff", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        elapsed = int((time.monotonic() - start) * 1000)
        return SourceResult(
            source=SOURCE,
            status="skipped",
            duration_ms=elapsed,
            messages=["ruff is not installed or not on PATH"],
        )

    # ------------------------------------------------------------------
    # Run ruff check
    # ------------------------------------------------------------------
    result = subprocess.run(
        ["ruff", "check", "--output-format=json", "."],
        capture_output=True,
        text=True,
        cwd=project_dir,
    )

    elapsed = int((time.monotonic() - start) * 1000)

    # ruff exits 0 when no issues are found, 1 when issues are found.
    # Both are normal.  Any other exit code is an unexpected error.
    if result.returncode not in (0, 1):
        return SourceResult(
            source=SOURCE,
            status="error",
            duration_ms=elapsed,
            messages=[
                f"ruff exited with code {result.returncode}",
                result.stderr.strip() if result.stderr else "",
            ],
        )

    # ------------------------------------------------------------------
    # Parse JSON output
    # ------------------------------------------------------------------
    findings: list[Finding] = []
    raw_output = result.stdout.strip()

    if raw_output:
        try:
            diagnostics = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            return SourceResult(
                source=SOURCE,
                status="error",
                duration_ms=elapsed,
                messages=[f"Failed to parse ruff JSON output: {exc}"],
            )

        for diag in diagnostics:
            code: str = diag.get("code", "unknown")
            filename: str = diag.get("filename", "unknown")
            line: int = diag.get("location", {}).get("row", 0)
            message: str = diag.get("message", "")

            # Normalise the file path to be relative to project_dir so
            # the finding IDs are stable regardless of cwd.
            try:
                rel = str(Path(filename).relative_to(Path(project_dir).resolve()))
            except ValueError:
                rel = filename

            finding_id = f"ruff-{code}-{rel}:{line}"

            findings.append(
                Finding(
                    id=finding_id,
                    source=SOURCE,
                    severity=_map_severity(code),  # type: ignore[arg-type]
                    category=CATEGORY,  # type: ignore[arg-type]
                    title=f"{code}: {message}",
                    detail=message,
                    file_path=rel,
                    line=line if line else None,
                )
            )

    return SourceResult(
        source=SOURCE,
        status="ok",
        findings=findings,
        duration_ms=elapsed,
    )

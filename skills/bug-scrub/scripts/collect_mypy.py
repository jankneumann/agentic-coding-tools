#!/usr/bin/env python3
"""Signal collector: mypy type-checker.

Runs ``mypy src/ --no-error-summary`` against *project_dir* and parses the
diagnostics into Finding objects with severity "medium", source "mypy", and
category "type-error".

If mypy is not installed or otherwise unavailable the collector returns a
SourceResult with status "skipped" so the overall scrub can proceed.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

from models import Finding, SourceResult

# mypy output: file.py:42: error: Incompatible types [assignment]
_LINE_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):\s*error:\s*(?P<message>.+?)(?:\s*\[(?P<code>[^\]]+)\])?\s*$"
)


def collect(project_dir: str) -> SourceResult:
    """Run mypy and return parsed findings.

    Parameters
    ----------
    project_dir:
        Absolute path to the project root that contains ``src/``.

    Returns
    -------
    SourceResult
        Findings extracted from mypy output, or a "skipped" result when mypy
        is not available.
    """
    source = "mypy"

    # ------------------------------------------------------------------
    # Guard: ensure mypy is available
    # ------------------------------------------------------------------
    if shutil.which("mypy") is None:
        return SourceResult(
            source=source,
            status="skipped",
            messages=["mypy not found on PATH"],
        )

    # ------------------------------------------------------------------
    # Run mypy
    # ------------------------------------------------------------------
    start = time.monotonic()
    try:
        proc = subprocess.run(
            ["mypy", "src/", "--no-error-summary"],
            capture_output=True,
            text=True,
            cwd=project_dir,
        )
    except (OSError, FileNotFoundError) as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        return SourceResult(
            source=source,
            status="skipped",
            duration_ms=duration_ms,
            messages=[f"Failed to run mypy: {exc}"],
        )
    duration_ms = int((time.monotonic() - start) * 1000)

    # ------------------------------------------------------------------
    # Parse output
    # ------------------------------------------------------------------
    findings: list[Finding] = []
    for raw_line in proc.stdout.splitlines():
        m = _LINE_RE.match(raw_line)
        if m is None:
            continue

        file_path = m.group("file")
        line_no = int(m.group("line"))
        message = m.group("message").strip()
        code = m.group("code") or "unknown"

        filename = Path(file_path).name
        finding_id = f"mypy-{code}-{filename}:{line_no}"

        findings.append(
            Finding(
                id=finding_id,
                source=source,
                severity="medium",
                category="type-error",
                title=message,
                detail=raw_line.strip(),
                file_path=file_path,
                line=line_no,
            )
        )

    return SourceResult(
        source=source,
        status="ok",
        findings=findings,
        duration_ms=duration_ms,
    )

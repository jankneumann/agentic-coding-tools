#!/usr/bin/env python3
"""Signal collector: pytest failures.

Runs pytest with ``-m "not e2e and not integration" --tb=line -q`` inside the
given *project_dir* and parses failures into :class:`Finding` objects.

Each finding is tagged ``severity="high"``, ``source="pytest"``,
``category="test-failure"`` with an ID of ``pytest-{test_name}``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time

from models import Finding, SourceResult

_SOURCE = "pytest"

# Matches the one-line failure summary produced by ``--tb=line``.
# Example:
#   FAILED tests/test_foo.py::test_bar - AssertionError: expected 1 got 2
_FAILURE_RE = re.compile(
    r"^FAILED\s+(?P<nodeid>\S+?)(?:\s+-\s+(?P<reason>.+))?$",
)

# Matches the short-form failure line that ``--tb=line`` emits *above* the
# summary block, e.g.:
#   /abs/path/tests/test_foo.py:42: AssertionError
_TB_LINE_RE = re.compile(
    r"^(?P<path>[^\s:]+):(?P<lineno>\d+):\s+(?P<exc>.+)$",
)


def _test_name_from_nodeid(nodeid: str) -> str:
    """Extract a concise test name from a pytest node ID.

    ``tests/test_foo.py::TestClass::test_bar`` -> ``TestClass::test_bar``
    ``tests/test_foo.py::test_bar``             -> ``test_bar``
    """
    parts = nodeid.split("::")
    if len(parts) >= 2:
        return "::".join(parts[1:])
    return nodeid


def collect(project_dir: str) -> SourceResult:
    """Run pytest and return parsed failures as a :class:`SourceResult`."""

    # ------------------------------------------------------------------
    # Guard: pytest must be available
    # ------------------------------------------------------------------
    if shutil.which("pytest") is None:
        return SourceResult(
            source=_SOURCE,
            status="skipped",
            messages=["pytest not found on PATH"],
        )

    # ------------------------------------------------------------------
    # Run pytest
    # ------------------------------------------------------------------
    cmd = [
        "pytest",
        "-m",
        "not e2e and not integration",
        "--tb=line",
        "-q",
    ]

    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=project_dir,
            timeout=300,
        )
    except FileNotFoundError:
        return SourceResult(
            source=_SOURCE,
            status="skipped",
            duration_ms=int((time.monotonic() - start) * 1000),
            messages=["pytest executable not found"],
        )
    except subprocess.TimeoutExpired:
        return SourceResult(
            source=_SOURCE,
            status="error",
            duration_ms=int((time.monotonic() - start) * 1000),
            messages=["pytest timed out after 300 seconds"],
        )
    except subprocess.SubprocessError as exc:
        return SourceResult(
            source=_SOURCE,
            status="error",
            duration_ms=int((time.monotonic() - start) * 1000),
            messages=[f"subprocess error: {exc}"],
        )

    duration_ms = int((time.monotonic() - start) * 1000)

    # ------------------------------------------------------------------
    # Exit code 0 -> no failures; exit code 5 -> no tests collected.
    # Both are non-error states with zero findings.
    # ------------------------------------------------------------------
    if result.returncode in (0, 5):
        messages: list[str] = []
        if result.returncode == 5:
            messages.append("no tests were collected")
        return SourceResult(
            source=_SOURCE,
            status="ok",
            duration_ms=duration_ms,
            messages=messages,
        )

    # ------------------------------------------------------------------
    # Parse ``--tb=line`` traceback lines for file/line metadata
    # ------------------------------------------------------------------
    combined_output = result.stdout + "\n" + result.stderr
    lines = combined_output.splitlines()

    # Map nodeid fragments -> (file_path, line_number, exception text)
    tb_info: dict[str, tuple[str, int, str]] = {}
    for line in lines:
        m = _TB_LINE_RE.match(line.strip())
        if m:
            path = m.group("path")
            lineno = int(m.group("lineno"))
            exc = m.group("exc")
            tb_info[path] = (path, lineno, exc)

    # ------------------------------------------------------------------
    # Parse FAILED lines
    # ------------------------------------------------------------------
    findings: list[Finding] = []
    for line in lines:
        m = _FAILURE_RE.match(line.strip())
        if not m:
            continue

        nodeid = m.group("nodeid")
        reason = m.group("reason") or ""
        test_name = _test_name_from_nodeid(nodeid)

        # Try to find traceback info for this failure.
        # The nodeid starts with the file path (e.g. tests/test_foo.py).
        file_path = nodeid.split("::")[0] if "::" in nodeid else ""
        line_number: int | None = None
        detail = reason

        # Match tb_info by file path prefix.
        for tb_path, (fpath, lineno, exc) in tb_info.items():
            if tb_path == file_path or tb_path.endswith(file_path):
                file_path = fpath
                line_number = lineno
                if not detail:
                    detail = exc
                break

        findings.append(
            Finding(
                id=f"pytest-{test_name}",
                source=_SOURCE,
                severity="high",
                category="test-failure",
                title=f"Test failure: {test_name}",
                detail=detail,
                file_path=file_path,
                line=line_number,
            )
        )

    # ------------------------------------------------------------------
    # If pytest returned a failure exit code but we parsed zero FAILED
    # lines, report a generic error so the signal is not silently lost.
    # ------------------------------------------------------------------
    if result.returncode != 0 and not findings:
        return SourceResult(
            source=_SOURCE,
            status="error",
            duration_ms=duration_ms,
            messages=[
                f"pytest exited with code {result.returncode} "
                "but no FAILED lines were parsed",
                result.stdout[-500:] if result.stdout else "",
                result.stderr[-500:] if result.stderr else "",
            ],
        )

    return SourceResult(
        source=_SOURCE,
        status="ok",
        findings=findings,
        duration_ms=duration_ms,
    )

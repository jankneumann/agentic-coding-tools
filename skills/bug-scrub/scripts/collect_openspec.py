#!/usr/bin/env python3
"""Signal collector: OpenSpec validation.

Runs ``openspec validate --strict --all`` in a project directory and parses
the output into Finding objects with category "spec-violation".  When
``openspec`` is not installed or not on PATH the collector returns a
SourceResult with status "skipped" so the bug-scrub pipeline continues
without failing.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time

from models import Finding, SourceResult

_SOURCE = "openspec"
_CATEGORY = "spec-violation"
_SEVERITY = "medium"

# Patterns observed in openspec validate output.  Lines that start with
# a severity token (error/warning) followed by a colon carry the actual
# finding text.  Example:
#   error: REQ-001 has no acceptance criteria (spec: specs/core.yaml:12)
#   warning: Change 2025-001 proposal is missing test plan
_LINE_RE = re.compile(
    r"^\s*(?:error|warning|Error|Warning|ERROR|WARNING)\s*:\s*(.+)",
)

# Optional file/line reference at the end of a finding message.
# Example: (spec: specs/core.yaml:12)  or  (file: path/to/thing.md:5)
_LOC_RE = re.compile(
    r"\((?:spec|file):\s*([^:)]+)(?::(\d+))?\)\s*$",
)


def _slugify(text: str, max_len: int = 40) -> str:
    """Turn a short text fragment into a safe identifier slug."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    return slug.strip("-")[:max_len]


def _parse_findings(output: str) -> list[Finding]:
    """Extract findings from openspec validate stdout/stderr."""
    findings: list[Finding] = []
    for idx, line in enumerate(output.splitlines()):
        m = _LINE_RE.match(line)
        if not m:
            continue
        message = m.group(1).strip()

        file_path = ""
        line_no: int | None = None
        loc = _LOC_RE.search(message)
        if loc:
            file_path = loc.group(1)
            if loc.group(2):
                line_no = int(loc.group(2))
            # Strip the location reference from the title.
            message = message[: loc.start()].rstrip()

        snippet = _slugify(message)
        finding_id = f"openspec-{idx}-{snippet}"

        findings.append(
            Finding(
                id=finding_id,
                source=_SOURCE,
                severity=_SEVERITY,
                category=_CATEGORY,
                title=message,
                detail=line.strip(),
                file_path=file_path,
                line=line_no,
            ),
        )
    return findings


def collect(project_dir: str) -> SourceResult:
    """Run openspec validate and return parsed findings.

    Parameters
    ----------
    project_dir:
        Absolute path to the project root where ``openspec validate`` should
        be executed.

    Returns
    -------
    SourceResult
        * status ``"ok"`` when the command ran (even with validation errors).
        * status ``"skipped"`` when ``openspec`` is not found on PATH.
        * status ``"error"`` on unexpected failures.
    """
    # Guard: check that the openspec CLI is available.
    if shutil.which("openspec") is None:
        return SourceResult(
            source=_SOURCE,
            status="skipped",
            messages=["openspec CLI not found on PATH"],
        )

    start = time.monotonic()
    try:
        result = subprocess.run(
            ["openspec", "validate", "--strict", "--all"],
            capture_output=True,
            text=True,
            cwd=project_dir,
            timeout=120,
        )
    except FileNotFoundError:
        # Belt-and-suspenders: shutil.which passed but exec failed.
        elapsed = int((time.monotonic() - start) * 1000)
        return SourceResult(
            source=_SOURCE,
            status="skipped",
            duration_ms=elapsed,
            messages=["openspec CLI not available (FileNotFoundError)"],
        )
    except subprocess.TimeoutExpired:
        elapsed = int((time.monotonic() - start) * 1000)
        return SourceResult(
            source=_SOURCE,
            status="error",
            duration_ms=elapsed,
            messages=["openspec validate timed out after 120 s"],
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = int((time.monotonic() - start) * 1000)
        return SourceResult(
            source=_SOURCE,
            status="error",
            duration_ms=elapsed,
            messages=[f"unexpected error running openspec validate: {exc}"],
        )

    elapsed = int((time.monotonic() - start) * 1000)
    combined_output = f"{result.stdout}\n{result.stderr}"
    findings = _parse_findings(combined_output)

    messages: list[str] = []
    if result.returncode != 0:
        messages.append(
            f"openspec validate exited with code {result.returncode}"
        )

    return SourceResult(
        source=_SOURCE,
        status="ok",
        findings=findings,
        duration_ms=elapsed,
        messages=messages,
    )

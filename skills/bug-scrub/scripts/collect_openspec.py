#!/usr/bin/env python3
"""Signal collector: OpenSpec validation.

Runs ``openspec validate --strict --all --json`` in a project directory and
turns each reported issue into a Finding with category "spec-violation".  When
``openspec`` is not installed or not on PATH the collector returns a
SourceResult with status "skipped" so the bug-scrub pipeline continues
without failing.

Why --json: the human-readable output of ``--all`` carries no per-issue detail
at all -- just a tick per item and a totals line -- so there is nothing there
to scrape.  The JSON envelope is versioned ("version": "1.0") and reports each
issue's level, path, and message.  An earlier version of this collector
matched ``error: <msg>`` against the text output, a shape no release of the
CLI has ever emitted; it therefore reported zero spec violations on every run,
indistinguishable from a clean repository.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time

from models import Finding, SourceResult

_SOURCE = "openspec"
_CATEGORY = "spec-violation"

# openspec issue levels -> bug-scrub severities.  INFO covers advisory notes
# such as "Requirement text is very long"; it maps to "info" so the pipeline's
# default severity filter ("low") excludes it from the report body while still
# counting it in filtered_out_count.  Unknown levels are treated as medium so
# a new level is surfaced rather than dropped.
_SEVERITY_BY_LEVEL = {
    "ERROR": "high",
    "WARNING": "medium",
    "INFO": "info",
}
_DEFAULT_SEVERITY = "medium"


def _slugify(text: str, max_len: int = 40) -> str:
    """Turn a short text fragment into a safe identifier slug."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    return slug.strip("-")[:max_len]


def _candidate_paths(path: str, item_type: str, item_id: str) -> list[str]:
    """Repository-relative candidates for an issue's item-relative ``path``.

    openspec reports a file-shaped path relative to the *item*, not the
    repository root.  A change's "probe-cap/spec.md" lives at
    ``openspec/changes/<id>/specs/probe-cap/spec.md``; a spec's would live
    under ``openspec/specs/<id>/``.  Ordered most- to least-likely, plus the
    raw value last in case a future CLI starts reporting repo-relative paths.
    """
    candidates: list[str] = []
    if item_type == "change":
        candidates.append(f"openspec/changes/{item_id}/specs/{path}")
        # Non-delta files of a change (proposal.md, tasks.md) sit one level up.
        candidates.append(f"openspec/changes/{item_id}/{path}")
    elif item_type == "spec":
        candidates.append(f"openspec/specs/{item_id}/{path}")
    candidates.append(path)
    return candidates


def _as_file_path(
    path: str, item_type: str, item_id: str, project_dir: str
) -> str:
    """Resolve an issue's ``path`` to a repository-relative file, else "".

    An issue's ``path`` is either a file relative to its item ("probe-cap/
    spec.md") or a structural pointer into the parsed document
    ("requirements[0]", "overview", "file").  Only the former belongs in
    Finding.file_path -- reporting a pointer as a file path sends fix-scrub
    looking for a file that does not exist.

    A file-shaped path is resolved against the item it belongs to and returned
    only if it is actually on disk.  An unresolvable path yields "" rather than
    a plausible-looking guess, for the same reason: a wrong path is worse than
    no path.  The raw pointer survives in the finding's detail either way.
    """
    if not path or "[" in path:
        return ""
    if "." not in path.rsplit("/", 1)[-1]:
        return ""

    for candidate in _candidate_paths(path, item_type, item_id):
        if os.path.isfile(os.path.join(project_dir, candidate)):
            return candidate
    return ""


def _parse_findings(payload: dict, project_dir: str) -> list[Finding]:
    """Extract findings from a parsed ``openspec validate --json`` payload."""
    findings: list[Finding] = []
    for item in payload.get("items", []):
        item_id = str(item.get("id", "?"))
        item_type = str(item.get("type", "item"))
        for idx, issue in enumerate(item.get("issues", []) or []):
            level = str(issue.get("level", "")).upper()
            message = str(issue.get("message", "")).strip()
            if not message:
                continue
            path = str(issue.get("path", "")).strip()

            findings.append(
                Finding(
                    id=(
                        f"openspec-{item_type}-{item_id}-{idx}-"
                        f"{_slugify(message)}"
                    ),
                    source=_SOURCE,
                    severity=_SEVERITY_BY_LEVEL.get(level, _DEFAULT_SEVERITY),
                    category=_CATEGORY,
                    title=message,
                    # The item id is what `openspec validate <id>` takes, so
                    # keep it in the detail line to make the finding actionable.
                    detail=(
                        f"{level or 'ISSUE'} in {item_type}/{item_id}"
                        f"{f' at {path}' if path else ''}: {message}"
                    ),
                    file_path=_as_file_path(
                        path, item_type, item_id, project_dir
                    ),
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
            ["openspec", "validate", "--strict", "--all", "--json"],
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

    # Report a parse failure as an error carrying the raw output.  Returning
    # ok/no-findings here would be a silent pass: a collector that did not
    # understand the tool would look exactly like a clean repository, which is
    # how the previous parser's total blindness went unnoticed.
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raw = f"{result.stdout}\n{result.stderr}".strip()
        return SourceResult(
            source=_SOURCE,
            status="error",
            duration_ms=elapsed,
            messages=[
                f"could not parse openspec validate JSON output: {exc}",
                f"raw output: {raw}",
            ],
        )

    if not isinstance(payload, dict):
        return SourceResult(
            source=_SOURCE,
            status="error",
            duration_ms=elapsed,
            messages=[
                "unexpected openspec validate JSON output: expected an "
                f"object, got {type(payload).__name__}",
                f"raw output: {result.stdout.strip()}",
            ],
        )

    findings = _parse_findings(payload, project_dir)

    messages: list[str] = []
    if result.returncode != 0:
        messages.append(
            f"openspec validate exited with code {result.returncode}"
        )
    if result.stderr.strip():
        messages.append(f"stderr: {result.stderr.strip()}")

    return SourceResult(
        source=_SOURCE,
        status="ok",
        findings=findings,
        duration_ms=elapsed,
        messages=messages,
    )

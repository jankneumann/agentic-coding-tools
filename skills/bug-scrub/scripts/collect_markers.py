#!/usr/bin/env python3
"""Signal collector: TODO/FIXME/HACK/XXX code markers.

Scans all ``*.py`` files under a project directory for comment lines containing
TODO, FIXME, HACK, or XXX markers.  Each match produces a Finding with source
``"markers"`` and category ``"code-marker"``.

Severity mapping:
- FIXME, HACK -> "medium" (actionable debt)
- TODO, XXX   -> "low"    (informational notes)

File age is estimated via ``git log -1 --format=%ai -- <file>`` to avoid the
expense of per-line git blame.  If git is unavailable the collector still runs
but omits ``age_days``.
"""

from __future__ import annotations

import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from models import Finding, SourceResult

SOURCE = "markers"
CATEGORY = "code-marker"

SKIP_DIRS = {".venv", "node_modules", "__pycache__", ".git"}

# Match comment lines containing a marker keyword with optional colon.
# Group 1: marker type, Group 2: trailing text after the keyword (and colon).
_MARKER_RE = re.compile(
    r"#\s*(TODO|FIXME|HACK|XXX)\s*:?\s*(.*)", re.IGNORECASE
)

_SEVERITY: dict[str, str] = {
    "todo": "low",
    "fixme": "medium",
    "hack": "medium",
    "xxx": "low",
}


def _git_available(project_dir: str) -> bool:
    """Return True when git is usable inside *project_dir*."""
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            check=True,
            cwd=project_dir,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    return True


def _file_age_days(filepath: Path, project_dir: str) -> int | None:
    """Return age in days since the file was last touched in git."""
    try:
        proc = subprocess.run(
            ["git", "log", "-1", "--format=%ai", "--", str(filepath)],
            capture_output=True,
            text=True,
            cwd=project_dir,
        )
    except (FileNotFoundError, OSError):
        return None

    date_str = proc.stdout.strip()
    if not date_str:
        return None

    try:
        last_commit = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S %z")
        delta = datetime.now(timezone.utc) - last_commit
        return max(int(delta.total_seconds() / 86400), 0)
    except (ValueError, TypeError):
        return None


def _should_skip(path: Path) -> bool:
    """Return True if any path component is in the skip set."""
    return bool(SKIP_DIRS.intersection(path.parts))


def collect(project_dir: str) -> SourceResult:
    """Scan Python files for TODO/FIXME/HACK/XXX markers.

    Parameters
    ----------
    project_dir:
        Absolute or relative path to the project root to scan.

    Returns
    -------
    SourceResult
        ``status`` is ``"ok"`` on success (even when findings exist),
        or ``"error"`` on unexpected failures.
    """
    start = time.monotonic()
    root = Path(project_dir).resolve()

    use_git = _git_available(project_dir)
    messages: list[str] = []
    if not use_git:
        messages.append("git not available; age_days will be omitted")

    # Cache file-level age to avoid repeated git calls for the same file.
    age_cache: dict[Path, int | None] = {}

    findings: list[Finding] = []

    try:
        py_files = list(root.glob("**/*.py")) + list(root.glob("**/*.pyi"))
        for py_file in py_files:
            if _should_skip(py_file.relative_to(root)):
                continue

            rel_path = str(py_file.relative_to(root))

            # Determine file age (cached).
            if use_git and py_file not in age_cache:
                age_cache[py_file] = _file_age_days(
                    py_file.relative_to(root), project_dir
                )
            age_days = age_cache.get(py_file)

            try:
                lines = py_file.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue

            for line_no, line in enumerate(lines, start=1):
                m = _MARKER_RE.search(line)
                if m is None:
                    continue

                marker_type = m.group(1).upper()
                detail = m.group(2).strip()
                severity = _SEVERITY[marker_type.lower()]

                finding_id = f"marker-{marker_type}-{rel_path}:{line_no}"

                findings.append(
                    Finding(
                        id=finding_id,
                        source=SOURCE,
                        severity=severity,  # type: ignore[arg-type]
                        category=CATEGORY,  # type: ignore[arg-type]
                        title=f"{marker_type}: {detail}" if detail else marker_type,
                        detail=detail,
                        file_path=rel_path,
                        line=line_no,
                        age_days=age_days,
                    )
                )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return SourceResult(
            source=SOURCE,
            status="error",
            duration_ms=elapsed,
            messages=[f"Unexpected error scanning markers: {exc}"],
        )

    elapsed = int((time.monotonic() - start) * 1000)
    return SourceResult(
        source=SOURCE,
        status="ok",
        findings=findings,
        duration_ms=elapsed,
        messages=messages,
    )

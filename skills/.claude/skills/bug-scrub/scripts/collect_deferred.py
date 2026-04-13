#!/usr/bin/env python3
"""Signal collector for deferred issues harvested from OpenSpec change artifacts.

Scans three artifact types across both active and archived changes:
  (a) impl-findings.md  - findings containing "out of scope" or "deferred" text
  (b) deferred-tasks.md - migrated task tables
  (c) tasks.md          - unchecked items (``- [ ]``) representing open tasks

Active changes produce severity "medium"; archived changes produce severity "low".
Each finding carries a FindingOrigin with enough metadata for fix-scrub to locate
and update the source artifact.
"""

from __future__ import annotations

import glob
import logging
import os
import re
import time

from models import Finding, FindingOrigin, SourceResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFERRED_RE = re.compile(r"(?:out[\s\-]of[\s\-]scope|deferred)", re.IGNORECASE)
_UNCHECKED_RE = re.compile(r"^(\s*)-\s*\[\s*\]\s+(.+)", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\|(.+)\|$")

# Glob patterns relative to the project root
_ACTIVE_GLOB = "openspec/changes/*/{}".format  # noqa: UP032 – used as a factory
_ARCHIVE_GLOB = "openspec/changes/archive/*/{}".format


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _change_id_from_path(artifact_path: str) -> str:
    """Extract the change-id directory name from an artifact path.

    Works for both active (``openspec/changes/<id>/artifact.md``) and archived
    (``openspec/changes/archive/<id>/artifact.md``) layouts.
    """
    return os.path.basename(os.path.dirname(artifact_path))


def _is_archived(artifact_path: str) -> bool:
    """Return True if *artifact_path* resides under the archive directory."""
    normalized = artifact_path.replace(os.sep, "/")
    return "/archive/" in normalized


def _severity_for(artifact_path: str) -> str:
    """Return ``'low'`` for archived changes, ``'medium'`` for active."""
    return "low" if _is_archived(artifact_path) else "medium"


def _relative_path(project_dir: str, full_path: str) -> str:
    """Return *full_path* relative to *project_dir*."""
    return os.path.relpath(full_path, project_dir)


def _parse_table_rows(text: str) -> list[dict[str, str]]:
    """Parse a simple markdown table into a list of row dicts.

    Returns one dict per data row, keyed by lower-cased/stripped header names.
    Skips the separator row (``|---|---|…``).
    """
    lines = text.splitlines()
    header_line: str | None = None
    headers: list[str] = []
    rows: list[dict[str, str]] = []

    for line in lines:
        stripped = line.strip()
        match = _TABLE_ROW_RE.match(stripped)
        if not match:
            continue
        cells = [c.strip() for c in match.group(1).split("|")]
        # Detect header row (first table row)
        if header_line is None:
            header_line = stripped
            headers = [h.strip().lower() for h in cells]
            continue
        # Skip separator rows (e.g. |---|---|)
        if all(set(c) <= {"-", ":"} for c in cells):
            continue
        # Skip empty placeholder rows (all cells blank)
        if all(c == "" for c in cells):
            continue
        row: dict[str, str] = {}
        for idx, cell in enumerate(cells):
            key = headers[idx] if idx < len(headers) else f"col{idx}"
            row[key] = cell
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Per-artifact scanners
# ---------------------------------------------------------------------------


def _scan_impl_findings(
    project_dir: str,
    findings: list[Finding],
    messages: list[str],
) -> None:
    """Scan ``impl-findings.md`` artifacts for deferred/out-of-scope items."""
    source_type = "impl-findings"
    source_name = "deferred:impl-findings"

    patterns = [
        os.path.join(project_dir, _ACTIVE_GLOB("impl-findings.md")),
        os.path.join(project_dir, _ARCHIVE_GLOB("impl-findings.md")),
    ]

    for pattern in patterns:
        for fpath in sorted(glob.glob(pattern)):
            rel = _relative_path(project_dir, fpath)
            change_id = _change_id_from_path(fpath)
            severity = _severity_for(fpath)

            try:
                with open(fpath, encoding="utf-8") as fh:
                    content = fh.read()
            except OSError as exc:
                logger.warning("Cannot read %s: %s", fpath, exc)
                messages.append(f"warn: cannot read {rel}: {exc}")
                continue

            try:
                table_rows = _parse_table_rows(content)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Malformed table in %s: %s", fpath, exc)
                messages.append(f"warn: malformed table in {rel}: {exc}")
                continue

            # Also check by line so we can capture line_in_artifact
            lines = content.splitlines()
            line_map: dict[str, int] = {}  # row-index-str -> line number
            for line_no, line_text in enumerate(lines, start=1):
                if _TABLE_ROW_RE.match(line_text.strip()):
                    # We'll correlate later via content matching
                    pass
                # Build a quick lookup: first occurrence of each cell "#" value
                match = _TABLE_ROW_RE.match(line_text.strip())
                if match:
                    cells = [c.strip() for c in match.group(1).split("|")]
                    if cells and cells[0] and cells[0] not in ("#", "---", "-"):
                        line_map[cells[0]] = line_no

            idx = 0
            for row in table_rows:
                # Check description and resolution columns for deferred signals
                desc = row.get("description", "")
                resolution = row.get("resolution", "")
                combined = f"{desc} {resolution}"
                if not _DEFERRED_RE.search(combined):
                    continue

                task_number = row.get("#", str(idx))
                line_in_artifact = line_map.get(task_number)
                finding_id = f"deferred-{source_type}-{change_id}-{idx}"

                findings.append(
                    Finding(
                        id=finding_id,
                        source=source_name,
                        severity=severity,  # type: ignore[arg-type]
                        category="deferred-issue",
                        title=desc[:120] if desc else f"Deferred finding in {change_id}",
                        detail=f"Resolution: {resolution}" if resolution else "",
                        origin=FindingOrigin(
                            change_id=change_id,
                            artifact_path=rel,
                            task_number=task_number if task_number else None,
                            line_in_artifact=line_in_artifact,
                        ),
                    )
                )
                idx += 1


def _scan_deferred_tasks(
    project_dir: str,
    findings: list[Finding],
    messages: list[str],
) -> None:
    """Scan ``deferred-tasks.md`` artifacts for migrated task tables."""
    source_type = "tasks"
    source_name = "deferred:tasks"

    patterns = [
        os.path.join(project_dir, _ACTIVE_GLOB("deferred-tasks.md")),
        os.path.join(project_dir, _ARCHIVE_GLOB("deferred-tasks.md")),
    ]

    for pattern in patterns:
        for fpath in sorted(glob.glob(pattern)):
            rel = _relative_path(project_dir, fpath)
            change_id = _change_id_from_path(fpath)
            severity = _severity_for(fpath)

            try:
                with open(fpath, encoding="utf-8") as fh:
                    content = fh.read()
            except OSError as exc:
                logger.warning("Cannot read %s: %s", fpath, exc)
                messages.append(f"warn: cannot read {rel}: {exc}")
                continue

            try:
                table_rows = _parse_table_rows(content)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Malformed table in %s: %s", fpath, exc)
                messages.append(f"warn: malformed table in {rel}: {exc}")
                continue

            # Build line number lookup
            lines = content.splitlines()
            line_map: dict[str, int] = {}
            for line_no, line_text in enumerate(lines, start=1):
                match = _TABLE_ROW_RE.match(line_text.strip())
                if match:
                    cells = [c.strip() for c in match.group(1).split("|")]
                    if cells and cells[0] and cells[0] not in ("#", "---", "-"):
                        line_map[cells[0]] = line_no

            idx = 0
            for row in table_rows:
                task_desc = row.get("original task", "")
                reason = row.get("reason", "")
                task_number = row.get("#", str(idx))
                line_in_artifact = line_map.get(task_number)
                finding_id = f"deferred-{source_type}-{change_id}-{idx}"

                title = task_desc[:120] if task_desc else f"Deferred task in {change_id}"
                detail_parts: list[str] = []
                if reason:
                    detail_parts.append(f"Reason: {reason}")
                migration_target = row.get("migration target", "")
                if migration_target:
                    detail_parts.append(f"Migration target: {migration_target}")
                files = row.get("files", "")
                if files:
                    detail_parts.append(f"Files: {files}")

                findings.append(
                    Finding(
                        id=finding_id,
                        source=source_name,
                        severity=severity,  # type: ignore[arg-type]
                        category="deferred-issue",
                        title=title,
                        detail="; ".join(detail_parts),
                        origin=FindingOrigin(
                            change_id=change_id,
                            artifact_path=rel,
                            task_number=task_number if task_number else None,
                            line_in_artifact=line_in_artifact,
                        ),
                    )
                )
                idx += 1


def _scan_open_tasks(
    project_dir: str,
    findings: list[Finding],
    messages: list[str],
) -> None:
    """Scan ``tasks.md`` for unchecked checkbox items (``- [ ]``)."""
    source_type = "open-tasks"
    source_name = "deferred:open-tasks"

    patterns = [
        os.path.join(project_dir, _ACTIVE_GLOB("tasks.md")),
        os.path.join(project_dir, _ARCHIVE_GLOB("tasks.md")),
    ]

    for pattern in patterns:
        for fpath in sorted(glob.glob(pattern)):
            rel = _relative_path(project_dir, fpath)
            change_id = _change_id_from_path(fpath)
            severity = _severity_for(fpath)

            try:
                with open(fpath, encoding="utf-8") as fh:
                    content = fh.read()
            except OSError as exc:
                logger.warning("Cannot read %s: %s", fpath, exc)
                messages.append(f"warn: cannot read {rel}: {exc}")
                continue

            try:
                lines = content.splitlines()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Malformed content in %s: %s", fpath, exc)
                messages.append(f"warn: malformed content in {rel}: {exc}")
                continue

            idx = 0
            for line_no, line_text in enumerate(lines, start=1):
                match = _UNCHECKED_RE.match(line_text)
                if not match:
                    continue

                task_text = match.group(2).strip()
                # Try to extract a task number (e.g. "1.1 Create foo")
                task_num_match = re.match(r"^(\d+(?:\.\d+)?)\s+", task_text)
                task_number = task_num_match.group(1) if task_num_match else None

                finding_id = f"deferred-{source_type}-{change_id}-{idx}"
                findings.append(
                    Finding(
                        id=finding_id,
                        source=source_name,
                        severity=severity,  # type: ignore[arg-type]
                        category="deferred-issue",
                        title=task_text[:120],
                        detail=f"Open task in change {change_id}",
                        origin=FindingOrigin(
                            change_id=change_id,
                            artifact_path=rel,
                            task_number=task_number,
                            line_in_artifact=line_no,
                        ),
                    )
                )
                idx += 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def collect(project_dir: str) -> SourceResult:
    """Harvest deferred issues from OpenSpec change artifacts.

    Parameters
    ----------
    project_dir:
        Absolute path to the project root (must contain ``openspec/changes/``).

    Returns
    -------
    SourceResult
        Aggregated findings across all three artifact types with timing.
    """
    start_ns = time.monotonic_ns()
    all_findings: list[Finding] = []
    messages: list[str] = []

    changes_dir = os.path.join(project_dir, "openspec", "changes")
    if not os.path.isdir(changes_dir):
        return SourceResult(
            source="deferred",
            status="skipped",
            messages=["openspec/changes/ directory not found"],
            duration_ms=0,
        )

    _scan_impl_findings(project_dir, all_findings, messages)
    _scan_deferred_tasks(project_dir, all_findings, messages)
    _scan_open_tasks(project_dir, all_findings, messages)

    elapsed_ms = int((time.monotonic_ns() - start_ns) / 1_000_000)

    return SourceResult(
        source="deferred",
        status="ok",
        findings=all_findings,
        duration_ms=elapsed_ms,
        messages=messages,
    )

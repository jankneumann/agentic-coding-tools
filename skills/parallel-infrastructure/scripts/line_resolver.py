"""Ingest-time line resolver: anchors a finding's ``existing_code`` snippet
to line numbers by parsing the diff, without a model call.

Ported from alibaba/open-code-review's resolver and hunk parser
(internal/diff/resolver.go, internal/diff/hunk.go, Apache-2.0 License,
https://github.com/alibaba/open-code-review, read 2026-09-14). Resolution
order: the diff's new side (context + added lines, new-file numbering),
then its old side (context + deleted lines, old-file numbering), then — only
when full file text is supplied — the whole new-file content. An unresolved
finding is kept, never dropped; ``line_resolution`` records which path (if
any) found it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from file_selection import FileDiff, parse_diff_files

_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

CONTEXT = "context"
ADDED = "added"
DELETED = "deleted"

RESOLUTION_VENDOR = "vendor"
RESOLUTION_HUNK_NEW = "hunk_new"
RESOLUTION_HUNK_OLD = "hunk_old"
RESOLUTION_FILE = "file"
RESOLUTION_UNRESOLVED = "unresolved"


@dataclass
class HunkLine:
    type: str
    content: str


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[HunkLine] = field(default_factory=list)


def parse_hunks(file_diff_text: str) -> list[Hunk]:
    """Parse one file's unified-diff text into its ``@@`` hunks.

    Lines before the first ``@@`` header (``diff --git``, ``---``, ``+++``)
    are ignored, matching OCR's ``ParseHunks``.
    """
    lines = file_diff_text.split("\n")
    hunks: list[Hunk] = []
    current: Hunk | None = None
    for line in lines:
        match = _HUNK_HEADER_RE.match(line)
        if match:
            if current is not None:
                hunks.append(current)
            old_count = int(match.group(2)) if match.group(2) else 1
            new_count = int(match.group(4)) if match.group(4) else 1
            current = Hunk(
                old_start=int(match.group(1)), old_count=old_count,
                new_start=int(match.group(3)), new_count=new_count,
            )
            continue
        if current is None:
            continue
        if line.startswith("\\ No newline at end of file"):
            continue
        if line.startswith("diff --git "):
            break
        if line.startswith("+"):
            current.lines.append(HunkLine(ADDED, line[1:]))
        elif line.startswith("-"):
            current.lines.append(HunkLine(DELETED, line[1:]))
        else:
            content = line[1:] if line.startswith(" ") else line
            current.lines.append(HunkLine(CONTEXT, content))
    if current is not None:
        hunks.append(current)
    return hunks


def _normalize_line(s: str) -> str:
    """Strip whitespace and one leading diff marker (+/-)."""
    s = s.strip()
    if s.startswith(("+", "-")):
        s = s[1:]
    return s.strip()


def _split_and_normalize(code: str) -> list[str]:
    return [n for n in (_normalize_line(line) for line in code.split("\n")) if n]


@dataclass
class _IndexedLine:
    line_num: int
    content: str


def _extract_side_lines(hunk: Hunk, *, new_side: bool) -> list[_IndexedLine]:
    result: list[_IndexedLine] = []
    old_line, new_line = hunk.old_start, hunk.new_start
    for line in hunk.lines:
        if line.type == CONTEXT:
            result.append(
                _IndexedLine(
                    new_line if new_side else old_line, _normalize_line(line.content)
                )
            )
            old_line += 1
            new_line += 1
        elif line.type == ADDED:
            if new_side:
                result.append(_IndexedLine(new_line, _normalize_line(line.content)))
            new_line += 1
        elif line.type == DELETED:
            if not new_side:
                result.append(_IndexedLine(old_line, _normalize_line(line.content)))
            old_line += 1
    return result


def _match_consecutive(
    side_lines: list[_IndexedLine], target_lines: list[str],
) -> tuple[int, int] | None:
    if not target_lines or len(side_lines) < len(target_lines):
        return None
    span = len(target_lines)
    for i in range(len(side_lines) - span + 1):
        if all(side_lines[i + j].content == target_lines[j] for j in range(span)):
            return side_lines[i].line_num, side_lines[i + span - 1].line_num
    return None


def _resolve_from_hunks(
    hunks: list[Hunk], existing_code: str,
) -> tuple[int, int, str] | None:
    target = _split_and_normalize(existing_code)
    if not target:
        return None
    for hunk in hunks:
        hit = _match_consecutive(_extract_side_lines(hunk, new_side=True), target)
        if hit:
            return hit[0], hit[1], RESOLUTION_HUNK_NEW
    for hunk in hunks:
        hit = _match_consecutive(_extract_side_lines(hunk, new_side=False), target)
        if hit:
            return hit[0], hit[1], RESOLUTION_HUNK_OLD
    return None


def _resolve_from_file_content(file_text: str, existing_code: str) -> tuple[int, int] | None:
    target = _split_and_normalize(existing_code)
    if not target:
        return None
    normalized: list[str] = []
    line_nums: list[int] = []
    for i, line in enumerate(file_text.split("\n")):
        n = _normalize_line(line.rstrip("\r"))
        if n:
            normalized.append(n)
            line_nums.append(i + 1)
    span = len(target)
    if len(normalized) < span:
        return None
    for i in range(len(normalized) - span + 1):
        if normalized[i : i + span] == target:
            return line_nums[i], line_nums[i + span - 1]
    return None


def find_file_diff(files: list[FileDiff], file_path: str) -> FileDiff | None:
    for f in files:
        if f.path == file_path or f.old_path == file_path:
            return f
    return None


def _has_usable_line_range(finding: dict[str, Any]) -> bool:
    rng = finding.get("line_range")
    return bool(
        isinstance(rng, dict) and rng.get("start") and rng.get("end")
    )


def resolve(
    finding: dict[str, Any],
    packet_diff: str,
    *,
    file_text: str | None = None,
    files: list[FileDiff] | None = None,
) -> dict[str, Any]:
    """Return a shallow copy of *finding* with ``line_range``/``line_resolution`` set.

    - A finding that already carries a usable ``line_range`` is returned
      with ``line_resolution: "vendor"`` (unless already set) and is
      otherwise unchanged.
    - A finding without ``existing_code`` is returned unchanged — there is
      nothing to resolve from.
    - Otherwise: new side of each hunk, then old side, then (only when
      *file_text* is supplied) the whole new-file content. An unresolved
      finding keeps ``line_range`` absent and gets
      ``line_resolution: "unresolved"`` — it is never dropped.
    """
    result = dict(finding)
    existing_code = result.get("existing_code")

    if _has_usable_line_range(result):
        result.setdefault("line_resolution", RESOLUTION_VENDOR)
        return result
    if not existing_code:
        return result

    files = files if files is not None else parse_diff_files(packet_diff)
    file_diff = find_file_diff(files, str(result.get("file_path", "")))
    if file_diff is not None:
        hit = _resolve_from_hunks(parse_hunks(file_diff.body), existing_code)
        if hit is not None:
            start, end, kind = hit
            result["line_range"] = {"start": start, "end": end}
            result["line_resolution"] = kind
            return result

    if file_text is not None:
        hit = _resolve_from_file_content(file_text, existing_code)
        if hit is not None:
            result["line_range"] = {"start": hit[0], "end": hit[1]}
            result["line_resolution"] = RESOLUTION_FILE
            return result

    result["line_resolution"] = RESOLUTION_UNRESOLVED
    return result


def resolve_all(
    findings: list[dict[str, Any]],
    packet_diff: str,
    *,
    file_texts: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Resolve every finding against one packet diff.

    Parses the diff once and reuses it across findings. Returns
    ``(resolved_findings, unanchored_count)``.
    """
    files = parse_diff_files(packet_diff)
    file_texts = file_texts or {}
    resolved: list[dict[str, Any]] = []
    unanchored = 0
    for finding in findings:
        r = resolve(
            finding, packet_diff,
            file_text=file_texts.get(str(finding.get("file_path", ""))),
            files=files,
        )
        if r.get("line_resolution") == RESOLUTION_UNRESOLVED:
            unanchored += 1
        resolved.append(r)
    return resolved, unanchored

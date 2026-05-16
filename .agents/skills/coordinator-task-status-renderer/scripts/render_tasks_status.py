#!/usr/bin/env python3
"""Render coordinator-owned task status block in openspec/changes/<id>/tasks.md.

Reads issue state from the coordinator via
``coordination_bridge.try_issue_list(labels=["change:<id>"], limit=100)``
and rewrites the ``<!-- GENERATED: begin coordinator:tasks-status -->`` block.

Contract: openspec/changes/add-coordinator-task-status-renderer/contracts/README.md
Spec: openspec/changes/add-coordinator-task-status-renderer/specs/coordinator-task-status-renderer/spec.md
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

# Allow importing coordination_bridge regardless of cwd.
_SKILL_ROOT = Path(__file__).resolve().parents[2]
_BRIDGE_DIR = _SKILL_ROOT / "coordination-bridge" / "scripts"
if str(_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_DIR))

import coordination_bridge  # noqa: E402

# ----------------------------------------------------------------------
# Marker helpers (locally duplicated from skills/plan-roadmap/scripts/renderer.py
# per D1 — do not import private underscore-prefixed symbols).
# ----------------------------------------------------------------------

_BLOCK_NAME = "coordinator:tasks-status"
_GEN_BEGIN = f"<!-- GENERATED: begin {_BLOCK_NAME} -->"
_GEN_END = f"<!-- GENERATED: end {_BLOCK_NAME} -->"
_GEN_BEGIN_RE = re.compile(re.escape(_GEN_BEGIN))
_GEN_END_RE = re.compile(re.escape(_GEN_END))
_INFO_COMMENT_TMPL = (
    '<!-- Informational projection — see openspec/changes/'
    '{change_id}/proposal.md "What Doesn\'t Change" -->'
)
_PAGE_CAP = 100
_DEFAULT_TIMEOUT_SECONDS = 5


def _gen_block(content: str) -> str:
    """Wrap content in the renderer's generated-block markers."""
    inner = content.rstrip("\n")
    return f"{_GEN_BEGIN}\n{inner}\n{_GEN_END}"


def _split_around_block(md: str) -> tuple[str, str | None, str]:
    """Split tasks.md into (prefix, existing_block_content, suffix).

    ``existing_block_content`` is ``None`` when no managed block is found.
    Marker-aware prefix/suffix splitter — do NOT use
    ``plan-roadmap._extract_human_sections`` (D1).
    """
    lines = md.split("\n")
    begin_idx: int | None = None
    end_idx: int | None = None
    for i, line in enumerate(lines):
        if begin_idx is None and _GEN_BEGIN_RE.search(line):
            begin_idx = i
        elif begin_idx is not None and end_idx is None and _GEN_END_RE.search(line):
            end_idx = i
            break
    if begin_idx is None or end_idx is None:
        return md, None, ""
    prefix = "\n".join(lines[:begin_idx])
    inner = "\n".join(lines[begin_idx + 1 : end_idx])
    suffix = "\n".join(lines[end_idx + 1 :])
    return prefix, inner, suffix


# ----------------------------------------------------------------------
# Natural-numeric comparator (contracts/README.md "Natural-numeric comparator").
# ----------------------------------------------------------------------

_LEADING_DIGITS_RE = re.compile(r"^(\d*)(.*)$")
_LETTER_PREFIX_RE = re.compile(r"^([A-Za-z]+)(\d*)(.*)$")


def _segment_sort_key(segment: str) -> tuple[int, str]:
    m = _LEADING_DIGITS_RE.match(segment)
    assert m is not None  # regex always matches
    digits, suffix = m.group(1), m.group(2)
    int_part = int(digits) if digits else -1
    return (int_part, suffix)


def _key_sort_key(task_key: str) -> tuple[int, tuple[Any, ...]]:
    """Bucket all-numeric keys before letter-prefixed keys, then sort within."""
    if task_key and task_key[0].isalpha():
        m = _LETTER_PREFIX_RE.match(task_key)
        assert m is not None
        prefix, digits, suffix = m.group(1), m.group(2), m.group(3)
        int_part = int(digits) if digits else -1
        return (1, (prefix, int_part, suffix))
    segments = task_key.split(".")
    return (0, tuple(_segment_sort_key(s) for s in segments))


def _sort_task_keys(keys: list[str]) -> list[str]:
    return sorted(keys, key=_key_sort_key)


def _natural_compare(a: str, b: str) -> int:
    ka, kb = _key_sort_key(a), _key_sort_key(b)
    if ka < kb:
        return -1
    if ka > kb:
        return 1
    return 0


# ----------------------------------------------------------------------
# Coordinator -> rendered-content mapping.
# ----------------------------------------------------------------------


def _extract_task_key(issue: dict[str, Any]) -> str | None:
    """Pull the ``task:<key>`` label off an issue. Returns None if missing."""
    labels = issue.get("labels") or []
    for lbl in labels:
        if isinstance(lbl, str) and lbl.startswith("task:"):
            return lbl[len("task:") :]
    return None


def _format_status_annotation(issue: dict[str, Any]) -> str:
    """Format the trailing status annotation per contracts/README.md."""
    status = issue.get("status", "pending")
    assignee = issue.get("assignee")
    if status == "pending":
        return "pending"
    if status == "claimed":
        return f"claimed by {assignee}" if assignee else "claimed"
    if status == "running":
        return (
            f"in_progress, claimed by {assignee}" if assignee else "in_progress"
        )
    if status == "completed":
        completed_at = issue.get("completed_at")
        date_str = ""
        if completed_at:
            try:
                # Strip subsecond + zone to UTC date.
                dt = _dt.datetime.fromisoformat(
                    str(completed_at).replace("Z", "+00:00")
                )
                date_str = dt.astimezone(_dt.timezone.utc).date().isoformat()
            except (ValueError, TypeError):
                date_str = ""
        if assignee and date_str:
            return f"done by {assignee} {date_str}"
        if assignee:
            return f"done by {assignee}"
        if date_str:
            return f"done {date_str}"
        return "done"
    if status == "failed":
        reason = issue.get("close_reason")
        return f"failed: {reason}" if reason else "failed"
    if status == "cancelled":
        reason = issue.get("close_reason")
        return f"cancelled: {reason}" if reason else "cancelled"
    return status


def _build_blocked_on_suffix(
    issue: dict[str, Any], by_uuid: dict[str, dict[str, Any]]
) -> str:
    """Return ' — blocked on <keys>' when depends_on has uncompleted upstreams."""
    deps = issue.get("depends_on") or []
    if not deps:
        return ""
    blocking_keys: list[str] = []
    for upstream_uuid in deps:
        up = by_uuid.get(upstream_uuid)
        if up is None:
            continue  # Unknown — not part of current change.
        if up.get("status") == "completed":
            continue
        k = _extract_task_key(up)
        if k:
            blocking_keys.append(k)
    if not blocking_keys:
        return ""
    blocking_keys = _sort_task_keys(blocking_keys)
    return f" — blocked on {', '.join(blocking_keys)}"


def _render_issue_line(
    issue: dict[str, Any], by_uuid: dict[str, dict[str, Any]]
) -> str | None:
    task_key = _extract_task_key(issue)
    if not task_key:
        print(
            f"WARN: issue {issue.get('id')!r} missing task:<key> label, skipping",
            file=sys.stderr,
        )
        return None
    box = "x" if issue.get("status") == "completed" else " "
    title = issue.get("title", "")
    status_annot = _format_status_annotation(issue)
    blocked = _build_blocked_on_suffix(issue, by_uuid)
    return f"- [{box}] {task_key}: {title} — {status_annot}{blocked}"


def _render_block_content(
    change_id: str, issues: list[dict[str, Any]]
) -> str:
    lines = [_INFO_COMMENT_TMPL.format(change_id=change_id)]
    by_uuid: dict[str, dict[str, Any]] = {
        i["id"]: i for i in issues if i.get("id")
    }
    rendered: list[tuple[str, str]] = []
    for issue in issues:
        line = _render_issue_line(issue, by_uuid)
        if line is None:
            continue
        key = _extract_task_key(issue) or ""
        rendered.append((key, line))
    # Stable tie-breaker on UUID
    by_uuid_for_tie = {
        _extract_task_key(i) or "": (i.get("id") or "") for i in issues
    }
    rendered.sort(
        key=lambda kv: (_key_sort_key(kv[0]), by_uuid_for_tie.get(kv[0], ""))
    )
    for _, line in rendered:
        lines.append(line)
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Stale-marker sidecar (two-tier idempotency).
# ----------------------------------------------------------------------


def _sidecar_path(repo_root: Path, change_id: str) -> Path:
    return (
        repo_root
        / "openspec"
        / "changes"
        / change_id
        / ".tasks-status.state.json"
    )


def _read_sidecar(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_sidecar(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"WARN: failed to write sidecar {path}: {e}", file=sys.stderr)


def _stale_marker_content(timestamp_iso: str) -> str:
    return f"> Coordinator unreachable at {timestamp_iso} — status frozen."


# ----------------------------------------------------------------------
# Timeout wrapper.
# ----------------------------------------------------------------------


class _RenderTimeout(Exception):
    pass


def _call_coordinator_with_timeout(
    change_id: str, timeout_seconds: int
) -> dict[str, Any]:
    """Invoke try_issue_list with a wall-clock alarm.

    On timeout raises ``_RenderTimeout``. On other errors propagates the
    bridge's normal dict response (caller inspects ``status`` field).
    """

    def _handler(signum: int, frame: Any) -> None:  # pragma: no cover (signal path)
        raise _RenderTimeout()

    old_handler = signal.signal(signal.SIGALRM, _handler)
    try:
        signal.alarm(timeout_seconds)
        try:
            return coordination_bridge.try_issue_list(
                labels=[f"change:{change_id}"], limit=_PAGE_CAP
            )
        finally:
            signal.alarm(0)
    finally:
        signal.signal(signal.SIGALRM, old_handler)


# ----------------------------------------------------------------------
# Main rendering driver.
# ----------------------------------------------------------------------


def _now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).replace(microsecond=0).isoformat()


def _resolve_repo_root(arg: str | None) -> Path:
    if arg:
        return Path(arg).resolve()
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()


def _render_managed_block(
    md: str, block_content: str
) -> str:
    """Insert or replace the managed block in ``md``."""
    prefix, existing, suffix = _split_around_block(md)
    block = _gen_block(block_content)
    if existing is None:
        # Insert at end of file, preserving trailing newline conventions.
        joined = md.rstrip("\n")
        return joined + "\n\n" + block + "\n"
    head = prefix.rstrip("\n")
    tail = suffix.lstrip("\n")
    out = head + ("\n\n" if head else "") + block + ("\n\n" + tail if tail else "\n")
    return out


def render(
    change_id: str,
    repo_root: Path,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    *,
    _now: str | None = None,
) -> int:
    """Render the managed block. Returns exit code.

    Behavior:
    - Coordinator success: writes normal block (or stale-marker block if zero
      issues but coordinator reachable — actually zero issues renders only the
      header comment, which is intentional).
    - Coordinator unreachable / timeout / cap-exceeded: writes stale-marker
      block (cap-exceeded reports error and returns 1).
    - tasks.md missing / unreadable: returns 1.
    """
    tasks_path = repo_root / "openspec" / "changes" / change_id / "tasks.md"
    try:
        md = tasks_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"ERROR: tasks.md not found at {tasks_path}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"ERROR: cannot read {tasks_path}: {e}", file=sys.stderr)
        return 1

    sidecar = _sidecar_path(repo_root, change_id)
    sidecar_state = _read_sidecar(sidecar)

    stale_reason: str | None = None
    issues: list[dict[str, Any]] = []
    try:
        result = _call_coordinator_with_timeout(change_id, timeout_seconds)
    except _RenderTimeout:
        stale_reason = "timeout"
        result = {"status": "timeout"}
    else:
        status = result.get("status", "skipped")
        if status in ("ok", "success"):
            issues = result.get("data", {}).get("issues") or result.get("issues") or []
            # Pagination guard: cap-exceeded -> hard ERROR exit 1.
            if isinstance(issues, list) and len(issues) >= _PAGE_CAP:
                print(
                    "ERROR: coordinator returned page cap ("
                    f"{_PAGE_CAP}) for change {change_id!r}; refusing to render "
                    "(silent truncation risk). See follow-up "
                    "query-issues-by-change-label-server-side.",
                    file=sys.stderr,
                )
                return 1
        else:
            stale_reason = status or "unreachable"

    if stale_reason is not None:
        # Use sidecar-persisted timestamp if present, else stamp now.
        ts = sidecar_state.get("stale_timestamp")
        if not ts:
            ts = _now or _now_iso()
            sidecar_state["stale_timestamp"] = ts
            _write_sidecar(sidecar, sidecar_state)
        block_content = _stale_marker_content(ts)
        new_md = _render_managed_block(md, block_content)
        try:
            tasks_path.write_text(new_md, encoding="utf-8")
        except OSError as e:
            print(f"ERROR: cannot write {tasks_path}: {e}", file=sys.stderr)
            return 1
        print(
            f"stale-marker {change_id} reason={stale_reason}",
            file=sys.stdout,
        )
        return 0

    # Coordinator reachable — clear sidecar's stale entry.
    if "stale_timestamp" in sidecar_state:
        sidecar_state.pop("stale_timestamp", None)
        _write_sidecar(sidecar, sidecar_state)

    block_content = _render_block_content(change_id, issues)
    new_md = _render_managed_block(md, block_content)
    try:
        tasks_path.write_text(new_md, encoding="utf-8")
    except OSError as e:
        print(f"ERROR: cannot write {tasks_path}: {e}", file=sys.stderr)
        return 1
    print(f"rendered {change_id} issues={len(issues)}", file=sys.stdout)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("change_id")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=_DEFAULT_TIMEOUT_SECONDS,
        help="Wall-clock timeout for coordinator call (default 5).",
    )
    args = parser.parse_args(argv)
    repo_root = _resolve_repo_root(args.repo_root)
    return render(args.change_id, repo_root, args.timeout_seconds)


if __name__ == "__main__":
    sys.exit(main())

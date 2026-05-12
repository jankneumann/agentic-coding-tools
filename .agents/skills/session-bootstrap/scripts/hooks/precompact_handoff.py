#!/usr/bin/env python3
"""PreCompact hook: persist a snapshot handoff and clear the compact-pending flag.

Runs immediately before Claude Code compacts the conversation. Two duties:

  1. **Clear the flag** written by check_compact.py so the next Stop after the
     compaction does not immediately re-block.
  2. **Write a snapshot handoff** to the coordinator (and local fallback) so
     SessionStart's register_agent.py rehydrates context post-compaction.
     Symmetric with deregister_agent.py.

Stdlib-only (urllib) — matches the constraint on register/deregister hooks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

PREFIX = "[precompact_handoff]"
MAX_NEXT_STEPS_IN_SUMMARY = 3


def _all_worktree_roots(cwd: Path | None = None) -> list[Path]:
    """Return every checkout known to the current git repository. See
    check_compact.py:_all_worktree_roots for the full rationale."""
    cwd = cwd or Path.cwd()
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=2, check=True,
            cwd=str(cwd),
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return [cwd]
    roots: list[Path] = []
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            roots.append(Path(line.split(" ", 1)[1]))
    return roots or [cwd]


def _agent_id() -> str:
    return os.environ.get("AGENT_ID", "unknown")


def _flag_path() -> Path:
    return Path.home() / ".claude" / f"compact-pending-{_agent_id()}.flag"


def _coordinator_url() -> str | None:
    url = os.environ.get("COORDINATION_API_URL")
    return url.rstrip("/") if url else None


def _api_headers() -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "agentic-coding-tools/0.1",
    }
    api_key = os.environ.get("COORDINATION_API_KEY", "")
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _post(base_url: str, path: str, payload: dict) -> dict | None:
    url = f"{base_url}{path}"
    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers=_api_headers(), method="POST")
    try:
        with urlopen(req, timeout=5.0) as resp:
            return json.loads(resp.read())
    except (URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"{PREFIX} HTTP request failed ({path}): {exc}", file=sys.stderr)
        return None


def _read_hook_input() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def _clear_flag() -> None:
    try:
        _flag_path().unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        print(f"{PREFIX} failed to clear flag: {exc}", file=sys.stderr)


def _latest_phase_record(cwd: Path | None = None) -> dict[str, Any] | None:
    """Find the newest openspec/changes/<id>/handoffs/<phase>-<N>.json across
    every worktree of the current repo, return its inner ``payload`` dict.
    Returns None if no handoff exists or parsing fails. The on-disk format
    is the local-fallback envelope:
    {schema_version, written_at, coordinator_error, payload: {...}}."""
    candidates: list[Path] = []
    seen: set[Path] = set()
    for root in _all_worktree_roots(cwd):
        for p in root.glob("openspec/changes/*/handoffs/*.json"):
            try:
                resolved = p.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(p)
    if not candidates:
        return None
    try:
        newest = max(candidates, key=lambda p: p.stat().st_mtime)
    except OSError:
        return None
    try:
        data = json.loads(newest.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    payload = data.get("payload")
    if isinstance(payload, dict):
        return payload
    if "summary" in data:  # tolerate flat-shaped handoffs
        return data
    return None


def _build_summary(record: dict[str, Any] | None) -> str:
    """Compose a snapshot summary from the latest PhaseRecord, with a
    fallback message when none exists. Includes the first few next_steps
    inline so post-compact rehydration carries actionable context."""
    base = f"Pre-compact snapshot (agent={_agent_id()})."
    if not record:
        return (
            f"{base} No phase handoffs available; rehydrate by inspecting "
            f"recent commits and openspec/changes/."
        )
    parts = [base]
    record_summary = record.get("summary")
    if isinstance(record_summary, str) and record_summary.strip():
        parts.append(f"Last phase: {record_summary.strip()}")
    next_steps = record.get("next_steps") or []
    if isinstance(next_steps, list) and next_steps:
        head = [str(s) for s in next_steps[:MAX_NEXT_STEPS_IN_SUMMARY]]
        parts.append("Next steps: " + " | ".join(head))
        if len(next_steps) > MAX_NEXT_STEPS_IN_SUMMARY:
            parts.append(f"(+{len(next_steps) - MAX_NEXT_STEPS_IN_SUMMARY} more)")
    combined = " ".join(parts)
    return combined[:1900]  # schema caps summary at 2000 chars; leave headroom


def _write_handoff(payload: dict) -> None:
    """Write a pre-compact snapshot via /handoffs/write. Empty agent_id/type
    let the coordinator resolve identity from the API key (same pattern as
    deregister_agent.py:85-90). Structured fields (completed_work, in_progress,
    next_steps, decisions, relevant_files) come from the latest PhaseRecord
    payload so SessionStart can rehydrate full context after compaction."""
    base_url = _coordinator_url()
    if not base_url:
        print(f"{PREFIX} no coordinator URL; skipping handoff write",
              file=sys.stderr)
        return

    record = _latest_phase_record()
    session_id = os.environ.get("SESSION_ID", "") or payload.get("session_id", "")
    summary = _build_summary(record)

    body: dict[str, Any] = {
        "agent_id": "",
        "agent_type": "",
        "session_id": session_id or None,
        "summary": summary,
    }
    if record:
        for key in ("completed_work", "in_progress", "next_steps",
                    "decisions", "relevant_files"):
            value = record.get(key)
            if isinstance(value, list) and value:
                body[key] = value

    result = _post(base_url, "/handoffs/write", body)

    if result and result.get("success"):
        handoff_id = result.get("handoff_id", "?")
        print(f"{PREFIX} Pre-compact handoff written: {handoff_id}")
    elif result and result.get("error"):
        print(f"{PREFIX} Handoff write failed: {result['error']}",
              file=sys.stderr)
    else:
        print(f"{PREFIX} Handoff write failed", file=sys.stderr)


def main() -> int:
    payload = _read_hook_input()
    _clear_flag()
    _write_handoff(payload)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        # Must never block compaction.
        print(f"{PREFIX} unexpected error: {exc}", file=sys.stderr)
        sys.exit(0)

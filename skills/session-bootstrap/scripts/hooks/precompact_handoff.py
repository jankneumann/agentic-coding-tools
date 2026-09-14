#!/usr/bin/env python3
"""PreCompact hook: persist a snapshot handoff and clear the compact-pending flag.

Runs immediately before Claude Code compacts the conversation. Two duties:

  1. **Clear the flag** written by check_compact.py so the next Stop after the
     compaction does not immediately re-block. Both hooks key the flag on the
     session (session_scope.session_key), derived from their hook payloads.
  2. **Write a snapshot handoff** to the coordinator (and local fallback) so
     SessionStart's register_agent.py rehydrates context post-compaction.
     Only this session's PhaseRecords are folded in. Symmetric with
     deregister_agent.py.

Stdlib-only (urllib) — matches the constraint on register/deregister hooks.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
import session_scope  # noqa: E402

PREFIX = "[precompact_handoff]"
MAX_NEXT_STEPS_IN_SUMMARY = 3


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


def _clear_flag(payload: dict | None = None) -> None:
    try:
        session_scope.flag_path(payload).unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        print(f"{PREFIX} failed to clear flag: {exc}", file=sys.stderr)


def _latest_phase_record(
    payload: dict | None = None, cwd: Path | None = None,
) -> dict[str, Any] | None:
    """Find this session's newest openspec/changes/<id>/handoffs/<phase>-<N>.json
    and return its inner ``payload`` dict. A handoff from a worktree the
    session never worked in, or for a change it never mentioned, belongs to
    another session and is skipped (session_scope.SessionScope.owns_handoff).
    Returns None if no owned handoff exists or parsing fails. The on-disk
    format is the local-fallback envelope:
    {schema_version, written_at, coordinator_error, payload: {...}}."""
    roots = session_scope.all_worktree_roots(cwd)
    scope = session_scope.load_session_scope(payload, fallback_cwd=cwd)
    candidates: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        for p in root.glob(session_scope.HANDOFF_GLOB):
            try:
                resolved = p.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            if scope.owns_handoff(p, roots):
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
    handoff_payload = data.get("payload")
    if isinstance(handoff_payload, dict):
        return handoff_payload
    if "summary" in data:  # tolerate flat-shaped handoffs
        return data
    return None


def _build_summary(
    record: dict[str, Any] | None, session: str = "unknown",
) -> str:
    """Compose a snapshot summary from the latest PhaseRecord, with a
    fallback message when none exists. Includes the first few next_steps
    inline so post-compact rehydration carries actionable context."""
    base = f"Pre-compact snapshot (session={session})."
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

    record = _latest_phase_record(payload)
    session_id = os.environ.get("SESSION_ID", "") or payload.get("session_id", "")
    summary = _build_summary(record, session_scope.session_key(payload))

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
    _clear_flag(payload)
    _write_handoff(payload)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        # Must never block compaction.
        print(f"{PREFIX} unexpected error: {exc}", file=sys.stderr)
        sys.exit(0)

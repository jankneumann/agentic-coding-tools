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
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

PREFIX = "[precompact_handoff]"


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


def _write_handoff(payload: dict) -> None:
    """Write a pre-compact snapshot via /handoffs/write. Empty agent_id/type
    let the coordinator resolve identity from the API key (same pattern as
    deregister_agent.py:85-90)."""
    base_url = _coordinator_url()
    if not base_url:
        print(f"{PREFIX} no coordinator URL; skipping handoff write",
              file=sys.stderr)
        return

    session_id = os.environ.get("SESSION_ID", "") or payload.get("session_id", "")
    summary = (
        f"Pre-compact snapshot (agent={_agent_id()}). Context window threshold "
        f"or phase boundary triggered /compact; rehydrate next steps from "
        f"latest PhaseRecord on resume."
    )

    result = _post(base_url, "/handoffs/write", {
        "agent_id": "",
        "agent_type": "",
        "session_id": session_id or None,
        "summary": summary,
    })

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

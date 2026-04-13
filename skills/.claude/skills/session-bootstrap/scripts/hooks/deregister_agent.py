#!/usr/bin/env python3
"""Deregister agent session on Claude Code session end.

This script is called by Claude Code's SessionEnd lifecycle hook.
It reports session end to the coordinator and writes a final handoff
document for the next session to pick up.

Uses only stdlib (urllib) — no third-party dependencies required.

Note: Lock release is not performed here because the HTTP API has no
endpoint to list locks by agent. Locks expire automatically via TTL
(default 120 minutes). If immediate release is needed, skills should
release locks explicitly before session end.

Usage:
    python agent-coordinator/scripts/deregister_agent.py

Environment variables:
    COORDINATION_API_URL: Coordinator HTTP API URL (optional; skips if unset)
    COORDINATION_API_KEY: API key for X-API-Key header
    AGENT_ID: Agent identifier (default: "unknown")
    AGENT_TYPE: Agent type (default: "claude_code")
    SESSION_ID: Session identifier (optional)
"""

from __future__ import annotations

import json
import os
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

PREFIX = "[deregister_agent]"


def _coordinator_url() -> str | None:
    """Resolve coordinator base URL from environment. Returns None when unset."""
    url = os.environ.get("COORDINATION_API_URL")
    return url.rstrip("/") if url else None


def _api_headers() -> dict[str, str]:
    """Build HTTP headers including API key if available.

    The User-Agent header is set to bypass Cloudflare bot filtering on
    proxied hostnames — see docs/cloudflare-setup.md section 6.
    """
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "agentic-coding-tools/0.1",
    }
    api_key = os.environ.get("COORDINATION_API_KEY", "")
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _post(base_url: str, path: str, payload: dict) -> dict | None:
    """POST JSON to coordinator endpoint. Returns parsed response or None."""
    url = f"{base_url}{path}"
    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers=_api_headers(), method="POST")
    try:
        with urlopen(req, timeout=5.0) as resp:
            return json.loads(resp.read())
    except (URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"{PREFIX} HTTP request failed ({path}): {exc}", file=sys.stderr)
        return None


def main() -> None:
    base_url = _coordinator_url()
    if not base_url:
        print(f"{PREFIX} No coordinator URL configured, skipping", file=sys.stderr)
        return

    agent_id = os.environ.get("AGENT_ID", "unknown")
    agent_type = os.environ.get("AGENT_TYPE", "claude_code")
    session_id = os.environ.get("SESSION_ID", "")

    # Write a final handoff document.
    # Use empty agent_id/agent_type to let server resolve from API key,
    # avoiding 403 when AGENT_ID doesn't match the key's bound identity.
    handoff_result = _post(base_url, "/handoffs/write", {
        "agent_id": "",
        "agent_type": "",
        "session_id": session_id or None,
        "summary": "Session ended.",
    })

    if handoff_result and handoff_result.get("success"):
        handoff_id = handoff_result.get("handoff_id", "?")
        print(f"{PREFIX} Final handoff written: {handoff_id}")
    elif handoff_result and handoff_result.get("error"):
        print(f"{PREFIX} Handoff write failed: {handoff_result['error']}", file=sys.stderr)
    else:
        print(f"{PREFIX} Handoff write failed", file=sys.stderr)

    # Report session end (triggers heartbeat on the coordinator)
    result = _post(base_url, "/status/report", {
        "agent_id": agent_id,
        "change_id": "",
        "phase": "SESSION_END",
        "message": "Session ended",
        "needs_human": False,
        "event_type": "status.phase_transition",
        "metadata": {
            "agent_type": agent_type,
            "session_id": session_id,
            "event": "session.ended",
        },
    })

    if result:
        print(f"{PREFIX} Deregistered session for {agent_id}")
    else:
        print(f"{PREFIX} Deregistration failed (coordinator may be unreachable)", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Must never block Claude Code shutdown
        pass

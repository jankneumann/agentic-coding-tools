#!/usr/bin/env python3
"""Register agent session on Claude Code session start.

This script is called by Claude Code's SessionStart lifecycle hook.
It registers the agent with the coordination system via the HTTP API
and loads the most recent handoff document for context continuity.

Uses only stdlib (urllib) — no third-party dependencies required.

Usage:
    python agent-coordinator/scripts/register_agent.py

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

PREFIX = "[register_agent]"


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

    # Register via status report (triggers heartbeat on the coordinator).
    # /status/report has no auth — uses AGENT_ID env var directly.
    result = _post(base_url, "/status/report", {
        "agent_id": agent_id,
        "change_id": "",
        "phase": "SESSION_START",
        "message": f"Session started (type={agent_type})",
        "needs_human": False,
        "event_type": "status.phase_transition",
        "metadata": {
            "agent_type": agent_type,
            "session_id": session_id,
            "event": "session.started",
        },
    })

    if result:
        print(f"{PREFIX} Registered session for {agent_id}")
    else:
        print(f"{PREFIX} Registration failed (coordinator may be unreachable)", file=sys.stderr)

    # Load most recent handoff for context continuity.
    # Pass agent_name=None to read the most recent handoff regardless of
    # which agent wrote it — avoids identity mismatch between AGENT_ID
    # env var and the API key's bound identity on the server.
    handoff_result = _post(base_url, "/handoffs/read", {
        "agent_name": None,
        "limit": 1,
    })

    if handoff_result and handoff_result.get("handoffs"):
        h = handoff_result["handoffs"][0]
        summary = h.get("summary", "")[:80]
        print(f"{PREFIX} Previous handoff loaded: {summary}")
        next_steps = h.get("next_steps") or []
        if next_steps:
            print(f"{PREFIX} Next steps from previous session:")
            for step in next_steps:
                print(f"  - {step}")
    else:
        print(f"{PREFIX} No previous handoff found (first session)")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Must never block Claude Code startup
        pass

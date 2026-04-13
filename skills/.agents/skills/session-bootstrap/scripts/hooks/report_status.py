#!/usr/bin/env python3
"""Report agent status on Claude Code Stop/SubagentStop events.

This script is called by Claude Code's Stop and SubagentStop lifecycle hooks.
It reads loop-state.json from the current directory if it exists, compares
against a status cache to avoid duplicate reports, and calls POST /status/report
on the coordinator HTTP API.

Uses only stdlib (urllib) — no third-party dependencies required.

Usage:
    python agent-coordinator/scripts/report_status.py [--subagent]

Environment variables:
    AGENT_ID: Agent identifier
    CHANGE_ID: Fallback change_id if loop-state.json is missing
    COORDINATION_API_URL: Coordinator HTTP API URL (optional; skips if unset)
    COORDINATION_API_KEY: API key for auth header
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


def _coordinator_url() -> str | None:
    """Resolve coordinator base URL from environment. Returns None when unset."""
    url = os.environ.get("COORDINATION_API_URL")
    return url.rstrip("/") if url else None


def _read_loop_state() -> dict:
    """Read loop-state.json from the current directory. Returns {} on failure."""
    path = Path.cwd() / "loop-state.json"
    if not path.exists():
        print(
            f"report_status: loop-state.json not found at {path}, using phase=UNKNOWN",
            file=sys.stderr,
        )
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(
            f"report_status: invalid JSON in {path}: {exc}, using phase=UNKNOWN",
            file=sys.stderr,
        )
        return {}
    except OSError as exc:
        print(
            f"report_status: cannot read {path}: {exc}, using phase=UNKNOWN",
            file=sys.stderr,
        )
        return {}


def _read_status_cache() -> dict:
    """Read .status-cache.json from the current directory."""
    path = Path.cwd() / ".status-cache.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_status_cache(data: dict) -> None:
    """Write .status-cache.json to the current directory."""
    path = Path.cwd() / ".status-cache.json"
    try:
        path.write_text(json.dumps(data, indent=2) + "\n")
    except OSError:
        pass


def main() -> None:
    is_subagent = "--subagent" in sys.argv

    agent_id = os.environ.get("AGENT_ID", "unknown")
    base_url = _coordinator_url()
    if not base_url:
        print(
            "report_status: COORDINATION_API_URL not set, skipping",
            file=sys.stderr,
        )
        return

    api_key = os.environ.get("COORDINATION_API_KEY", "")

    # Read loop state
    loop_state = _read_loop_state()
    phase = loop_state.get("current_phase", "UNKNOWN")
    change_id = loop_state.get("change_id") or os.environ.get("CHANGE_ID", "unknown")
    findings_trend = loop_state.get("findings_trend", [])

    # Build message
    if findings_trend:
        message = f"Findings trend: {findings_trend[-3:]}"
    else:
        message = "Phase transition"

    needs_human = phase == "ESCALATE"
    event_type = "status.escalated" if needs_human else "status.phase_transition"

    # Check cache to avoid duplicate reports
    cache = _read_status_cache()
    if cache.get("last_phase") == phase and cache.get("change_id") == change_id:
        # Same phase, skip duplicate report
        return

    # Build request payload
    payload = {
        "agent_id": agent_id,
        "change_id": change_id,
        "phase": phase,
        "message": message,
        "needs_human": needs_human,
        "event_type": event_type,
        "metadata": {
            "is_subagent": is_subagent,
        },
    }

    # Send report via stdlib urllib
    url = f"{base_url}/status/report"
    data = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "agentic-coding-tools/0.1",
    }
    if api_key:
        headers["X-API-Key"] = api_key

    req = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=5.0) as resp:
            if resp.status < 300:
                _write_status_cache({"last_phase": phase, "change_id": change_id})
    except URLError as exc:
        # HTTPError (subclass of URLError) carries a status code
        if hasattr(exc, "code") and exc.code == 422:  # type: ignore[attr-defined]
            # Validation error will never recover; cache to prevent infinite retries
            _write_status_cache({"last_phase": phase, "change_id": change_id})
    except (OSError, ValueError):
        # Must not block Claude Code — swallow all errors
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Top-level guard: never block Claude Code
        pass

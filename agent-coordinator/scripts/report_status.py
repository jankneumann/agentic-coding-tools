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
import logging
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

# wire-autopilot-phase-subagents (D-2): closed-set archetype enum mirrored
# from agent-coordinator/agents/archetypes.yaml::phase_mapping. Must stay in
# sync with the Pydantic Literal in src/coordination_api.py::StatusReportRequest
# and the SQL CHECK constraint in
# database/migrations/023_add_phase_archetype.sql.
_VALID_PHASE_ARCHETYPES: frozenset[str] = frozenset(
    {"architect", "reviewer", "implementer", "analyst", "runner"}
)

logger = logging.getLogger(__name__)


def _coordinator_url() -> str | None:
    """Resolve coordinator base URL from environment. Returns None when unset."""
    url = os.environ.get("COORDINATION_API_URL")
    return url.rstrip("/") if url else None


def _read_loop_state() -> dict[str, Any]:
    """Read loop-state.json from the current directory. Returns {} on failure."""
    path = Path.cwd() / "loop-state.json"
    if not path.exists():
        print(
            f"report_status: loop-state.json not found at {path}, using phase=UNKNOWN",
            file=sys.stderr,
        )
        return {}
    try:
        parsed: Any = json.loads(path.read_text())
        if isinstance(parsed, dict):
            return parsed
        return {}
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


def _validate_phase_archetype(value: object) -> str | None:
    """Defensive validation against the closed archetype enum.

    wire-autopilot-phase-subagents (D-2, task 3.10): even though the API
    layer enforces enum membership via Pydantic ``Literal`` and the database
    enforces it via a CHECK constraint, the hook validates locally as
    defense-in-depth — local file tampering or a malformed loop-state.json
    must never cause the hook to forward an invalid value (which would
    waste a 422 round-trip and pollute the audit log).

    Returns ``value`` when valid, ``None`` otherwise. ``None`` and any
    non-string input always return ``None``.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        logger.warning(
            "report_status: phase_archetype is not a string (got %s); dropping",
            type(value).__name__,
        )
        return None
    if value in _VALID_PHASE_ARCHETYPES:
        return value
    logger.warning(
        "report_status: dropping invalid phase_archetype value %r (allowed: %s)",
        value,
        sorted(_VALID_PHASE_ARCHETYPES),
    )
    return None


def _read_status_cache() -> dict[str, Any]:
    """Read .status-cache.json from the current directory."""
    path = Path.cwd() / ".status-cache.json"
    if not path.exists():
        return {}
    try:
        parsed: Any = json.loads(path.read_text())
        if isinstance(parsed, dict):
            return parsed
        return {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_status_cache(data: dict[str, Any]) -> None:
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
    # wire-autopilot-phase-subagents (D-2): pull the resolved archetype set
    # by autopilot.run_phase_subagent (and INIT recorder). Validate locally
    # so tampered or stale state files can't push garbage to the API.
    raw_phase_archetype = loop_state.get("phase_archetype")
    phase_archetype = _validate_phase_archetype(raw_phase_archetype)

    # Build message
    if findings_trend:
        message = f"Findings trend: {findings_trend[-3:]}"
    else:
        message = "Phase transition"

    needs_human = phase == "ESCALATE"
    event_type = "status.escalated" if needs_human else "status.phase_transition"

    # Check cache to avoid duplicate reports. Dedupe key includes
    # phase_archetype so a phase that re-runs under a different archetype
    # (rare but legitimate, e.g. operator-forced re-resolution) still
    # reaches the coordinator instead of being permanently masked by
    # cached state. Older cache entries without the key compare equal to
    # any current archetype and trigger a refresh.
    cache = _read_status_cache()
    same_phase = cache.get("last_phase") == phase
    same_change = cache.get("change_id") == change_id
    same_archetype = cache.get("last_phase_archetype") == phase_archetype
    if same_phase and same_change and same_archetype:
        # Same phase + change + archetype, skip duplicate report
        return

    # Build request payload
    payload: dict[str, Any] = {
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
    # Always set the field — explicit `null` round-trips to FastAPI's
    # ``Literal[...] | None`` and is accepted as backward-compatible per
    # the spec scenario "Status report without phase_archetype is accepted".
    # Sending the key explicitly (even as null) makes the wire contract
    # unambiguous to log forwarders.
    payload["phase_archetype"] = phase_archetype

    # Send report via stdlib urllib
    url = f"{base_url}/status/report"
    # Explicit scheme allow-list closes the SonarCloud B310 hotspot:
    # the URL is operator-controlled (env var COORDINATION_API_URL), but
    # accidental misconfiguration to file:// or custom schemes would
    # otherwise be permitted by urlopen. http+https only.
    if not url.startswith(("http://", "https://")):
        return  # silently skip; this is a best-effort observability hook
    data = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "agentic-coding-tools/0.1",
    }
    if api_key:
        headers["X-API-Key"] = api_key

    req = Request(url, data=data, headers=headers, method="POST")
    try:
        # nosec B310: scheme allow-list above prevents file:// / custom schemes.
        with urlopen(req, timeout=5.0) as resp:  # noqa: S310
            if resp.status < 300:
                _write_status_cache(
                    {
                        "last_phase": phase,
                        "change_id": change_id,
                        "last_phase_archetype": phase_archetype,
                    }
                )
    except URLError as exc:
        # HTTPError (subclass of URLError) carries a status code
        if hasattr(exc, "code") and getattr(exc, "code", None) == 422:
            # Validation error will never recover; cache to prevent infinite retries
            _write_status_cache(
                    {
                        "last_phase": phase,
                        "change_id": change_id,
                        "last_phase_archetype": phase_archetype,
                    }
                )
    except (OSError, ValueError):
        # Must not block Claude Code — swallow all errors
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Top-level guard: never block Claude Code
        pass

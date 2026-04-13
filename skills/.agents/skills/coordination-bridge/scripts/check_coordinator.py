#!/usr/bin/env python3
"""Check coordinator availability and detect capabilities.

Probes the coordinator via HTTP API first, then falls back to MCP tool
detection for CLI environments where no HTTP server is running.  Outputs JSON
suitable for consumption by parallel workflow skills.

Usage:
    python3 agent-coordinator/scripts/check_coordinator.py [--url URL] [--json] [--quiet]

Environment:
    COORDINATION_API_URL  — coordinator base URL (default: http://localhost:8081)

Exit codes:
    0 — coordinator available
    1 — coordinator unavailable
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

DEFAULT_URL = "http://localhost:8081"

# Endpoints that confirm a capability is *actually routed*.
# We probe the real capability routes — a 401/403 proves the route exists
# (auth required), 404 means not mounted, 2xx means available.
# Capabilities with no dedicated HTTP route (handoff, policy) are MCP-only
# and fall back to /health (presence of the server implies these features).
ROUTE_PROBES: dict[str, str] = {
    "CAN_LOCK": "/locks/status/__probe__",
    "CAN_QUEUE_WORK": "/work/get",
    "CAN_GUARDRAILS": "/guardrails/check",
    "CAN_MEMORY": "/memory/query",
    "CAN_DISCOVER": "/profiles/me",
    "CAN_HANDOFF": "/handoffs/read",
    "CAN_POLICY": "/policy/check",
    "CAN_AUDIT": "/audit",
    "CAN_FEATURE_REGISTRY": "/features/active",
    "CAN_MERGE_QUEUE": "/merge-queue",
}

# MCP tool names that map to each capability flag.
# Used for fallback detection when no HTTP server is running.
MCP_TOOL_PROBES: dict[str, str] = {
    "CAN_LOCK": "mcp__coordination__acquire_lock",
    "CAN_QUEUE_WORK": "mcp__coordination__get_work",
    "CAN_GUARDRAILS": "mcp__coordination__check_guardrails",
    "CAN_MEMORY": "mcp__coordination__remember",
    "CAN_HANDOFF": "mcp__coordination__write_handoff",
    "CAN_DISCOVER": "mcp__coordination__discover_agents",
    "CAN_POLICY": "mcp__coordination__check_policy",
    "CAN_AUDIT": "mcp__coordination__query_audit",
    "CAN_FEATURE_REGISTRY": "mcp__coordination__list_active_features",
    "CAN_MERGE_QUEUE": "mcp__coordination__get_merge_queue",
}


def check_health(base_url: str, timeout: float = 3.0) -> dict | None:
    """Probe /health and return parsed JSON, or None on failure."""
    url = f"{base_url.rstrip('/')}/health"
    req = Request(url, method="GET")
    req.add_header("User-Agent", "agentic-coding-tools/0.1")
    try:
        with urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read())
    except (URLError, OSError, ValueError, json.JSONDecodeError):
        pass
    return None


def probe_route(base_url: str, path: str, timeout: float = 2.0) -> bool:
    """Return True if the route responds (any 2xx/4xx — not 404 'not found')."""
    url = f"{base_url.rstrip('/')}{path}"
    req = Request(url, method="GET")
    req.add_header("User-Agent", "agentic-coding-tools/0.1")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.status < 500
    except URLError as exc:
        # HTTPError is a subclass of URLError and carries a status code
        if hasattr(exc, "code"):
            code = exc.code  # type: ignore[attr-defined]
            # 401/403 means the route exists but requires auth → capability present
            # 404 means route not mounted → capability absent
            # 405 means route exists but wrong method → capability present
            return code not in (404,)
        return False
    except (OSError, ValueError):
        return False


def detect_mcp_server() -> bool:
    """Detect whether the coordination MCP server is configured and connected.

    Uses ``claude mcp get coordination`` to check registration and status.
    Returns True if the server is connected, False otherwise.
    """
    claude_bin = shutil.which("claude")
    if not claude_bin:
        return False
    try:
        proc = subprocess.run(
            [claude_bin, "mcp", "get", "coordination"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            return False
        # Output contains "Status: ✓ Connected" when the server is up
        return "Connected" in proc.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


def detect(base_url: str) -> dict:
    """Run full detection and return a result dict."""
    health = check_health(base_url)

    result: dict = {
        "COORDINATOR_AVAILABLE": False,
        "COORDINATION_TRANSPORT": "none",
        "coordinator_url": base_url,
        "health": None,
        "CAN_LOCK": False,
        "CAN_QUEUE_WORK": False,
        "CAN_DISCOVER": False,
        "CAN_GUARDRAILS": False,
        "CAN_MEMORY": False,
        "CAN_HANDOFF": False,
        "CAN_POLICY": False,
        "CAN_AUDIT": False,
    }

    if health is not None:
        # HTTP transport available — probe individual capability routes
        result["COORDINATOR_AVAILABLE"] = True
        result["COORDINATION_TRANSPORT"] = "http"
        result["health"] = health
        for cap, path in ROUTE_PROBES.items():
            result[cap] = probe_route(base_url, path)
        return result

    # HTTP unavailable — fall back to MCP server detection for CLI environments.
    # `claude mcp get coordination` tells us if the server is registered and
    # connected.  When connected, all coordination tools are available since
    # they ship as a single MCP server.
    if detect_mcp_server():
        result["COORDINATOR_AVAILABLE"] = True
        result["COORDINATION_TRANSPORT"] = "mcp"
        for cap in MCP_TOOL_PROBES:
            result[cap] = True
        return result

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Check coordinator availability")
    parser.add_argument(
        "--url",
        default=os.environ.get("COORDINATION_API_URL", DEFAULT_URL),
        help=f"Coordinator base URL (default: {DEFAULT_URL})",
    )
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    parser.add_argument("--quiet", action="store_true", help="Suppress non-JSON output")
    args = parser.parse_args()

    result = detect(args.url)

    if args.json_output:
        print(json.dumps(result, indent=2))
    elif not args.quiet:
        status = "AVAILABLE" if result["COORDINATOR_AVAILABLE"] else "UNAVAILABLE"
        print(f"Coordinator: {status}")
        print(f"  URL: {result['coordinator_url']}")
        print(f"  Transport: {result['COORDINATION_TRANSPORT']}")
        if result["health"]:
            h = result["health"]
            print(f"  Version: {h.get('version', '?')}")
            print(f"  DB: {h.get('db', '?')}")
        caps = [k for k in result if k.startswith("CAN_")]
        for cap in sorted(caps):
            symbol = "+" if result[cap] else "-"
            print(f"  [{symbol}] {cap}")

    return 0 if result["COORDINATOR_AVAILABLE"] else 1


if __name__ == "__main__":
    sys.exit(main())

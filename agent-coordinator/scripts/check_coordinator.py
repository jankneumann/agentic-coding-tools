#!/usr/bin/env python3
"""Check coordinator availability and detect capabilities.

Probes the coordinator HTTP API health endpoint and derives CAN_* capability
flags from the available endpoints.  Outputs JSON suitable for consumption by
parallel workflow skills.

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
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

DEFAULT_URL = "http://localhost:8081"

# Endpoint groups that map to capability flags.
# Each entry: CAN_* flag → list of (method, path) to probe.
CAPABILITY_PROBES: dict[str, list[tuple[str, str]]] = {
    "CAN_LOCK": [("GET", "/locks/status/__probe__")],
    "CAN_QUEUE_WORK": [("GET", "/health")],  # work endpoints need auth; health implies they exist
    "CAN_DISCOVER": [("GET", "/health")],
    "CAN_GUARDRAILS": [("GET", "/health")],
    "CAN_MEMORY": [("GET", "/health")],
    "CAN_HANDOFF": [("GET", "/health")],
    "CAN_POLICY": [("GET", "/health")],
    "CAN_AUDIT": [("GET", "/health")],
}

# Endpoints that confirm a capability is *actually routed* (not just implied by
# a healthy server).  We probe unauthenticated read-only endpoints where possible.
# For write-only endpoints we accept the health check as sufficient evidence
# because the API mounts all routes in create_coordination_api().
ROUTE_PROBES: dict[str, str] = {
    "CAN_LOCK": "/locks/status/__probe__",
    "CAN_QUEUE_WORK": "/health",
    "CAN_GUARDRAILS": "/health",
    "CAN_MEMORY": "/health",
    "CAN_HANDOFF": "/health",
    "CAN_DISCOVER": "/health",
    "CAN_POLICY": "/health",
    "CAN_AUDIT": "/health",
}


def check_health(base_url: str, timeout: float = 3.0) -> dict | None:
    """Probe /health and return parsed JSON, or None on failure."""
    url = f"{base_url.rstrip('/')}/health"
    req = Request(url, method="GET")
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

    if health is None:
        return result

    result["COORDINATOR_AVAILABLE"] = True
    result["COORDINATION_TRANSPORT"] = "http"
    result["health"] = health

    # Probe individual capabilities via their routes
    for cap, path in ROUTE_PROBES.items():
        result[cap] = probe_route(base_url, path)

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

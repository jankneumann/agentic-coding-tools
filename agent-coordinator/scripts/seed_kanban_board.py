#!/usr/bin/env python3
"""Seed demo data for the kanban-viz board.

Populates the coordinator work queue with a representative set of issues
spanning every Kanban column (backlog, in-flight, done) and every vendor
swimlane so the board renders something useful in dev. Idempotent: re-running
adds the `seed:<run-id>` label so a `--reset` pass can wipe just the seeded
rows without touching real coordinator work.

Limitation worth knowing: `claimed_by` / `claimed_at` / `completed_at` columns
are populated by the `/work/claim` + `/work/complete` service paths, not by
`/issues/update`. This seeder uses HTTP-only and flips status directly via
`/issues/update`, so cards appear in the right column but vendor-swimlane
bucketing (which keys on `claimed_by`) stays empty until a real claim runs.
For a fully-realistic demo, run `/explore-feature` or any other coordinator
flow that actually claims work after the seed.

Usage:
    python3 agent-coordinator/scripts/seed_kanban_board.py \\
        --api-url http://localhost:8081 \\
        --api-key dev-key-001 \\
        --change-id demo-kanban

    # Wipe seeded rows from a prior run:
    python3 agent-coordinator/scripts/seed_kanban_board.py --reset

Environment defaults:
    COORDINATION_API_URL (or COORDINATOR_URL)   API base URL
    COORDINATION_API_KEYS                       First key in the comma list is used
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any

DEFAULT_CHANGE_ID = "demo-kanban"
DEFAULT_API_URL = "http://localhost:8081"
SEED_LABEL_PREFIX = "seed:"
VENDORS = ("claude", "codex", "gemini")


@dataclass(frozen=True)
class SeedIssue:
    """One demo card to plant on the board."""

    title: str
    target_status: str  # raw work_queue status (pending/claimed/running/completed/failed/blocked)
    priority: int
    vendor: str | None  # for `vendor:<name>` swimlane label; None = no swimlane
    description: str = ""


# Hand-picked set: every column populated, vendor swimlanes covered, a few
# realistic priority/title combos. Order matters only for visual debugging —
# the board itself sorts by priority + recency.
SEED_SET: tuple[SeedIssue, ...] = (
    # ---------- backlog (pending) ----------
    SeedIssue("Wire telemetry into autopilot dispatch", "pending", 2, "claude",
              "Cross-vendor latency comparison."),
    SeedIssue("Document SSE token revocation", "pending", 4, None,
              "Backfill docs/ entry for D11 fail-closed behavior."),
    SeedIssue("Audit lockfile drift gate", "pending", 5, "codex",
              "Surface uv.lock vs manifest mismatch in /merge-pull-requests."),
    SeedIssue("Investigate gitleaks allowlists plural bug", "pending", 3, None,
              "File upstream issue + add regression test."),

    # ---------- backlog (blocked) ----------
    SeedIssue("Migrate coordinator to ParadeDB 18.5", "blocked", 6, "gemini",
              "Blocked on upstream pgvector compat patch."),

    # ---------- in-flight (claimed) ----------
    SeedIssue("Refactor coordinator-task-status-renderer markers", "claimed", 3, "claude"),
    SeedIssue("Add holdout-gate to /implement-feature", "claimed", 2, "codex"),

    # ---------- in-flight (running) ----------
    SeedIssue("Build kanban-viz vendor swimlane projection", "running", 1, "claude"),
    SeedIssue("Sync skill-tier negotiation tests", "running", 4, "gemini"),
    SeedIssue("Wire merge-train priority into autopilot-roadmap", "running", 2, "codex"),

    # ---------- done (completed, recent) ----------
    SeedIssue("Ship add-coordinator-kanban-viz PR #178", "completed", 1, "claude"),
    SeedIssue("Patch pip-audit ignore list for PYSEC-2025-183", "completed", 3, None),
    SeedIssue("Bump idna 3.11 → 3.15 (CVE-2026-45409)", "completed", 2, None),

    # ---------- done (failed) ----------
    SeedIssue("Attempt secret-scan with [[allowlists]] plural form", "failed", 5, "claude",
              "gitleaks 8.24.3 silently drops the plural form under [extend] useDefault=true."),
)


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only — keep the script dependency-free)
# ---------------------------------------------------------------------------


def _request(
    method: str,
    url: str,
    api_key: str,
    body: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any]]:
    """Run an HTTP request and return ``(status, parsed_body)``.

    Raises URLError / HTTPError on network / non-2xx (caller decides what to
    tolerate). Returns ``({}, status)`` on empty body.
    """
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            parsed = json.loads(raw) if raw else {}
            return resp.status, parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read() or b""
        try:
            parsed = json.loads(raw) if raw else {"error": exc.reason}
        except json.JSONDecodeError:
            parsed = {"error": raw.decode("utf-8", errors="replace")}
        return exc.code, parsed


def _resolve_defaults(args: argparse.Namespace) -> tuple[str, str]:
    api_url = (
        args.api_url
        or os.environ.get("COORDINATION_API_URL")
        or os.environ.get("COORDINATOR_URL")
        or DEFAULT_API_URL
    ).rstrip("/")
    api_key = args.api_key or (
        os.environ.get("COORDINATION_API_KEYS", "").split(",")[0].strip()
        or os.environ.get("COORDINATION_API_KEY", "")
    )
    if not api_key:
        print(
            "ERROR: no API key. Pass --api-key or set COORDINATION_API_KEYS / "
            "COORDINATION_API_KEY in env.",
            file=sys.stderr,
        )
        sys.exit(2)
    return api_url, api_key


# ---------------------------------------------------------------------------
# Seed / reset operations
# ---------------------------------------------------------------------------


def _list_seeded_issues(api_url: str, api_key: str, run_label: str) -> list[dict[str, Any]]:
    """Return all open issues tagged with ``run_label``."""
    status, body = _request(
        "POST", f"{api_url}/issues/list", api_key, body={"labels": [run_label], "limit": 100}
    )
    if status != 200:
        return []
    return body.get("issues", []) or body.get("items", []) or []


def _close_issues(api_url: str, api_key: str, issue_ids: list[str], reason: str) -> int:
    """Close the listed issues; return count successfully closed."""
    if not issue_ids:
        return 0
    status, body = _request(
        "POST",
        f"{api_url}/issues/close",
        api_key,
        body={"issue_ids": issue_ids, "reason": reason},
    )
    if status != 200 or not body.get("success"):
        print(f"  warn: close failed ({status}): {body.get('reason') or body}")
        return 0
    # /issues/close returns either a count or per-id results
    return len(issue_ids)


def reset_seeded(api_url: str, api_key: str) -> int:
    """Close every issue with any ``seed:<run-id>`` label across past runs."""
    # We can't list-by-prefix; query by the umbrella label "seed:*" doesn't
    # exist server-side. Instead, list all "seed:active" issues — we tag each
    # seeded card with both the per-run label AND a stable umbrella label.
    issues = _list_seeded_issues(api_url, api_key, run_label="seed:active")
    ids = [i["id"] for i in issues if i.get("id")]
    if not ids:
        print("No seeded issues found.")
        return 0
    print(f"Closing {len(ids)} seeded issues...")
    closed = _close_issues(api_url, api_key, ids, reason="kanban seed reset")
    print(f"  closed {closed} / {len(ids)}")
    return closed


def seed(api_url: str, api_key: str, change_id: str) -> int:
    """Plant the SEED_SET. Returns count of issues created (not flipped)."""
    run_id = uuid.uuid4().hex[:8]
    run_label = f"{SEED_LABEL_PREFIX}{run_id}"
    umbrella_label = f"{SEED_LABEL_PREFIX}active"
    change_label = f"change:{change_id}"

    print(f"Seeding {len(SEED_SET)} demo issues into change_id={change_id!r}...")
    print(f"  run-id={run_id} (re-run with --reset to wipe)")
    created = 0
    for spec in SEED_SET:
        labels = [change_label, umbrella_label, run_label]
        if spec.vendor:
            labels.append(f"vendor:{spec.vendor}")

        # Step 1: create (lands as `pending`).
        status, body = _request(
            "POST",
            f"{api_url}/issues/create",
            api_key,
            body={
                "title": spec.title,
                "description": spec.description or None,
                "issue_type": "task",
                "priority": spec.priority,
                "labels": labels,
                "assignee": (
                    f"agent-{spec.vendor}" if spec.vendor else None
                ),
            },
        )
        if status != 200 or not body.get("success"):
            print(
                f"  skip {spec.title!r}: create failed ({status}) "
                f"{body.get('reason') or body}"
            )
            continue
        issue_id = body["issue"]["id"]
        created += 1

        # Step 2: if target_status != pending, flip via /issues/update so the
        # work_queue trigger fires NOTIFY (which clients receive as a real
        # transition event — handy for verifying SSE wiring during a seed).
        if spec.target_status != "pending":
            status, body = _request(
                "POST",
                f"{api_url}/issues/update",
                api_key,
                body={"issue_id": issue_id, "status": spec.target_status},
            )
            if status != 200 or not body.get("success"):
                print(
                    f"  warn {spec.title!r}: flip to {spec.target_status!r} failed "
                    f"({status}) {body.get('reason') or body}"
                )
                continue

        status_emoji = {
            "pending": "🅿️ ",
            "blocked": "🚫",
            "claimed": "🤝",
            "running": "🏃",
            "completed": "✅",
            "failed": "💥",
        }.get(spec.target_status, "  ")
        print(f"  {status_emoji} [{spec.target_status:9}] {spec.title}")
        # Tiny gap so the SSE stream gets a chance to send each event as a
        # distinct frame (back-pressure coalesces bursts >50/sec into a
        # snapshot — see event_stream._BACKPRESSURE_LIMIT).
        time.sleep(0.02)

    print(f"\nSeeded {created}/{len(SEED_SET)} issues.")
    print(f"Open the board: http://localhost:5173 (change_ids={change_id})")
    return created


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--api-url", help=f"Coordinator base URL (default: {DEFAULT_API_URL})")
    parser.add_argument("--api-key", help="API key (default: first of COORDINATION_API_KEYS env)")
    parser.add_argument(
        "--change-id",
        default=DEFAULT_CHANGE_ID,
        help=f"change_id to tag seeded issues with (default: {DEFAULT_CHANGE_ID})",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Close all previously-seeded issues (those tagged seed:active) and exit",
    )
    args = parser.parse_args()
    api_url, api_key = _resolve_defaults(args)

    # Quick health probe — refuse to seed against a coordinator that isn't up.
    status, _ = _request("GET", f"{api_url}/health", api_key, body=None, timeout=3.0)
    if status >= 400 and status != 200:
        print(f"ERROR: coordinator at {api_url} returned {status} for /health", file=sys.stderr)
        return 1

    if args.reset:
        reset_seeded(api_url, api_key)
        return 0
    created = seed(api_url, api_key, args.change_id)
    return 0 if created > 0 else 1


if __name__ == "__main__":
    sys.exit(main())

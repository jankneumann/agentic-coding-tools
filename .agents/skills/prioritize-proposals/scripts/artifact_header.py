"""Mandatory artifact header for /prioritize-proposals report.json.

Aligned with the codeviz event-artifact schema (schema_version, generated_at,
git_sha, generator, run_id, event_kind). Once `skills/shared/artifact_header.py`
ships (codeviz roadmap), migrate this module to that helper without changing
the on-disk schema.

Design decision: D4 (mandatory artifact header).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
GENERATOR = "prioritize-proposals@1.0"
EVENT_KIND = "priorities-report"


def make_header(*, now: datetime, git_sha: str, run_id: str) -> dict[str, Any]:
    """Construct the six-field mandatory header for an event artifact.

    `now` must be a UTC-aware datetime; `git_sha` must be the full 40-char hash.
    """
    if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError("now must be a UTC-aware datetime")
    if len(git_sha) != 40:
        raise ValueError(f"git_sha must be the full 40-char hash, got length {len(git_sha)}")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": git_sha,
        "generator": GENERATOR,
        "run_id": run_id,
        "event_kind": EVENT_KIND,
    }


def wrap_report(header: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """Return `{"_header": header, "report": body}` without mutating body."""
    return {"_header": header, "report": body}


def _cli() -> int:
    """Wrap a report.json on stdin with a fresh header. Reads:
    - --git-sha (or `git rev-parse HEAD`)
    - --run-id (required)
    """
    import argparse
    import subprocess

    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--git-sha", default=None)
    p.add_argument("--in", dest="input_path", default="-", help="report body JSON (default: stdin)")
    p.add_argument("--out", dest="output_path", default="-", help="wrapped JSON (default: stdout)")
    args = p.parse_args()

    git_sha = args.git_sha
    if not git_sha:
        git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()

    if args.input_path == "-":
        body = json.load(sys.stdin)
    else:
        body = json.loads(Path(args.input_path).read_text())

    header = make_header(now=datetime.now(timezone.utc), git_sha=git_sha, run_id=args.run_id)
    wrapped = wrap_report(header, body)

    payload = json.dumps(wrapped, indent=2)
    if args.output_path == "-":
        sys.stdout.write(payload + "\n")
    else:
        Path(args.output_path).write_text(payload + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

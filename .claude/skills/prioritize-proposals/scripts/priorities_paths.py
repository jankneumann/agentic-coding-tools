"""Run-id and path construction for /prioritize-proposals output.

Pure functions only — no I/O, no subprocess. The bash entrypoint in SKILL.md
is responsible for capturing `datetime.now(UTC)` and `git rev-parse HEAD` and
passing them in. Keeping these pure makes the test suite fast and deterministic.

Design decisions: D1 (directory layout), D2 (run-id format), D3 (flat-file latest).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

RUN_ID_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-(\d{6}|legacy)(?:-([a-f0-9]+))?)?$")


@dataclass(frozen=True)
class PrioritiesPaths:
    """Bundle of paths for a single /prioritize-proposals run."""

    dated_dir: Path
    report_md: Path
    report_json: Path
    latest_md: Path
    latest_json: Path
    archive_dir: Path
    archive_destination: Path


def build_run_id(now: datetime, head_sha: str) -> str:
    """Return `YYYY-MM-DD-HHMMSS-<short-sha>` for the given UTC time and HEAD.

    `now` MUST carry a timezone-aware UTC value; naive datetimes are rejected
    so callers can't accidentally produce timezone-dependent run-ids.
    """
    if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError("now must be a UTC-aware datetime")
    if len(head_sha) < 7:
        raise ValueError(f"head_sha must be at least 7 characters, got {head_sha!r}")
    return f"{now:%Y-%m-%d-%H%M%S}-{head_sha[:7]}"


def build_paths(base: Path, run_id: str) -> PrioritiesPaths:
    """Compute all paths for a run given the priorities base directory and run-id."""
    dated_dir = base / run_id
    archive_dir = base / "archive"
    return PrioritiesPaths(
        dated_dir=dated_dir,
        report_md=dated_dir / "report.md",
        report_json=dated_dir / "report.json",
        latest_md=base / "latest.md",
        latest_json=base / "latest.json",
        archive_dir=archive_dir,
        archive_destination=archive_dir / run_id,
    )


def parse_run_id(name: str) -> tuple[str, str, str]:
    """Split a run-directory name into (date, hms, sha). Handles `-legacy` suffix.

    Returns `(date, "", "legacy")` for a legacy entry like `2026-05-04-legacy`.
    Raises ValueError for anything that doesn't start with YYYY-MM-DD.
    """
    m = RUN_ID_RE.match(name)
    if not m:
        raise ValueError(f"not a priorities run-id directory: {name!r}")
    date = m.group(1)
    middle = m.group(2) or ""
    sha = m.group(3) or ""
    if middle == "legacy":
        return date, "", "legacy"
    return date, middle, sha


def _cli() -> int:
    """Minimal CLI for shell invocation from SKILL.md."""
    import argparse
    import subprocess

    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run-id", help="Print a fresh run-id for HEAD at UTC now")
    paths = sub.add_parser("paths", help="Print paths for a given run-id")
    paths.add_argument("run_id")
    paths.add_argument("--base", default="openspec/priorities")
    args = p.parse_args()

    if args.cmd == "run-id":
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
        print(build_run_id(datetime.now(timezone.utc), head))
        return 0

    if args.cmd == "paths":
        paths_bundle = build_paths(Path(args.base), args.run_id)
        for name, value in paths_bundle.__dict__.items():
            print(f"{name}={value}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())

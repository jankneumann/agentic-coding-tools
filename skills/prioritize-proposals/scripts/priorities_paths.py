"""Run-id and path construction for /prioritize-proposals output.

Pure functions only — no I/O, no subprocess. The bash entrypoint in SKILL.md
is responsible for capturing `datetime.now(UTC)` and `git rev-parse HEAD` and
passing them in. Keeping these pure makes the test suite fast and deterministic.

`build_run_id`, `RUN_ID_RE`, and `parse_run_id` are defined in
`skills/shared/artifact_paths.py` and re-exported here unchanged (design
D2) — this module keeps only what is genuinely its own: the
`PrioritiesPaths` dataclass and `build_paths`, which name this skill's own
`report.{md,json}` filenames.

Design decisions: D1 (directory layout), D2 (shared run-id format), D3
(flat-file latest).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.artifact_paths import (  # noqa: E402
    RUN_ID_RE,
    build_run_id,
    parse_run_id,
)

__all__ = [
    "RUN_ID_RE",
    "PrioritiesPaths",
    "build_run_id",
    "build_paths",
    "parse_run_id",
]


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

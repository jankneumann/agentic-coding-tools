"""Archive-not-delete retention for /prioritize-proposals dated artifacts.

The scan runs after each successful write of a new run directory. It enumerates
active dated directories (excluding `archive/` and the flat-file `latest.{md,json}`),
sorts lexically (which is chronological because run-ids start with YYYY-MM-DD),
and moves the oldest entries past the Nth most recent into `archive/`. Archived
entries are never deleted by this module.

Design decision: D5 (retention policy).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import priorities_paths

ARCHIVE_DIRNAME = "archive"
SKIP_FILENAMES = frozenset({"latest.md", "latest.json"})


@dataclass(frozen=True)
class RetentionResult:
    active_count: int
    archived_count: int


def list_active_runs(priorities_dir: Path) -> list[Path]:
    """Return active dated-run directories, sorted chronologically (lexical sort)."""
    if not priorities_dir.exists():
        return []
    out: list[Path] = []
    for entry in priorities_dir.iterdir():
        if not entry.is_dir():
            continue
        if entry.name == ARCHIVE_DIRNAME:
            continue
        try:
            priorities_paths.parse_run_id(entry.name)
        except ValueError:
            continue
        out.append(entry)
    out.sort(key=lambda p: p.name)
    return out


def apply_retention(priorities_dir: Path, retain: int) -> RetentionResult:
    """Move oldest active runs to `archive/` until `retain` remain.

    Returns the resulting active and archived counts (this run's archive moves only).
    """
    if retain < 1:
        raise ValueError(f"retain must be >= 1, got {retain}")
    active = list_active_runs(priorities_dir)
    if len(active) <= retain:
        return RetentionResult(active_count=len(active), archived_count=0)
    archive_dir = priorities_dir / ARCHIVE_DIRNAME
    archive_dir.mkdir(exist_ok=True)
    to_archive = active[: len(active) - retain]
    for src in to_archive:
        dst = archive_dir / src.name
        shutil.move(str(src), str(dst))
    return RetentionResult(active_count=retain, archived_count=len(to_archive))


def _cli() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--base", default="openspec/priorities")
    p.add_argument("--retain", type=int, default=30)
    args = p.parse_args()
    result = apply_retention(Path(args.base), retain=args.retain)
    print(f"active={result.active_count} archived={result.archived_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

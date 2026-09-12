"""Archive-not-delete retention for /prioritize-proposals dated artifacts.

The scan runs after each successful write of a new run directory. It enumerates
active dated directories (excluding `archive/` and the flat-file `latest.{md,json}`),
sorts lexically (which is chronological because run-ids start with YYYY-MM-DD),
and moves the oldest entries past the Nth most recent into `archive/`. Archived
entries are never deleted by this module.

`apply_retention`, `list_active_runs`, `RetentionResult`, and `ARCHIVE_DIRNAME`
are defined in `skills/shared/artifact_paths.py` and re-exported here
unchanged (design D2, D3) — the retention concern is not specific to this
skill's report filenames.

Design decision: D3 (shared retention module, one DEFAULT_RETAIN).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.artifact_paths import (  # noqa: E402
    ARCHIVE_DIRNAME,
    DEFAULT_RETAIN,
    RetentionResult,
    apply_retention,
    list_active_runs,
)

__all__ = [
    "ARCHIVE_DIRNAME",
    "DEFAULT_RETAIN",
    "RetentionResult",
    "apply_retention",
    "list_active_runs",
]


def _cli() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--base", default="openspec/priorities")
    p.add_argument("--retain", type=int, default=DEFAULT_RETAIN)
    args = p.parse_args()
    result = apply_retention(Path(args.base), retain=args.retain)
    print(f"active={result.active_count} archived={result.archived_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

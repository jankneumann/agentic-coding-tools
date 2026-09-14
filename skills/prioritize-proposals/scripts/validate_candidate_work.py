"""Compatibility wrapper for the shared candidate-work runtime."""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[2] / "shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from candidate_work import (  # noqa: E402,F401
    SCHEMA_FILENAME,
    CandidateWorkCollisionError,
    CandidateWorkValidationError,
    DependencyResolution,
    LifecycleRecord,
    canonical_candidate_work_bytes,
    cli,
    find_schema_path,
    group_lifecycle_records,
    load_candidate_work,
    load_candidate_work_files,
    load_schema,
    resolve_dependency,
    validate_candidate_work,
    validate_candidate_work_batch,
    write_candidate_work,
)


def _cli() -> int:
    """Delegate the historical CLI entry point to the shared implementation."""
    return cli()


if __name__ == "__main__":
    raise SystemExit(_cli())

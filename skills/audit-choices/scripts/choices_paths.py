"""Destination routing and path construction for the audit-choices ledger
pair.

A change-id audit keeps writing to `openspec/changes/<change-id>/`, exactly
as before. A standalone commit-range audit — recorded `change_id` of the
form `range:<base>..<head>` — routes instead to a run-scoped directory
under `openspec/choices/`, mirroring `openspec/priorities/` (design D1).
The routing decision is a single function (`route_output_dir`) kept in the
driver's own code rather than in `skills/shared/`, which stays ignorant of
OpenSpec concepts (D5).

Design decisions: D1 (destination layout), D5 (routing lives with the
driver, keyed on the recorded id's prefix), D7 (the dated directory is
built from the driver's `resolved_now`/`resolved_git_sha` — the same two
values `make_header` receives — never a header field or the audited
`head_sha`), D8 (collision guard: `-2`, `-3`, ... when the computed name
already exists, checking the archive too).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.artifact_paths import ARCHIVE_DIRNAME, build_run_id  # noqa: E402

RANGE_PREFIX = "range:"
CHOICES_ROOT_NAME = "choices"


@dataclass(frozen=True)
class ChoicesPaths:
    """Bundle of paths for a single standalone range-audit run."""

    dated_dir: Path
    json_path: Path
    md_path: Path
    latest_json: Path
    latest_md: Path
    archive_dir: Path
    archive_destination: Path


def is_range_change_id(change_id: str) -> bool:
    """True only for the recorded id's own `range:` prefix (D5) — a change
    id that merely contains `..` or a colon is not special."""
    return change_id.startswith(RANGE_PREFIX)


def choices_root_for(repo_root: Path) -> Path:
    return repo_root / "openspec" / CHOICES_ROOT_NAME


def build_choices_paths(choices_root: Path, run_id: str) -> ChoicesPaths:
    """Compute all paths for a standalone-audit run given the choices root
    and a (already-resolved, collision-free) run-id."""
    dated_dir = choices_root / run_id
    archive_dir = choices_root / ARCHIVE_DIRNAME
    return ChoicesPaths(
        dated_dir=dated_dir,
        json_path=dated_dir / "choices.json",
        md_path=dated_dir / "choices.md",
        latest_json=choices_root / "latest.json",
        latest_md=choices_root / "latest.md",
        archive_dir=archive_dir,
        archive_destination=archive_dir / run_id,
    )


def _run_id_taken(choices_root: Path, run_id: str) -> bool:
    """D8: a run-id is taken if it exists as an active run OR as an
    archived one. Retention frees the active path while the archived copy
    persists, so a later audit computing that same base would otherwise
    collide with the archived directory on the next retention pass."""
    return (choices_root / run_id).exists() or (
        choices_root / ARCHIVE_DIRNAME / run_id
    ).exists()


#: Bound on the collision retry. Reaching it means something is creating
#: these directories faster than we can claim one, which is a broken
#: environment rather than contention — fail loudly instead of spinning.
_MAX_COLLISION_ATTEMPTS = 1000


def _reserve_run_id(choices_root: Path, base_run_id: str) -> str:
    """Reserve and return `base_run_id`, or a `-2`, `-3`, ... suffixed
    sibling when the base is already taken (D8). `build_run_id` resolves to
    the second, so two audits started in the same UTC second at the same
    HEAD would otherwise share a directory and have their snapshots merged.

    The reservation is the `mkdir` itself, with `exist_ok=False`. Testing
    `.exists()` and returning the name would be check-then-write: two
    concurrent audits in the same second could both observe the base as
    free and both proceed, because the real directory creation happens
    later inside `write_ledger_pair` with `exist_ok=True`. `mkdir` is
    atomic against a concurrent creator, so losing the race raises
    `FileExistsError` here and the loop advances instead of two runs
    sharing one directory.

    The archive is checked too: retention frees the active path while the
    archived copy persists, so a later audit computing that same base would
    otherwise collide with the archived directory on the next pass.
    """
    candidate = base_run_id
    for n in range(1, _MAX_COLLISION_ATTEMPTS + 1):
        if not _run_id_taken(choices_root, candidate):
            try:
                (choices_root / candidate).mkdir(parents=True, exist_ok=False)
                return candidate
            except FileExistsError:
                pass  # lost the race; fall through and advance
        candidate = f"{base_run_id}-{n + 1}"
    raise RuntimeError(
        f"could not reserve a run directory for {base_run_id!r} after "
        f"{_MAX_COLLISION_ATTEMPTS} attempts under {choices_root}"
    )


def route_output_dir(
    *, repo_root: Path, change_id: str, now: datetime, git_sha: str
) -> Path:
    """D5: map the recorded `change_id` to an output directory.

    Everything not prefixed `range:` routes to
    `openspec/changes/<change_id>/`, unchanged. A `range:`-prefixed id
    routes to a dated run directory under `openspec/choices/` (D1), built
    from `now`/`git_sha` — the same two values the driver hands
    `make_header` (D7) — with a D8 collision suffix appended if that
    directory (active or archived) already exists.
    """
    if not is_range_change_id(change_id):
        return repo_root / "openspec" / "changes" / change_id
    choices_root = choices_root_for(repo_root)
    base_run_id = build_run_id(now, git_sha)
    run_id = _reserve_run_id(choices_root, base_run_id)
    return choices_root / run_id

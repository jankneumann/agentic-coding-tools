"""Run-id format and archive-not-delete retention shared by the event-class
artifact producers under `openspec/` — `prioritize-proposals`
(`openspec/priorities/`) and `audit-choices`' standalone range form
(`openspec/choices/`).

Pure functions and filesystem moves only — no knowledge of report or ledger
filenames (design D2). Each producer keeps its own small dataclass naming
its own files (`PrioritiesPaths` in `prioritize-proposals/scripts/
priorities_paths.py`, `ChoicesPaths` in `audit-choices/scripts/
choices_paths.py`).

Imported as `shared.artifact_paths` by callers that put the skills root on
`sys.path` first (D2's import bootstrap) — never run as a script itself:

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from shared.artifact_paths import build_run_id, ...

`parents[2]` is `skills/` in the source tree and in an installed runtime
copy alike, because `install.sh` ships `shared/` as a sibling of every
skill directory (`SHARED_LIBS`) — the same relationship `worktree.py` has
with `shared.environment_profile`.

Design decisions: D2 (shared run-id format, not filenames), D3 (retention
moves here too), D8 (collision-suffix support in `RUN_ID_RE`, so
`list_active_runs` keeps counting a `-2`/`-3` sibling instead of silently
letting the tree grow unbounded; `parse_run_id` validates a suffixed name
but always returns a fixed 3-tuple, and `run_id_suffix` reads the suffix
separately).
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_RETAIN = 30
ARCHIVE_DIRNAME = "archive"

# Group 1: date. Group 2: HHMMSS or the literal "legacy". Group 3: short
# git sha (only meaningful alongside group 2's HHMMSS form). Group 4: an
# optional collision suffix (D8) — "-2", "-3", ... appended when the
# computed run-id's directory already exists at the same HEAD in the same
# UTC second. `prioritize-proposals` never emits a suffix; accepting one
# costs it nothing and keeps one format shared.
RUN_ID_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})(?:-(\d{6}|legacy)(?:-([a-f0-9]+))?)?(?:-(\d+))?$"
)


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


def parse_run_id(name: str) -> tuple[str, str, str]:
    """Split a run-directory name into its `(date, hms, sha)` components.

    Returns `(date, hms, sha)` for the ordinary form, `(date, "", "legacy")`
    for a legacy `<date>-legacy` entry, and `(date, "", "")` for a bare
    `<date>`. Raises `ValueError` for anything that doesn't start with
    `YYYY-MM-DD` in the shape this module produces.

    The return shape is always a 3-tuple, regardless of whether `name`
    carries a D8 collision suffix (`-2`, `-3`, ...) — `RUN_ID_RE` accepts
    the suffix so a suffixed directory still validates and round-trips
    through this function, but the suffix itself is not part of the
    component breakdown. Use `run_id_suffix()` to read it. This keeps the
    function's return arity independent of its input, which matters
    because `list_active_runs` — the only production caller — calls this
    purely as a validity check and discards the result entirely; every
    caller that actually destructures the tuple (`prioritize-proposals`'
    frozen tests included) unpacks exactly three values.
    """
    m = RUN_ID_RE.match(name)
    if not m:
        raise ValueError(f"not a valid run-id directory: {name!r}")
    date = m.group(1)
    middle = m.group(2) or ""
    sha = m.group(3) or ""
    if middle == "legacy":
        return (date, "", "legacy")
    return (date, middle, sha)


def run_id_suffix(name: str) -> str | None:
    """Return the D8 collision suffix (e.g. `"2"`) if `name` carries one,
    else `None`. Raises `ValueError` under the same condition as
    `parse_run_id` — anything that isn't a valid run-id directory name."""
    m = RUN_ID_RE.match(name)
    if not m:
        raise ValueError(f"not a valid run-id directory: {name!r}")
    return m.group(4)


@dataclass(frozen=True)
class RetentionResult:
    active_count: int
    archived_count: int


def list_active_runs(base_dir: Path) -> list[Path]:
    """Return active run directories under `base_dir`, sorted chronologically
    (lexical sort — valid because run-ids start with `YYYY-MM-DD`).

    Skips `archive/` and anything that doesn't parse as a run-id.
    """
    if not base_dir.exists():
        return []
    out: list[Path] = []
    for entry in base_dir.iterdir():
        if not entry.is_dir():
            continue
        if entry.name == ARCHIVE_DIRNAME:
            continue
        try:
            parse_run_id(entry.name)
        except ValueError:
            continue
        out.append(entry)
    out.sort(key=lambda p: p.name)
    return out


def apply_retention(base_dir: Path, retain: int) -> RetentionResult:
    """Move the oldest active runs under `base_dir` to `archive/` until
    `retain` remain. Archive-not-delete: nothing is ever destroyed.

    Returns the resulting active and archived counts (this call's archive
    moves only — an existing archive is never re-counted).
    """
    if retain < 1:
        raise ValueError(f"retain must be >= 1, got {retain}")
    active = list_active_runs(base_dir)
    if len(active) <= retain:
        return RetentionResult(active_count=len(active), archived_count=0)
    archive_dir = base_dir / ARCHIVE_DIRNAME
    archive_dir.mkdir(exist_ok=True)
    to_archive = active[: len(active) - retain]
    for src in to_archive:
        dst = archive_dir / src.name
        shutil.move(str(src), str(dst))
    return RetentionResult(active_count=retain, archived_count=len(to_archive))

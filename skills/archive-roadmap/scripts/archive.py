"""Archive a completed roadmap workspace.

Moves ``openspec/roadmaps/<roadmap-id>/`` into
``openspec/roadmaps/archive/<YYYY-MM-DD>-<roadmap-id>/``, mirroring the
OpenSpec change-archive convention. Refuses to archive incomplete roadmaps
unless ``force=True``; refuses to overwrite an existing archive entry.
"""

from __future__ import annotations

import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent / "roadmap-runtime" / "scripts"
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

from models import ItemStatus, load_roadmap  # type: ignore[import-untyped]

# Statuses that mean "this item reached a terminal state by design."
# COMPLETED = work done; SKIPPED = work explicitly written off.
# Anything else (FAILED, BLOCKED, REPLAN_REQUIRED, IN_PROGRESS, APPROVED,
# CANDIDATE) is unfinished and requires --force to archive.
_TERMINAL_STATUSES: frozenset[ItemStatus] = frozenset({
    ItemStatus.COMPLETED,
    ItemStatus.SKIPPED,
})


@dataclass
class ArchiveResult:
    roadmap_id: str
    source: Path
    destination: Path
    item_counts: dict[str, int]
    forced: bool


class IncompleteRoadmapError(Exception):
    """Raised when a roadmap has non-terminal items and force=False."""

    def __init__(self, roadmap_id: str, counts: dict[str, int]) -> None:
        self.roadmap_id = roadmap_id
        self.counts = counts
        super().__init__(
            f"Roadmap {roadmap_id!r} has unfinished items: {counts}. "
            f"Pass force=True to archive anyway."
        )


def _terminal(counts: dict[str, int]) -> bool:
    return all(
        ItemStatus(status) in _TERMINAL_STATUSES
        for status in counts
    )


def archive_roadmap(
    workspace: Path,
    archive_root: Path | None = None,
    *,
    force: bool = False,
    today: date | None = None,
) -> ArchiveResult:
    """Move a roadmap workspace into the archive directory.

    Parameters
    ----------
    workspace:
        Path to the active workspace, e.g. ``openspec/roadmaps/<roadmap-id>``.
    archive_root:
        Parent directory for archived roadmaps. Defaults to
        ``<workspace.parent>/archive`` so a workspace at
        ``openspec/roadmaps/<id>`` archives to
        ``openspec/roadmaps/archive/<date>-<id>``.
    force:
        If True, archive even when items are not in terminal states.
    today:
        Date used for the archive prefix. Defaults to ``date.today()``.
        Exposed for deterministic tests.
    """
    if not workspace.is_dir():
        raise FileNotFoundError(f"Workspace directory not found: {workspace}")

    roadmap_path = workspace / "roadmap.yaml"
    if not roadmap_path.is_file():
        raise FileNotFoundError(f"No roadmap.yaml in workspace: {workspace}")

    roadmap = load_roadmap(roadmap_path)
    counts = dict(Counter(item.status.value for item in roadmap.items))

    if not force and not _terminal(counts):
        raise IncompleteRoadmapError(roadmap.roadmap_id, counts)

    archive_root = archive_root or (workspace.parent / "archive")
    prefix = (today or date.today()).isoformat()
    destination = archive_root / f"{prefix}-{roadmap.roadmap_id}"

    if destination.exists():
        raise FileExistsError(
            f"Archive target already exists: {destination}. "
            f"Rename or remove the existing entry, or pick a different date."
        )

    archive_root.mkdir(parents=True, exist_ok=True)
    shutil.move(str(workspace), str(destination))

    return ArchiveResult(
        roadmap_id=roadmap.roadmap_id,
        source=workspace,
        destination=destination,
        item_counts=counts,
        forced=force and not _terminal(counts),
    )

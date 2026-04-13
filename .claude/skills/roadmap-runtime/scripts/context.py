"""Bounded context assembly for roadmap execution.

Loads only the artifacts needed for the current item's execution phase,
keeping context assembly at O(k) where k = dependency fan-in + recency window.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from learning import select_relevant_entries  # type: ignore[import-untyped]
from models import (  # type: ignore[import-untyped]
    Checkpoint,
    Roadmap,
    RoadmapItem,
    load_checkpoint,
    load_roadmap,
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """Assembled context for executing a single roadmap item."""

    roadmap: Roadmap
    checkpoint: Checkpoint
    current_item: RoadmapItem
    learning_entries: list[dict[str, Any]] = field(default_factory=list)
    child_change_path: str | None = None

    @property
    def item_id(self) -> str:
        return self.current_item.item_id

    @property
    def dependency_learnings(self) -> list[dict[str, Any]]:
        """Learning entries from direct dependencies only."""
        dep_ids = set(self.current_item.depends_on)
        return [e for e in self.learning_entries if e.get("item_id") in dep_ids]


def assemble_context(
    workspace: Path,
    repo_root: Path | None = None,
    recency_window: int = 3,
) -> ExecutionContext:
    """Assemble execution context for the current checkpoint item.

    Loads:
    1. roadmap.yaml — full roadmap state
    2. checkpoint.json — current execution position
    3. Learning entries for direct dependencies + most recent N
    """
    roadmap = load_roadmap(workspace / "roadmap.yaml", repo_root)
    checkpoint = load_checkpoint(workspace / "checkpoint.json", repo_root)

    current_item = roadmap.get_item(checkpoint.current_item_id)
    if current_item is None:
        raise ValueError(
            f"Checkpoint references item '{checkpoint.current_item_id}' "
            f"not found in roadmap"
        )

    learning_entries = select_relevant_entries(
        workspace,
        current_item.depends_on,
        recency_window=recency_window,
    )

    child_change_path = None
    if current_item.change_id:
        child_change_path = f"openspec/changes/{current_item.change_id}"

    logger.info(
        "Context assembled: item=%s, learnings=%d, deps=%s",
        current_item.item_id,
        len(learning_entries),
        current_item.depends_on,
    )

    return ExecutionContext(
        roadmap=roadmap,
        checkpoint=checkpoint,
        current_item=current_item,
        learning_entries=learning_entries,
        child_change_path=child_change_path,
    )


def assemble_summary(workspace: Path) -> dict[str, Any]:
    """Build a lightweight roadmap summary for coordinator memory or quick display."""
    roadmap = load_roadmap(workspace / "roadmap.yaml")

    items_by_status: dict[str, int] = {}
    for item in roadmap.items:
        status = item.status.value
        items_by_status[status] = items_by_status.get(status, 0) + 1

    checkpoint = None
    cp_path = workspace / "checkpoint.json"
    if cp_path.exists():
        checkpoint = load_checkpoint(cp_path)

    return {
        "roadmap_id": roadmap.roadmap_id,
        "status": roadmap.status.value,
        "total_items": len(roadmap.items),
        "items_by_status": items_by_status,
        "current_item": checkpoint.current_item_id if checkpoint else None,
        "current_phase": checkpoint.phase.value if checkpoint else None,
        "completed_count": len(checkpoint.completed_items) if checkpoint else 0,
        "failed_count": len(checkpoint.failed_items) if checkpoint else 0,
    }

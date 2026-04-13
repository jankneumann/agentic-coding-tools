"""Adaptive item reprioritization based on learning entries.

Reads learning entries for completed items, extracts recommendations
that mention pending items, and adjusts priorities accordingly.
Updates roadmap.yaml with the new priority values.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent / "roadmap-runtime" / "scripts"
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

from learning import read_entry, read_index  # type: ignore[import-untyped]
from models import ItemStatus, Roadmap  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# How much to adjust priority when a recommendation references an item
_PRIORITY_BOOST = -1  # Lower number = higher priority


def replan(roadmap: Roadmap, workspace: Path) -> list[str]:
    """Adjust pending item priorities based on learning recommendations.

    Scans learning entries for completed items.  When a recommendation
    mentions a pending item's ID, that item gets a priority boost
    (its priority value is lowered by 1, making it execute sooner).

    Parameters
    ----------
    roadmap:
        The current roadmap (mutated in place).
    workspace:
        Workspace directory containing learnings/.

    Returns
    -------
    List of human-readable change descriptions, e.g.
    ``["ri-03 priority 3->2 based on ri-01 recommendation"]``.
    """
    changes: list[str] = []

    # Build lookup of pending items
    pending_ids = {
        item.item_id
        for item in roadmap.items
        if item.status in (ItemStatus.APPROVED, ItemStatus.CANDIDATE)
    }

    if not pending_ids:
        return changes

    # Read all learning entries via the index
    completed_ids = read_index(workspace)

    for completed_id in completed_ids:
        entry = read_entry(workspace, completed_id)
        if entry is None:
            continue

        recommendations = entry.get("recommendations", [])
        for rec in recommendations:
            # Find any pending item IDs mentioned in the recommendation
            mentioned = _extract_item_references(rec, pending_ids)
            for item_id in mentioned:
                item = roadmap.get_item(item_id)
                if item is None:
                    continue

                old_priority = item.priority
                new_priority = max(1, old_priority + _PRIORITY_BOOST)

                if new_priority != old_priority:
                    item.priority = new_priority
                    change_desc = (
                        f"{item_id} priority {old_priority}->{new_priority} "
                        f"based on {completed_id} recommendation"
                    )
                    changes.append(change_desc)
                    logger.info("replan.adjust: %s", change_desc)

                    # Add learning ref to the item
                    if completed_id not in item.learning_refs:
                        item.learning_refs.append(completed_id)

    return changes


def _extract_item_references(text: str, valid_ids: set[str]) -> list[str]:
    """Extract item IDs mentioned in a text string.

    Looks for patterns like ``ri-01``, ``ri-02``, etc. and returns
    only those that are in the valid_ids set.
    """
    # Match item ID patterns: ri-01, ri-01-slug-text, etc.
    candidates = set(re.findall(r"\b(ri-\d+(?:-[\w-]+)?)\b", text, re.IGNORECASE))
    return [c for c in candidates if c in valid_ids]

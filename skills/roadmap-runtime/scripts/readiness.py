"""Shared, side-effect-free roadmap execution admission rule."""

from __future__ import annotations

from typing import Any


def _status_value(value: Any) -> str:
    """Return an enum-or-string status as its stable string value."""
    return str(getattr(value, "value", value))


def _get_ready_items(
    roadmap: Any,
    checkpoint: Any,
    external_completed: set[str] | None = None,
) -> list[Any]:
    """Return executable items using checkpoint-authoritative terminal state.

    This preserves the historical autopilot-roadmap contract while providing
    one runtime-owned implementation for repository-wide consumers.
    """
    external_completed = external_completed or set()
    completed_ids = set(checkpoint.completed_items)
    failed_ids = {failed.item_id for failed in checkpoint.failed_items}
    skip_ids = completed_ids | failed_ids

    ready: list[tuple[int, Any]] = []
    for position, item in enumerate(roadmap.items):
        if item.item_id in skip_ids or item.superseded_by:
            continue
        if _status_value(item.status) not in {"approved", "in_progress"}:
            continue
        if all(dep in completed_ids for dep in item.depends_on) and all(
            ref in external_completed for ref in item.external_depends_on
        ):
            ready.append((position, item))

    # Ties inside a priority tier break on roadmap list position, never on
    # item_id: position is the order the operator expressed and the only thing
    # ``refine-roadmap reorder`` can change without rewriting priorities. The
    # key is explicit rather than leaning on sort stability so the rule reads
    # the same here as in dispatch_scheduler and resolve_readiness.
    ready.sort(key=lambda entry: (entry[1].priority, entry[0]))
    return [item for _, item in ready]


__all__ = ["_get_ready_items"]

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

    ready = []
    for item in roadmap.items:
        if item.item_id in skip_ids or item.superseded_by:
            continue
        if _status_value(item.status) not in {"approved", "in_progress"}:
            continue
        if all(dep in completed_ids for dep in item.depends_on) and all(
            ref in external_completed for ref in item.external_depends_on
        ):
            ready.append(item)

    ready.sort(key=lambda item: item.priority)
    return ready


__all__ = ["_get_ready_items"]

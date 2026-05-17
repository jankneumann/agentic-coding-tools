"""Worktrees active projection for the Kanban visualization.

Reads ``.git-worktrees/.registry.json`` and returns a filtered view for
the ``GET /worktrees/active`` endpoint (contract in contracts/README.md).

Filtering rules (contract §"GET /worktrees/active"):
- Stale entries (heartbeat older than ``STALE_THRESHOLD_HOURS``) are omitted.
- Pinned entries are always returned regardless of heartbeat age.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STALE_THRESHOLD_HOURS: float = 1.0
_REGISTRY_REL = Path(".git-worktrees") / ".registry.json"


def _repo_root() -> Path:
    """Default: parents[2] of this file = repo root."""
    return Path(__file__).resolve().parents[2]


def _parse_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        parsed = datetime.fromisoformat(val)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    except (TypeError, ValueError):
        return None


def get_active_worktrees(
    repo_root: Path | None = None,
    stale_hours: float = STALE_THRESHOLD_HOURS,
) -> list[dict[str, Any]]:
    """Return worktree entries that are still considered active.

    Active = pinned=True OR last_heartbeat within ``stale_hours``.
    Returned dict shape (contract):
        {
          "agent_id": str,
          "branch": str,
          "worktree_path": str,
          "last_heartbeat_iso": str,
          "pinned": bool,
          "owner_session": str | None
        }
    """
    root = (repo_root or _repo_root()).resolve()
    registry_path = root / _REGISTRY_REL

    if not registry_path.is_file():
        return []

    try:
        with open(registry_path) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        logger.warning("worktrees_view: failed to read registry at %s", registry_path)
        return []

    entries = data.get("entries", []) if isinstance(data, dict) else []
    threshold = timedelta(hours=stale_hours)
    now = datetime.now(UTC)

    active: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        pinned = bool(entry.get("pinned", False))
        hb_str = entry.get("last_heartbeat", "")
        hb = _parse_dt(hb_str)
        if pinned or (hb is not None and now - hb <= threshold):
            active.append({
                "agent_id": entry.get("agent_id") or entry.get("change_id", ""),
                "branch": entry.get("branch", ""),
                "worktree_path": entry.get("worktree_path", ""),
                "last_heartbeat_iso": hb_str,
                "pinned": pinned,
                "owner_session": entry.get("owner_session") or entry.get("session_id"),
            })

    return active

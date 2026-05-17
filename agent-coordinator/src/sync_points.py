"""Sync-point status projection for the Kanban visualization.

The three sync-point skills (cleanup-feature, merge-pull-requests, update-specs)
block on active worktree registrations. This module projects that state into a
JSON-serializable list suitable for the ``GET /sync-points/status`` endpoint.

Design decision D5: reads ``.git-worktrees/.registry.json`` directly rather
than delegating to ``skills.shared.active_agents`` (which lives outside the
agent-coordinator package and is not available in the deployed Docker image).
The registry-reading logic is intentionally minimal — it mirrors the semantics
of ``check_no_active_agents()`` from skills/shared/active_agents.py without
importing it.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# The three sync-point skills, alphabetical (spec: deterministic ordering).
SYNC_POINT_SKILLS: list[str] = [
    "cleanup-feature",
    "merge-pull-requests",
    "update-specs",
]

_REGISTRY_RELATIVE = Path(".git-worktrees") / ".registry.json"
_STALE_THRESHOLD = timedelta(hours=1)


def _parse_iso(ts: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _load_registry(repo_root: Path) -> list[dict[str, Any]]:
    registry_path = repo_root / _REGISTRY_RELATIVE
    if not registry_path.is_file():
        return []
    try:
        with open(registry_path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    entries = data.get("entries", [])
    return [e for e in entries if isinstance(e, dict)]


def _check_active_worktrees(
    repo_root: Path,
) -> tuple[bool, list[dict[str, Any]]]:
    """Return ``(clear, active_list)`` by reading the worktree registry.

    Mirrors ``skills.shared.active_agents.check_no_active_agents`` semantics:
    an entry is active if pinned=True OR its last_heartbeat is within 1 hour.
    Fail-open: corrupted/missing registry → clear=True.
    """
    now = datetime.now(UTC)
    active: list[dict[str, Any]] = []
    for entry in _load_registry(repo_root):
        if entry.get("pinned"):
            active.append(entry)
            continue
        hb = _parse_iso(str(entry.get("last_heartbeat", "")))
        if hb is not None and now - hb <= _STALE_THRESHOLD:
            active.append(entry)
    return (not active, active)


def get_sync_points_status(repo_root: Path | None = None) -> list[dict[str, Any]]:
    """Return a sorted list of sync-point status dicts.

    Each element follows the contract in contracts/README.md:
        {
          "skill": str,
          "blocked": bool,
          "blockers": [{"agent_id": str, "last_heartbeat_iso": str}],
          "suggested_actions": ["wait", "kick:<agent_id>", ...]
        }

    The ``blockers`` list comes from reading ``.git-worktrees/.registry.json``.
    When the check returns ``clear=True``, ``blocked=False`` and the other
    arrays are empty.
    """
    # Resolve root: explicit arg > default (repo root relative to this file)
    # This file is at agent-coordinator/src/sync_points.py; parents[2] = repo root.
    root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    try:
        clear, active_list = _check_active_worktrees(root)
    except Exception as exc:
        logger.error("get_sync_points_status: registry read failed: %s", exc)
        clear = True
        active_list = []

    blockers = [
        {
            "agent_id": str(a.get("agent_id") or a.get("change_id") or ""),
            "last_heartbeat_iso": str(a.get("last_heartbeat", "")),
        }
        for a in active_list
    ]

    suggested_actions: list[str] = []
    if not clear:
        suggested_actions.append("wait")
        for b in blockers:
            aid = b["agent_id"]
            if aid:
                suggested_actions.append(f"kick:{aid}")

    status_row: dict[str, Any] = {
        "blocked": not clear,
        "blockers": blockers,
        "suggested_actions": suggested_actions,
    }

    return [
        {"skill": skill, **status_row}
        for skill in sorted(SYNC_POINT_SKILLS)
    ]

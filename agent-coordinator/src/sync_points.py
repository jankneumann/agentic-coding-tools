"""Sync-point status projection for the Kanban visualization.

The three sync-point skills (cleanup-feature, merge-pull-requests, update-specs)
block on active worktree registrations. This module projects that state into a
JSON-serializable list suitable for the ``GET /sync-points/status`` endpoint.

Design decision D5: reuses ``skills.shared.active_agents.check_no_active_agents``
rather than duplicating the logic.  The import is resolved at call-time via
sys.path manipulation pointing to the repo root — no vendoring.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# The three sync-point skills, alphabetical (spec: deterministic ordering).
SYNC_POINT_SKILLS: list[str] = [
    "cleanup-feature",
    "merge-pull-requests",
    "update-specs",
]


def _load_active_agents_module() -> Any:
    """Import skills.shared.active_agents, adding the repo root to sys.path."""
    # config.py lives at agent-coordinator/src/config.py.
    # parents[2] = repo root containing skills/shared/active_agents.py
    repo_root = Path(__file__).resolve().parents[2]
    skills_shared = repo_root / "skills" / "shared"
    if str(skills_shared) not in sys.path:
        sys.path.insert(0, str(skills_shared))
    import active_agents as _mod
    return _mod


def get_sync_points_status(repo_root: Path | None = None) -> list[dict[str, Any]]:
    """Return a sorted list of sync-point status dicts.

    Each element follows the contract in contracts/README.md:
        {
          "skill": str,
          "blocked": bool,
          "blockers": [{"agent_id": str, "last_heartbeat_iso": str}],
          "suggested_actions": ["wait", "kick:<agent_id>", ...]
        }

    The ``blockers`` list comes from
    ``check_no_active_agents(repo_root=<root>)``.  When the check returns
    ``clear=True``, ``blocked=False`` and the other arrays are empty.
    """
    try:
        mod = _load_active_agents_module()
        clear, active_list = mod.check_no_active_agents(repo_root=repo_root)
    except Exception as exc:
        logger.error("get_sync_points_status: active_agents import/call failed: %s", exc)
        clear = True
        active_list = []

    blockers = [
        {
            "agent_id": a.agent_id or a.change_id,
            "last_heartbeat_iso": a.last_heartbeat,
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

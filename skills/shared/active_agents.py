"""Active-agent guard for sync-point skills.

CLAUDE.md asserts that sync-point skills (/cleanup-feature, /merge-pull-requests,
/update-specs) must verify no other agents hold active worktrees before touching
main. This module is the implementation of that contract.

Reads .git-worktrees/.registry.json (managed by skills/worktree/scripts/worktree.py).
An entry is "active" when its last_heartbeat is within ``stale_threshold``
(default 1h) or it is ``pinned: true``. Stale-and-unpinned entries do not block
sync-point skills — they are assumed to be crashed agents that GC will clean up.

Library use::

    from shared.active_agents import check_no_active_agents
    clear, active = check_no_active_agents()
    if not clear:
        raise RuntimeError(f"{len(active)} active agents block sync-point operation")

CLI use (for skills shelling out from markdown instructions)::

    python skills/shared/active_agents.py             # exit 0 if clear, 1 if blocked
    python skills/shared/active_agents.py --force     # bypass; logs override; exit 0
    python skills/shared/active_agents.py --json      # machine-readable output

Sync-point skills (/cleanup-feature, /merge-pull-requests, /update-specs) should
invoke this as their first action and abort if it returns non-zero unless the
operator explicitly passes --force.

Fail-open philosophy: if the registry is missing or corrupt, this module returns
``clear=True``. The alternative (wedging every sync-point skill on a corrupt JSON
file) is worse than the risk of a missed guard. Operators investigate corruption
out-of-band; the registry write path in worktree.py is atomic via tmp+replace.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_STALE_THRESHOLD = timedelta(hours=1)
REGISTRY_RELATIVE_PATH = Path(".git-worktrees") / ".registry.json"


@dataclass(frozen=True)
class ActiveAgent:
    change_id: str
    agent_id: str | None
    branch: str
    worktree_path: str
    last_heartbeat: str
    pinned: bool

    @property
    def label(self) -> str:
        ident = f"{self.change_id}/{self.agent_id}" if self.agent_id else self.change_id
        suffix = " (pinned)" if self.pinned else ""
        return f"{ident} on {self.branch}{suffix}"


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _registry_path(repo_root: Path) -> Path:
    return repo_root / REGISTRY_RELATIVE_PATH


def _load_registry(path: Path) -> dict:
    if not path.is_file():
        return {"version": 1, "entries": []}
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "entries": []}
    if not isinstance(data, dict) or "entries" not in data:
        return {"version": 1, "entries": []}
    return data


def _is_active(
    entry: dict,
    *,
    now: datetime,
    stale_threshold: timedelta,
) -> bool:
    if entry.get("pinned"):
        return True
    hb = _parse_iso(entry.get("last_heartbeat", ""))
    if hb is None:
        return False
    return now - hb <= stale_threshold


def check_no_active_agents(
    *,
    repo_root: Path | None = None,
    stale_threshold: timedelta = DEFAULT_STALE_THRESHOLD,
    now: datetime | None = None,
) -> tuple[bool, list[ActiveAgent]]:
    """Return ``(clear, active_list)``.

    ``clear=True`` means it is safe for a sync-point skill to proceed.
    ``active_list`` is informational; it is empty iff ``clear=True``.

    An entry is active if it is pinned OR its ``last_heartbeat`` is within
    ``stale_threshold`` of ``now``. Stale-and-unpinned entries are ignored.
    """
    root = (repo_root or Path.cwd()).resolve()
    registry = _load_registry(_registry_path(root))
    when = now or datetime.now(timezone.utc)
    active: list[ActiveAgent] = []
    for entry in registry.get("entries", []):
        if not isinstance(entry, dict):
            continue
        if _is_active(entry, now=when, stale_threshold=stale_threshold):
            active.append(ActiveAgent(
                change_id=str(entry.get("change_id", "")),
                agent_id=entry.get("agent_id"),
                branch=str(entry.get("branch", "")),
                worktree_path=str(entry.get("worktree_path", "")),
                last_heartbeat=str(entry.get("last_heartbeat", "")),
                pinned=bool(entry.get("pinned", False)),
            ))
    return (not active, active)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Verify no active agents hold worktrees before a sync-point operation"
    )
    p.add_argument("--force", action="store_true",
                   help="bypass the guard; logs override to stderr but still exits 0")
    p.add_argument("--json", action="store_true",
                   help="emit machine-readable output to stdout")
    p.add_argument("--stale-hours", type=float, default=1.0,
                   help="active-threshold in hours (default 1)")
    p.add_argument("--repo-root", type=Path, default=None,
                   help="repository root containing .git-worktrees/ (default: cwd)")
    args = p.parse_args(argv)

    clear, active = check_no_active_agents(
        repo_root=args.repo_root,
        stale_threshold=timedelta(hours=args.stale_hours),
    )

    if args.json:
        json.dump({
            "clear": clear,
            "force": args.force,
            "active": [
                {
                    "change_id": a.change_id,
                    "agent_id": a.agent_id,
                    "branch": a.branch,
                    "worktree_path": a.worktree_path,
                    "last_heartbeat": a.last_heartbeat,
                    "pinned": a.pinned,
                }
                for a in active
            ],
        }, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        if clear:
            print("clear: no active agents")
        else:
            print(f"BLOCKED: {len(active)} active agent(s) hold worktrees:")
            for a in active:
                print(f"  - {a.label} (heartbeat {a.last_heartbeat})")

    if not clear and args.force:
        print("--force: bypassing active-agent guard", file=sys.stderr)
        return 0
    return 0 if clear else 1


if __name__ == "__main__":
    raise SystemExit(main())

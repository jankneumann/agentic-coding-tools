"""Conservative local activity and provisioning guard for sync points."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from shared import worktree_lifecycle as lifecycle
except ModuleNotFoundError:  # direct execution from skills/shared/
    import worktree_lifecycle as lifecycle  # type: ignore[no-redef]


DEFAULT_STALE_THRESHOLD = timedelta(hours=1)


@dataclass(frozen=True)
class ActiveAgent:
    change_id: str
    agent_id: str | None
    branch: str
    worktree_path: str
    last_heartbeat: str
    pinned: bool = False
    owner: str | None = None
    phase: str | None = None
    expires_at: str | None = None
    source: str = "activity-lease"

    @property
    def label(self) -> str:
        ident = f"{self.change_id}/{self.agent_id}" if self.agent_id else self.change_id
        owner = f" ({self.owner})" if self.owner else ""
        retained = " (retained)" if self.pinned and not owner else ""
        return f"{ident} on {self.branch}{owner}{retained}"


@dataclass(frozen=True)
class GuardBlocker:
    kind: str
    reason: str
    change_id: str | None = None
    agent_id: str | None = None
    setup_id: str | None = None
    entry_generation: str | None = None
    state: str | None = None
    created_at: str | None = None
    expires_at: str | None = None
    recovery_required: bool = False


@dataclass(frozen=True)
class GuardInspection:
    clear: bool
    active: tuple[ActiveAgent, ...]
    blockers: tuple[GuardBlocker, ...]
    registry_state: str
    inspected_at: str


def _main_root(root: Path) -> Path:
    """Resolve a linked-worktree path to the repository that owns the registry."""
    candidate = root.resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=str(candidate),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve().parent
    git_file = candidate / ".git"
    if git_file.is_file():
        try:
            text = git_file.read_text().strip()
            if text.startswith("gitdir:"):
                gitdir = Path(text.split(":", 1)[1].strip()).resolve()
                common = gitdir / "commondir"
                if common.is_file():
                    common_dir = (gitdir / common.read_text().strip()).resolve()
                    return common_dir.parent
        except OSError:
            pass
    return candidate


def inspect_guard(
    *,
    repo_root: Path | None = None,
    stale_threshold: timedelta = DEFAULT_STALE_THRESHOLD,
    now: datetime | None = None,
) -> GuardInspection:
    root = _main_root(repo_root or Path.cwd())
    when = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        registry = lifecycle.read_registry(root)
    except lifecycle.RegistryCorrupt as exc:
        blocker = GuardBlocker(kind="registry-corrupt", reason=str(exc), recovery_required=True)
        return GuardInspection(False, (), (blocker,), "corrupt", when.isoformat())
    except lifecycle.LockTimeout as exc:
        blocker = GuardBlocker(
            kind="registry-lock-timeout", reason=str(exc), recovery_required=True
        )
        return GuardInspection(False, (), (blocker,), "indeterminate", when.isoformat())

    active: list[ActiveAgent] = []
    for entry in registry["entries"]:
        lease = entry.get("activity_lease")
        live = lifecycle.lease_is_live(lease, now=when)
        if lease and lease.get("phase") == "LEGACY":
            heartbeat = lifecycle.parse_timestamp(lease.get("last_heartbeat"))
            live = heartbeat is not None and when - heartbeat <= stale_threshold
        if not live:
            continue
        # A normalized v1 heartbeat is a synthetic manual LEGACY lease; its
        # fixed one-hour expiry supplies the transitional freshness rule.
        active.append(
            ActiveAgent(
                change_id=entry["change_id"],
                agent_id=entry.get("agent_id"),
                branch=entry["branch"],
                worktree_path=entry["worktree_path"],
                last_heartbeat=lease["last_heartbeat"],
                pinned=bool(entry.get("retained")),
                owner=lease["owner"],
                phase=lease["phase"],
                expires_at=lease["expires_at"],
                source="legacy-heartbeat" if lease["phase"] == "LEGACY" else "activity-lease",
            )
        )

    blockers: list[GuardBlocker] = []
    for reservation in registry["setup_reservations"]:
        expiry = lifecycle.parse_timestamp(reservation["expires_at"])
        expired = expiry is None or expiry < when
        blockers.append(
            GuardBlocker(
                kind="setup-reservation-expired" if expired else "setup-reservation",
                reason=(
                    "expired setup reservation requires explicit reconciliation"
                    if expired
                    else "setup provisioning is unfinished"
                ),
                change_id=reservation["change_id"],
                agent_id=reservation.get("agent_id"),
                setup_id=reservation["setup_id"],
                entry_generation=reservation["entry_generation"],
                state=reservation["state"],
                created_at=reservation["created_at"],
                expires_at=reservation["expires_at"],
                recovery_required=expired,
            )
        )
    return GuardInspection(
        clear=not active and not blockers,
        active=tuple(active),
        blockers=tuple(blockers),
        registry_state="valid",
        inspected_at=when.isoformat(),
    )


def check_no_active_agents(
    *,
    repo_root: Path | None = None,
    stale_threshold: timedelta = DEFAULT_STALE_THRESHOLD,
    now: datetime | None = None,
) -> tuple[bool, list[ActiveAgent]]:
    """Compatibility tuple: activity is separate from conservative blockers."""
    inspection = inspect_guard(
        repo_root=repo_root,
        stale_threshold=stale_threshold,
        now=now,
    )
    return inspection.clear, list(inspection.active)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify no activity or unfinished provisioning blocks a sync point"
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--stale-hours", type=float, default=1.0)
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)
    inspection = inspect_guard(
        repo_root=args.repo_root,
        stale_threshold=timedelta(hours=args.stale_hours),
    )
    if args.json:
        print(
            json.dumps(
                {
                    "clear": inspection.clear,
                    "force": args.force,
                    "registry_state": inspection.registry_state,
                    "inspected_at": inspection.inspected_at,
                    "active": [asdict(item) for item in inspection.active],
                    "blockers": [asdict(item) for item in inspection.blockers],
                },
                indent=2,
                sort_keys=True,
            )
        )
    elif inspection.clear:
        print("clear: no active agents or unfinished setup reservations")
    else:
        if inspection.active:
            print(f"BLOCKED: {len(inspection.active)} active agent(s):")
            for item in inspection.active:
                print(f"  - {item.label} (heartbeat {item.last_heartbeat})")
        if inspection.blockers:
            print(f"BLOCKED: {len(inspection.blockers)} indeterminate lifecycle blocker(s):")
            for item in inspection.blockers:
                identity = item.setup_id or item.change_id or item.kind
                print(f"  - {identity}: {item.reason}")
    if not inspection.clear and args.force:
        print("--force: bypassing lifecycle guard", file=sys.stderr)
        return 0
    return 0 if inspection.clear else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Git worktree lifecycle helper for OpenSpec skills.

Manages worktree creation, teardown, status, detection, heartbeat,
pin/unpin, list, and garbage collection. Outputs machine-parseable
KEY=VALUE lines for shell eval.

Usage:
    python3 scripts/worktree.py setup <change-id> [--agent-id <id>] [--branch <name>] [--prefix <prefix>] [--no-bootstrap]
    python3 scripts/worktree.py teardown <change-id> [--agent-id <id>] [--prefix <prefix>]
    python3 scripts/worktree.py status [<change-id>] [--agent-id <id>]
    python3 scripts/worktree.py detect
    python3 scripts/worktree.py heartbeat <change-id> [--agent-id <id>]
    python3 scripts/worktree.py list
    python3 scripts/worktree.py pin <change-id> [--agent-id <id>]
    python3 scripts/worktree.py unpin <change-id> [--agent-id <id>]
    python3 scripts/worktree.py gc [--stale-after <duration>] [--force]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def run_git(*args: str, cwd: str | None = None, check: bool = True) -> str:
    """Run a git command and return stripped stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        # Include git's stderr in the exception so the caller sees the real error
        msg = f"git {' '.join(args)} failed (exit {result.returncode})"
        if result.stderr.strip():
            msg += f": {result.stderr.strip()}"
        raise subprocess.CalledProcessError(
            result.returncode, result.args, result.stdout, result.stderr,
        )
    return result.stdout.strip()


def resolve_main_repo(cwd: str | None = None) -> Path:
    """Resolve the main repository path, even from inside a worktree."""
    git_common = run_git("rev-parse", "--git-common-dir", cwd=cwd)
    if git_common == ".git":
        return Path(run_git("rev-parse", "--show-toplevel", cwd=cwd))
    # In a worktree: git-common-dir returns /path/to/main/.git
    main_git = git_common.split("/.git")[0]
    return Path(main_git)


# ---------------------------------------------------------------------------
# Path computation
# ---------------------------------------------------------------------------

def worktree_path(
    main_repo: Path,
    change_id: str,
    agent_id: str | None = None,
    prefix: str | None = None,
) -> Path:
    """Compute the worktree path under .git-worktrees/.

    Patterns:
      .git-worktrees/<change-id>/                        (no agent, no prefix)
      .git-worktrees/<change-id>/<agent-id>/             (agent, no prefix)
      .git-worktrees/<prefix>/<change-id>/               (no agent, prefix)
      .git-worktrees/<prefix>/<change-id>/<agent-id>/    (agent + prefix)
    """
    base = main_repo / ".git-worktrees"
    if prefix:
        base = base / prefix
    base = base / change_id
    if agent_id:
        base = base / agent_id
    return base


def default_branch(
    change_id: str,
    agent_id: str | None = None,
    prefix: str | None = None,
) -> str:
    """Compute the default branch name.

    Uses '--' separator between change-id and agent-id to avoid a git
    ref storage limitation: git cannot have both ``refs/heads/a/b`` (a
    branch) and ``refs/heads/a/b/c`` (a sub-path) simultaneously.
    Using '/' would make the feature branch ``openspec/<change-id>``
    conflict with agent branches ``openspec/<change-id>/<agent-id>``.

    Patterns:
      openspec/<change-id>                   (no agent, no prefix)
      openspec/<change-id>--<agent-id>       (agent, no prefix)
      <prefix>/<change-id>                   (no agent, prefix)
      <prefix>/<change-id>--<agent-id>       (agent, prefix)
    """
    if prefix:
        base = f"{prefix}/{change_id}"
    else:
        base = f"openspec/{change_id}"
    if agent_id:
        return f"{base}--{agent_id}"
    return base


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTRY_FILENAME = ".registry.json"


def _registry_path(main_repo: Path) -> Path:
    return main_repo / ".git-worktrees" / REGISTRY_FILENAME


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_registry(main_repo: Path) -> dict[str, Any]:
    """Load the registry file, returning an empty registry if missing."""
    path = _registry_path(main_repo)
    if not path.is_file():
        return {"version": 1, "entries": []}
    with open(path) as f:
        return json.load(f)  # type: ignore[no-any-return]


def save_registry(main_repo: Path, registry: dict[str, Any]) -> None:
    """Write the registry file atomically (best-effort)."""
    path = _registry_path(main_repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(registry, f, indent=2)
        f.write("\n")
    tmp.replace(path)


def find_entry(
    registry: dict[str, Any],
    change_id: str,
    agent_id: str | None = None,
) -> dict[str, Any] | None:
    """Find a registry entry by (change_id, agent_id)."""
    for entry in registry["entries"]:
        if entry["change_id"] == change_id and entry.get("agent_id") == agent_id:
            return entry  # type: ignore[no-any-return]
    return None


def remove_entry(
    registry: dict[str, Any],
    change_id: str,
    agent_id: str | None = None,
) -> bool:
    """Remove a registry entry. Returns True if found and removed."""
    before = len(registry["entries"])
    registry["entries"] = [
        e for e in registry["entries"]
        if not (e["change_id"] == change_id and e.get("agent_id") == agent_id)
    ]
    return len(registry["entries"]) < before


# ---------------------------------------------------------------------------
# Duration parsing
# ---------------------------------------------------------------------------

def parse_duration_hours(duration: str) -> float:
    """Parse a duration string like '24h', '48h', '7d' into hours."""
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(h|d|m)$", duration.strip().lower())
    if not m:
        raise ValueError(f"Invalid duration format: {duration!r}. Use e.g. 24h, 7d, 30m")
    value = float(m.group(1))
    unit = m.group(2)
    if unit == "h":
        return value
    if unit == "d":
        return value * 24
    if unit == "m":
        return value / 60
    raise ValueError(f"Unknown unit: {unit}")  # pragma: no cover


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_setup(args: argparse.Namespace) -> int:
    """Create a worktree for the given change-id."""
    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    change_id: str = args.change_id
    agent_id: str | None = getattr(args, "agent_id", None)
    prefix: str | None = args.prefix
    branch = args.branch or default_branch(change_id, agent_id, prefix)

    wt_path = worktree_path(main_repo, change_id, agent_id, prefix)

    # Check if already in the target worktree
    try:
        current_toplevel = Path(
            run_git("rev-parse", "--show-toplevel", cwd=cwd)
        )
        if current_toplevel == wt_path:
            print(f"WORKTREE_PATH={wt_path}")
            print("ALREADY_EXISTS=true", file=sys.stderr)
            return 0
    except subprocess.CalledProcessError:
        pass

    # Create parent directory
    wt_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure we have latest main
    run_git("fetch", "origin", "main", cwd=str(main_repo), check=False)

    # Create branch if it doesn't exist
    try:
        run_git(
            "show-ref", "--verify", "--quiet", f"refs/heads/{branch}",
            cwd=str(main_repo),
        )
    except subprocess.CalledProcessError:
        run_git("branch", branch, "main", cwd=str(main_repo))
        print(f"BRANCH_CREATED={branch}", file=sys.stderr)

    # Prune stale worktree entries (e.g., directory was deleted but git still tracks it)
    run_git("worktree", "prune", cwd=str(main_repo), check=False)

    # Create worktree (or reuse)
    already_exists = False
    if wt_path.is_dir():
        already_exists = True
        print("ALREADY_EXISTS=true", file=sys.stderr)
    else:
        try:
            run_git("worktree", "add", str(wt_path), branch, cwd=str(main_repo))
        except subprocess.CalledProcessError as exc:
            # Surface git's actual error message for diagnosis
            stderr = exc.stderr.strip() if exc.stderr else ""
            print(f"ERROR: git worktree add failed: {stderr}", file=sys.stderr)
            raise
        print("CREATED=true", file=sys.stderr)

    # Update registry
    registry = load_registry(main_repo)
    existing = find_entry(registry, change_id, agent_id)
    now = _utcnow_iso()
    if existing:
        existing["last_heartbeat"] = now
    else:
        registry["entries"].append({
            "change_id": change_id,
            "agent_id": agent_id,
            "branch": branch,
            "worktree_path": str(wt_path),
            "created_at": now,
            "last_heartbeat": now,
            "pinned": False,
        })
    save_registry(main_repo, registry)

    # Bootstrap the worktree (copy .env, install deps, sync skills)
    bootstrapped = False
    if not args.no_bootstrap and not already_exists:
        bootstrap_script = main_repo / "skills" / "worktree" / "scripts" / "worktree-bootstrap.sh"
        if bootstrap_script.is_file():
            print("Bootstrapping worktree...", file=sys.stderr)
            env = os.environ.copy()
            if agent_id:
                env["AGENT_ID"] = agent_id
            result = subprocess.run(
                ["bash", str(bootstrap_script), str(wt_path), str(main_repo)],
                capture_output=False,
                check=False,
                env=env,
            )
            bootstrapped = result.returncode == 0
        else:
            print("No bootstrap script found, skipping", file=sys.stderr)

    print(f"WORKTREE_PATH={wt_path}")
    print(f"BOOTSTRAPPED={'true' if bootstrapped else 'false'}")
    return 0


def cmd_teardown(args: argparse.Namespace) -> int:
    """Remove a worktree for the given change-id."""
    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    change_id: str = args.change_id
    agent_id: str | None = getattr(args, "agent_id", None)
    prefix: str | None = args.prefix

    wt_path = worktree_path(main_repo, change_id, agent_id, prefix)

    if not wt_path.is_dir():
        print(f"No worktree found for {change_id}"
              + (f" (agent: {agent_id})" if agent_id else ""),
              file=sys.stderr)
        print("REMOVED=false")
        return 1

    # Must run from main repo to remove worktree
    run_git("worktree", "remove", str(wt_path), cwd=str(main_repo))

    # Update registry
    registry = load_registry(main_repo)
    remove_entry(registry, change_id, agent_id)
    save_registry(main_repo, registry)

    print("REMOVED=true")
    print(f"REMOVED_PATH={wt_path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """List active worktrees or check a specific one."""
    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    change_id: str | None = args.change_id
    agent_id: str | None = getattr(args, "agent_id", None)

    if change_id:
        if agent_id:
            # Check specific agent worktree
            wt_path = worktree_path(main_repo, change_id, agent_id)
            if wt_path.is_dir():
                print("EXISTS=true")
                print(f"WORKTREE_PATH={wt_path}")
            else:
                print("EXISTS=false")
                return 1
        else:
            # Check change-level (single agent or list agents)
            wt_path = worktree_path(main_repo, change_id)
            if wt_path.is_dir():
                print("EXISTS=true")
                print(f"WORKTREE_PATH={wt_path}")
            else:
                # Check if any agent worktrees exist under this change
                change_dir = main_repo / ".git-worktrees" / change_id
                if change_dir.is_dir():
                    agents = [d.name for d in change_dir.iterdir() if d.is_dir()]
                    if agents:
                        print("EXISTS=true")
                        print(f"WORKTREE_PATH={change_dir}")
                        print(f"AGENTS={','.join(agents)}")
                    else:
                        print("EXISTS=false")
                        return 1
                else:
                    print("EXISTS=false")
                    return 1
    else:
        output = run_git("worktree", "list", cwd=str(main_repo))
        print(output)
    return 0


def cmd_detect(_args: argparse.Namespace) -> int:
    """Detect if running in a worktree and output context variables."""
    cwd = os.getcwd()
    try:
        git_common = run_git("rev-parse", "--git-common-dir", cwd=cwd)
    except subprocess.CalledProcessError:
        print("IN_WORKTREE=false")
        print(f"MAIN_REPO={cwd}")
        print("OPENSPEC_PATH=openspec")
        return 0

    if git_common == ".git":
        main_repo = run_git("rev-parse", "--show-toplevel", cwd=cwd)
        print("IN_WORKTREE=false")
        print(f"MAIN_REPO={main_repo}")
        print("OPENSPEC_PATH=openspec")
    else:
        main_git = git_common.split("/.git")[0]
        print("IN_WORKTREE=true")
        print(f"MAIN_REPO={main_git}")
        print(f"OPENSPEC_PATH={main_git}/openspec")

    return 0


def cmd_heartbeat(args: argparse.Namespace) -> int:
    """Update the last_heartbeat timestamp for a registered worktree."""
    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    change_id: str = args.change_id
    agent_id: str | None = getattr(args, "agent_id", None)

    registry = load_registry(main_repo)
    entry = find_entry(registry, change_id, agent_id)
    if entry is None:
        print(f"No registry entry for {change_id}"
              + (f" (agent: {agent_id})" if agent_id else ""),
              file=sys.stderr)
        return 1

    entry["last_heartbeat"] = _utcnow_iso()
    save_registry(main_repo, registry)
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    """List all registered worktrees with staleness and pin indicators."""
    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    registry = load_registry(main_repo)

    if not registry["entries"]:
        print("No active worktrees registered.")
        return 0

    now = datetime.now(timezone.utc)
    stale_threshold_hours = 1.0

    # Header
    print(f"{'CHANGE_ID':<30} {'AGENT_ID':<15} {'BRANCH':<40} {'STATUS':<20} {'PATH'}")
    print("-" * 130)

    for entry in registry["entries"]:
        hb = datetime.fromisoformat(entry["last_heartbeat"])
        age_hours = (now - hb).total_seconds() / 3600
        status_parts = []
        if entry.get("pinned"):
            status_parts.append("[pinned]")
        if age_hours > stale_threshold_hours:
            status_parts.append(f"[stale {age_hours:.1f}h]")
        else:
            status_parts.append("[active]")
        status = " ".join(status_parts)

        print(
            f"{entry['change_id']:<30} "
            f"{(entry.get('agent_id') or '-'):<15} "
            f"{entry['branch']:<40} "
            f"{status:<20} "
            f"{entry['worktree_path']}"
        )

    return 0


def cmd_pin(args: argparse.Namespace) -> int:
    """Mark a worktree as protected from garbage collection."""
    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    change_id: str = args.change_id
    agent_id: str | None = getattr(args, "agent_id", None)

    registry = load_registry(main_repo)
    entry = find_entry(registry, change_id, agent_id)
    if entry is None:
        print(f"No registry entry for {change_id}"
              + (f" (agent: {agent_id})" if agent_id else ""),
              file=sys.stderr)
        return 1

    entry["pinned"] = True
    save_registry(main_repo, registry)
    print(f"Pinned: {change_id}" + (f"/{agent_id}" if agent_id else ""),
          file=sys.stderr)
    return 0


def cmd_unpin(args: argparse.Namespace) -> int:
    """Remove garbage collection protection from a worktree."""
    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    change_id: str = args.change_id
    agent_id: str | None = getattr(args, "agent_id", None)

    registry = load_registry(main_repo)
    entry = find_entry(registry, change_id, agent_id)
    if entry is None:
        print(f"No registry entry for {change_id}"
              + (f" (agent: {agent_id})" if agent_id else ""),
              file=sys.stderr)
        return 1

    entry["pinned"] = False
    save_registry(main_repo, registry)
    print(f"Unpinned: {change_id}" + (f"/{agent_id}" if agent_id else ""),
          file=sys.stderr)
    return 0


def cmd_gc(args: argparse.Namespace) -> int:
    """Remove stale worktrees based on heartbeat age and pin status."""
    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    force: bool = args.force
    stale_hours = parse_duration_hours(args.stale_after)

    registry = load_registry(main_repo)
    now = datetime.now(timezone.utc)
    removed: list[str] = []
    kept: list[dict[str, Any]] = []

    for entry in registry["entries"]:
        hb = datetime.fromisoformat(entry["last_heartbeat"])
        age_hours = (now - hb).total_seconds() / 3600
        wt = Path(entry["worktree_path"])

        # Orphaned registry entry (directory gone) — always remove
        if not wt.is_dir():
            print(f"Removing orphaned entry: {entry['change_id']}"
                  + (f"/{entry.get('agent_id', '')}" if entry.get("agent_id") else ""),
                  file=sys.stderr)
            removed.append(str(wt))
            continue

        # Not stale — keep
        if age_hours <= stale_hours:
            kept.append(entry)
            continue

        # Pinned and not forced — keep
        if entry.get("pinned") and not force:
            print(f"Skipping pinned: {entry['change_id']}"
                  + (f"/{entry.get('agent_id', '')}" if entry.get("agent_id") else ""),
                  file=sys.stderr)
            kept.append(entry)
            continue

        # Stale (and unpinned, or forced) — remove
        label = entry["change_id"] + (f"/{entry.get('agent_id', '')}" if entry.get("agent_id") else "")
        print(f"Removing stale worktree: {label} (age: {age_hours:.1f}h)",
              file=sys.stderr)
        try:
            run_git("worktree", "remove", str(wt), cwd=str(main_repo))
        except subprocess.CalledProcessError:
            # Force remove if normal remove fails
            try:
                run_git("worktree", "remove", "--force", str(wt), cwd=str(main_repo))
            except subprocess.CalledProcessError as e:
                print(f"Failed to remove {wt}: {e}", file=sys.stderr)
                kept.append(entry)
                continue

        removed.append(str(wt))

        # Prune branch if fully merged
        branch = entry["branch"]
        try:
            run_git(
                "branch", "-d", branch,
                cwd=str(main_repo),
                check=True,
            )
            print(f"Pruned merged branch: {branch}", file=sys.stderr)
        except subprocess.CalledProcessError:
            pass  # Branch not fully merged or doesn't exist — leave it

    registry["entries"] = kept
    save_registry(main_repo, registry)

    print(f"REMOVED_COUNT={len(removed)}")
    if removed:
        print(f"REMOVED_PATHS={','.join(removed)}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _add_agent_id_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--agent-id", dest="agent_id", default=None,
                        help="Agent identifier for parallel disambiguation")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Git worktree lifecycle helper for OpenSpec skills"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # setup
    setup_parser = subparsers.add_parser("setup", help="Create a worktree")
    setup_parser.add_argument("change_id", help="Change ID or identifier")
    _add_agent_id_flag(setup_parser)
    setup_parser.add_argument("--branch", help="Branch name (default: openspec/<change-id>)")
    setup_parser.add_argument("--prefix", help="Path prefix (e.g., fix-scrub)")
    setup_parser.add_argument(
        "--no-bootstrap", action="store_true",
        help="Skip environment bootstrap (deps, .env copy, skills sync)",
    )
    setup_parser.set_defaults(func=cmd_setup)

    # teardown
    teardown_parser = subparsers.add_parser("teardown", help="Remove a worktree")
    teardown_parser.add_argument("change_id", help="Change ID or identifier")
    _add_agent_id_flag(teardown_parser)
    teardown_parser.add_argument("--prefix", help="Path prefix (e.g., fix-scrub)")
    teardown_parser.set_defaults(func=cmd_teardown)

    # status
    status_parser = subparsers.add_parser("status", help="Check worktree status")
    status_parser.add_argument("change_id", nargs="?", help="Change ID to check")
    _add_agent_id_flag(status_parser)
    status_parser.set_defaults(func=cmd_status)

    # detect
    detect_parser = subparsers.add_parser("detect", help="Detect worktree context")
    detect_parser.set_defaults(func=cmd_detect)

    # heartbeat
    hb_parser = subparsers.add_parser("heartbeat", help="Update heartbeat timestamp")
    hb_parser.add_argument("change_id", help="Change ID")
    _add_agent_id_flag(hb_parser)
    hb_parser.set_defaults(func=cmd_heartbeat)

    # list
    list_parser = subparsers.add_parser("list", help="List registered worktrees")
    list_parser.set_defaults(func=cmd_list)

    # pin
    pin_parser = subparsers.add_parser("pin", help="Pin worktree (protect from GC)")
    pin_parser.add_argument("change_id", help="Change ID")
    _add_agent_id_flag(pin_parser)
    pin_parser.set_defaults(func=cmd_pin)

    # unpin
    unpin_parser = subparsers.add_parser("unpin", help="Unpin worktree")
    unpin_parser.add_argument("change_id", help="Change ID")
    _add_agent_id_flag(unpin_parser)
    unpin_parser.set_defaults(func=cmd_unpin)

    # gc
    gc_parser = subparsers.add_parser("gc", help="Remove stale worktrees")
    gc_parser.add_argument("--stale-after", default="24h",
                           help="Duration threshold (e.g., 24h, 48h, 7d)")
    gc_parser.add_argument("--force", action="store_true",
                           help="Remove pinned worktrees too")
    gc_parser.set_defaults(func=cmd_gc)

    parsed = parser.parse_args()
    return parsed.func(parsed)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        cmd_str = " ".join(str(a) for a in exc.cmd) if isinstance(exc.cmd, list) else str(exc.cmd)
        print(f"Error: {cmd_str} failed (exit {exc.returncode})", file=sys.stderr)
        if stderr:
            print(f"  {stderr}", file=sys.stderr)
        sys.exit(exc.returncode)

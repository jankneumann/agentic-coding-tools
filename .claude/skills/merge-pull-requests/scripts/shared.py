"""Shared utilities for merge-pull-requests scripts.

Provides common functions for gh CLI interaction, argument parsing,
and author extraction used across discover, staleness, comment, and merge scripts.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

GH_TIMEOUT = 30
GIT_TIMEOUT = 60
ACTIVE_AGENT_STALE_HOURS = 1.0


def _truncate_cmd(parts: list[str], max_len: int = 200) -> str:
    """Format a command for error messages, truncating if too long."""
    full = " ".join(parts)
    if len(full) <= max_len:
        return full
    return full[:max_len] + "…"


def check_gh():
    """Verify gh CLI is installed and authenticated."""
    try:
        subprocess.run(
            ["gh", "--version"], capture_output=True, text=True,
            check=True, timeout=GH_TIMEOUT,
        )
    except FileNotFoundError:
        print("Error: 'gh' CLI is not installed or not on PATH.", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("Error: 'gh --version' timed out.", file=sys.stderr)
        sys.exit(1)

    result = subprocess.run(
        ["gh", "auth", "status"], capture_output=True, text=True,
        check=False, timeout=GH_TIMEOUT,
    )
    if result.returncode != 0:
        print(
            "Error: gh is not authenticated. Run 'gh auth login' first.",
            file=sys.stderr,
        )
        sys.exit(1)


def run_gh(args: list[str], timeout: int = GH_TIMEOUT) -> str:
    """Run a gh command and return stdout, raising RuntimeError on failure."""
    result = subprocess.run(
        ["gh"] + args, capture_output=True, text=True,
        check=False, timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{_truncate_cmd(['gh'] + args)} failed (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )
    return result.stdout.strip()


def run_gh_unchecked(
    args: list[str], timeout: int = GH_TIMEOUT,
) -> subprocess.CompletedProcess:
    """Run a gh command and return the CompletedProcess without raising."""
    return subprocess.run(
        ["gh"] + args, capture_output=True, text=True,
        check=False, timeout=timeout,
    )


def run_cmd(
    cmd: list[str], check: bool = True, timeout: int = GIT_TIMEOUT,
) -> str:
    """Run an arbitrary command and return stdout.

    When check=True (default), raises RuntimeError on non-zero exit.
    """
    result = subprocess.run(
        cmd, capture_output=True, text=True, check=False, timeout=timeout,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"{_truncate_cmd(cmd)} failed (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )
    return result.stdout.strip()


def parse_pr_number(arg: str) -> int:
    """Parse and validate PR number from argument."""
    try:
        num = int(arg)
    except ValueError:
        print(f"Error: '{arg}' is not a valid PR number.", file=sys.stderr)
        sys.exit(1)
    if num <= 0:
        print(f"Error: PR number must be positive, got {num}.", file=sys.stderr)
        sys.exit(1)
    return num


def parse_pr_numbers(arg: str) -> list[int]:
    """Parse comma-separated PR numbers."""
    numbers = []
    for part in arg.split(","):
        part = part.strip()
        if not part:
            continue
        numbers.append(parse_pr_number(part))
    if not numbers:
        print("Error: No valid PR numbers provided.", file=sys.stderr)
        sys.exit(1)
    return numbers


def safe_author(obj: dict, key: str = "author") -> str:
    """Extract author login from a dict, handling null/missing author."""
    author = obj.get(key)
    if author is None:
        return "unknown"
    return author.get("login", "unknown") or "unknown"


def check_write_access():
    """Verify the gh token has write (push) access to the repository.

    Non-fatal: if the check itself fails (e.g. no repo context), we skip
    and let the actual merge/close fail with a clearer error later.
    """
    try:
        raw = run_gh(["api", "repos/{owner}/{repo}", "--jq", ".permissions.push"])
    except RuntimeError:
        print(
            "Warning: Could not verify write access — will proceed and "
            "fail at merge/close if access is insufficient.",
            file=sys.stderr,
        )
        return
    if raw.strip() == "false":
        print(
            "Error: Your gh token does not have write (push) access to this "
            "repository. Merge and close operations will fail. Check your "
            "token scopes or request write access.",
            file=sys.stderr,
        )
        sys.exit(1)


def check_clean_worktree() -> bool:
    """Check if the git working directory is clean.

    Non-fatal: prints a warning to stderr if dirty. Returns True if clean.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, check=False, timeout=GIT_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print(
            "Warning: Could not check working directory status.",
            file=sys.stderr,
        )
        return False

    if result.returncode != 0:
        print(
            "Warning: Could not check working directory status.",
            file=sys.stderr,
        )
        return False

    if result.stdout.strip():
        print(
            "Warning: Working directory has uncommitted changes. "
            "Commit, stash, or discard changes before proceeding.",
            file=sys.stderr,
        )
        return False

    return True


# ---------------------------------------------------------------------------
# Active-agent guard for sync-point skills
# ---------------------------------------------------------------------------

def _resolve_main_repo() -> Path | None:
    """Resolve the main repository root, returning None on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, check=False, timeout=GIT_TIMEOUT,
        )
        if result.returncode != 0:
            return None
        git_common = result.stdout.strip()
        if git_common == ".git":
            toplevel = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, check=False, timeout=GIT_TIMEOUT,
            )
            return Path(toplevel.stdout.strip()) if toplevel.returncode == 0 else None
        # Inside a worktree: git-common-dir is /path/to/main/.git
        main_git = git_common.split("/.git")[0]
        return Path(main_git)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _load_worktree_registry(main_repo: Path) -> dict | None:
    """Load .git-worktrees/.registry.json, returning None if absent."""
    registry_path = main_repo / ".git-worktrees" / ".registry.json"
    if not registry_path.is_file():
        return None
    try:
        with open(registry_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def check_no_active_agents(force: bool = False) -> bool:
    """Check the worktree registry for active agents.

    Sync-point skills (merge-pull-requests, update-specs) operate on the
    shared checkout / main branch. They must not run while other agents
    hold active worktrees, as concurrent git operations on main could
    interfere with worktree-based work.

    Returns True if safe to proceed (no active agents or registry
    unavailable). Returns False if active agents are detected.

    When force=True, prints a warning but returns True anyway.
    """
    main_repo = _resolve_main_repo()
    if main_repo is None:
        return True  # Can't resolve repo — skip guard

    registry = _load_worktree_registry(main_repo)
    if registry is None or not registry.get("entries"):
        return True  # No registry or no entries — safe

    now = datetime.now(timezone.utc)
    active_agents = []

    for entry in registry["entries"]:
        try:
            hb = datetime.fromisoformat(entry["last_heartbeat"])
        except (KeyError, ValueError):
            continue
        age_hours = (now - hb).total_seconds() / 3600

        # Skip stale entries (heartbeat older than threshold)
        if age_hours > ACTIVE_AGENT_STALE_HOURS:
            continue

        # Skip entries whose worktree directory no longer exists
        wt_path = entry.get("worktree_path", "")
        if wt_path and not Path(wt_path).is_dir():
            continue

        label = entry.get("change_id", "unknown")
        agent_id = entry.get("agent_id")
        if agent_id:
            label = f"{label}/{agent_id}"
        active_agents.append(label)

    if not active_agents:
        return True

    agent_list = ", ".join(active_agents)
    if force:
        print(
            f"Warning: {len(active_agents)} active agent(s) detected "
            f"({agent_list}). Proceeding anyway (--force).",
            file=sys.stderr,
        )
        return True

    print(
        f"Error: {len(active_agents)} active agent(s) detected in worktree "
        f"registry: {agent_list}.\n"
        "Sync-point skills (merge-pull-requests, update-specs) require "
        "exclusive access to the shared checkout. Running them while other "
        "agents are active may cause interference.\n"
        "Options:\n"
        "  - Wait for active agents to finish\n"
        "  - Use --force to proceed anyway\n"
        "  - Run 'python3 skills/worktree/scripts/worktree.py gc' to clean "
        "stale entries",
        file=sys.stderr,
    )
    return False

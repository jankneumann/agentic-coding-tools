"""Shared utilities for merge-pull-requests scripts.

Provides common functions for gh CLI interaction, argument parsing,
and author extraction used across discover, staleness, comment, and merge scripts.
"""

import subprocess
import sys

GH_TIMEOUT = 30
GIT_TIMEOUT = 60


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

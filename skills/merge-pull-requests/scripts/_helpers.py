"""Shared utilities for merge-pull-requests scripts.

Provides common functions for gh CLI interaction, argument parsing,
and author extraction used across discover, staleness, comment, and merge scripts.
"""

import shutil
import subprocess
import sys
from pathlib import Path

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


# Stderr fragments meaning "the PR branch already contains its base". The first
# is the Update Branch API's own 422 wording; the other two predate it and are
# kept for compatibility. Every update-branch caller shares this list: two
# private copies of the check are how the real wording went missing.
_UPDATE_BRANCH_CURRENT_MARKERS = (
    "no new commits on the base branch",
    "already up-to-date",
    "not behind",
)


def update_branch_already_current(stderr: str) -> bool:
    """True when a failed update-branch call only means nothing was behind."""
    lowered = stderr.lower()
    return any(marker in lowered for marker in _UPDATE_BRANCH_CURRENT_MARKERS)


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


def capture_head() -> dict:
    """Snapshot the checkout's HEAD state (branch name + SHA).

    ``branch`` is None when HEAD is detached (``git branch --show-current``
    prints nothing). Used to detect vendor CLIs mutating the shared
    checkout during review dispatch (issue #349).
    """
    branch = run_cmd(["git", "branch", "--show-current"], check=False)
    sha = run_cmd(["git", "rev-parse", "HEAD"], check=False)
    return {"branch": branch or None, "sha": sha}


def verify_and_restore_head(before: dict) -> dict:
    """Compare HEAD against a prior capture_head() snapshot; restore on drift.

    Returns a dict with ``drift_detected``, ``before``, ``after``,
    ``restored``, and ``error``. Restoration only checks out the original
    branch — it never discards working-tree changes; a failed restore is
    reported, not forced.
    """
    after = capture_head()
    drifted = after["branch"] != before["branch"] or after["sha"] != before["sha"]
    result = {
        "drift_detected": drifted,
        "before": before,
        "after": after,
        "restored": False,
        "error": None,
    }
    if not drifted:
        return result

    if before["branch"]:
        try:
            run_cmd(["git", "checkout", before["branch"]])
            now = capture_head()
            result["restored"] = (
                now["branch"] == before["branch"] and now["sha"] == before["sha"]
            )
            if not result["restored"]:
                result["error"] = (
                    f"checked out {before['branch']} but HEAD is now "
                    f"{now['sha']} (expected {before['sha']})"
                )
        except RuntimeError as e:
            result["error"] = str(e)
    else:
        result["error"] = (
            "HEAD was already detached before dispatch; no branch to restore"
        )
    return result


def _repo_toplevel() -> Path | None:
    top = run_cmd(["git", "rev-parse", "--show-toplevel"], check=False)
    return Path(top) if top else None


def capture_untracked() -> set[str]:
    """Snapshot untracked, non-ignored files as repository-relative paths.

    Pairs with ``quarantine_new_untracked()`` around vendor review dispatch.
    Ignored files (caches, venvs) are excluded: vendors running Python create
    them legitimately, and they can never be swept into a commit.
    """
    top = _repo_toplevel()
    if top is None:
        return set()
    out = run_cmd(
        ["git", "-C", str(top), "ls-files", "--others", "--exclude-standard", "-z"],
        check=False,
    )
    return {path for path in out.split("\0") if path}


def quarantine_new_untracked(before: set[str], dest: Path) -> dict:
    """Move files that appeared since ``before`` out of the working tree.

    Vendor CLIs run against the shared checkout and have left review output at
    the repository root (``pr484_review.json``, 2026-09-14), where the next
    ``git add -A`` sync-point commit would publish it. Files are moved under
    ``dest`` with their relative path kept, never deleted, because such a file
    can be the only readable copy of a vendor's findings. Pre-existing untracked
    files are left alone. Callers hold the sync point, so nothing else should be
    creating files in the checkout during dispatch.
    """
    result: dict = {
        "new_untracked": [],
        "moved": [],
        "quarantined_to": None,
        "errors": [],
    }
    top = _repo_toplevel()
    if top is None:
        return result
    new = sorted(capture_untracked() - before)
    result["new_untracked"] = new
    if not new:
        return result
    # A destination inside the checkout (relative, or an in-repo override)
    # would only relocate each file to another untracked path that the next
    # `git add -A` still publishes. Refuse and leave the files for the caller
    # to report as a failure.
    resolved = dest.resolve()
    if resolved.is_relative_to(top.resolve()):
        result["errors"].append(
            f"quarantine destination {resolved} is inside the checkout {top}; "
            "nothing was moved"
        )
        return result
    for rel in new:
        target = resolved / rel
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(top / rel), str(target))
            result["moved"].append(rel)
        except OSError as exc:
            result["errors"].append(f"{rel}: {exc}")
    if result["moved"]:
        result["quarantined_to"] = str(resolved)
    return result


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

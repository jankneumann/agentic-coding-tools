"""GET /openspec/proposals endpoint — list OpenSpec proposals with implementation state.

Authentication: Bearer API key (same dependency as other coordinator endpoints).
Data source: local filesystem + git subprocess.
Cache: 60s in-process TTL, ?refresh=true cache-bust.
503 fail-closed when .git directory is unavailable.

Implementation state detection (D5):
  - "in-impl": branch openspec/<id> (or claude/<id>) exists AND has commits whose
    diff touches paths outside openspec/changes/<id>/
  - "drafted": no such branch, OR branch only touches the proposal directory
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CACHE_TTL_SECONDS = 60
_GIT_TIMEOUT = 5  # seconds per git subprocess call

# ---------------------------------------------------------------------------
# In-process cache
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_cache_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Repo root resolution
# ---------------------------------------------------------------------------


def _get_repo_root() -> Path:
    """Return the repo root.

    Precedence: OPENSPEC_REPO_ROOT env var → __file__ parent^3 (the checkout root
    when the module lives at agent-coordinator/src/openspec_proposals_api.py).
    """
    override = os.environ.get("OPENSPEC_REPO_ROOT", "").strip()
    if override:
        return Path(override)
    # agent-coordinator/src/openspec_proposals_api.py → ../../ = repo root
    return Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _run_git(repo: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:  # type: ignore[type-arg]
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=check,
        timeout=_GIT_TIMEOUT,
    )


def _has_git_dir(repo: Path) -> bool:
    """Return True when repo has a .git directory (or file for worktrees)."""
    result = _run_git(repo, "rev-parse", "--git-dir")
    return result.returncode == 0


def _resolve_branch(repo: Path, change_id: str) -> str | None:
    """Find the first existing branch ref for the given change_id.

    Priority order per design D5:
      1. local  refs/heads/openspec/<id>
      2. remote refs/remotes/origin/openspec/<id>
      3. local  refs/heads/claude/<id>
      4. remote refs/remotes/origin/claude/<id>
    """
    candidates = [
        f"refs/heads/openspec/{change_id}",
        f"refs/remotes/origin/openspec/{change_id}",
        f"refs/heads/claude/{change_id}",
        f"refs/remotes/origin/claude/{change_id}",
    ]
    for ref in candidates:
        result = _run_git(repo, "rev-parse", "--verify", ref)
        if result.returncode == 0:
            return ref
    return None


def _count_code_changes_outside_proposal(
    repo: Path, branch_ref: str, change_id: str
) -> int:
    """Count commits on branch_ref vs main that touch files outside the change dir.

    Uses 'git rev-list --count <branch_ref> ^<base>' with pathspec exclusion.
    """
    # Determine base: prefer origin/main, fall back to main
    base_candidates = ["origin/main", "main"]
    base: str | None = None
    for candidate in base_candidates:
        result = _run_git(repo, "rev-parse", "--verify", candidate)
        if result.returncode == 0:
            base = candidate
            break

    if base is None:
        # Can't determine base → treat as 0 code changes
        return 0

    proposal_path = f"openspec/changes/{change_id}"

    try:
        result = _run_git(
            repo,
            "rev-list",
            "--count",
            branch_ref,
            f"^{base}",
            "--",
            # Exclude the proposal directory itself
            f":!{proposal_path}",
        )
        if result.returncode != 0:
            logger.debug(
                "rev-list failed for %s ^%s: %s", branch_ref, base, result.stderr.strip()
            )
            return 0
        count_str = result.stdout.strip()
        return int(count_str) if count_str.isdigit() else 0
    except (subprocess.TimeoutExpired, ValueError):
        return 0


def _detect_impl_state(
    repo: Path, change_id: str, proposal_path_str: str
) -> tuple[str, bool, str | None, int]:
    """Detect the implementation state for a proposal.

    Returns (status, has_branch, branch_name, code_changes_outside_proposal).
    """
    try:
        branch_ref = _resolve_branch(repo, change_id)
    except (subprocess.TimeoutExpired, OSError):
        return ("drafted", False, None, 0)

    if branch_ref is None:
        return ("drafted", False, None, 0)

    # Extract the short branch name from the ref
    if branch_ref.startswith("refs/heads/"):
        branch_name = branch_ref.removeprefix("refs/heads/")
    elif branch_ref.startswith("refs/remotes/"):
        branch_name = branch_ref.removeprefix("refs/remotes/")
    else:
        branch_name = branch_ref

    try:
        code_changes = _count_code_changes_outside_proposal(repo, branch_ref, change_id)
    except (subprocess.TimeoutExpired, OSError):
        code_changes = 0

    status = "in-impl" if code_changes > 0 else "drafted"
    return (status, True, branch_name, code_changes)


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------


def _parse_h1_title(proposal_text: str) -> str:
    """Extract the first H1 heading from proposal.md text."""
    for line in proposal_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.removeprefix("# ").strip()
    return ""


def _git_log_iso(repo: Path, path: str, format_str: str) -> str | None:
    """Return git log --format=<format_str> for a path, or None."""
    try:
        result = _run_git(repo, "log", "-1", f"--format={format_str}", "--", path)
        if result.returncode == 0 and result.stdout.strip():
            return str(result.stdout.strip())
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


# ---------------------------------------------------------------------------
# Proposal enumeration
# ---------------------------------------------------------------------------


def _enumerate_proposals(repo: Path) -> list[dict[str, Any]]:
    """Enumerate non-archive proposals, classify implementation state."""
    changes_dir = repo / "openspec" / "changes"
    if not changes_dir.is_dir():
        return []

    proposals: list[dict[str, Any]] = []

    for entry in sorted(changes_dir.iterdir()):
        # Skip non-directories and the archive directory
        if not entry.is_dir() or entry.name == "archive":
            continue

        change_id = entry.name
        proposal_md = entry / "proposal.md"

        if not proposal_md.exists():
            logger.warning(
                "Proposal directory %s has no proposal.md — skipping.", entry
            )
            continue

        try:
            proposal_text = proposal_md.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not read %s: %s", proposal_md, exc)
            continue

        title = _parse_h1_title(proposal_text)
        proposal_path_rel = f"openspec/changes/{change_id}"

        # Git timestamps
        created_at = _git_log_iso(
            repo, proposal_path_rel, "%aI"  # strict ISO 8601
        )
        updated_at = _git_log_iso(
            repo, proposal_path_rel, "%aI"
        )
        now_iso = datetime.now(tz=UTC).isoformat()
        if not created_at:
            created_at = now_iso
        if not updated_at:
            updated_at = now_iso

        # Implementation state
        status, has_branch, branch_name, code_changes = _detect_impl_state(
            repo, change_id, proposal_path_rel
        )

        proposals.append({
            "kind": "proposal",
            "id": f"proposal:{change_id}",
            "change_id": change_id,
            "title": title,
            "status": status,
            "created_at_iso": created_at,
            "updated_at_iso": updated_at,
            "proposal_path": f"{proposal_path_rel}/proposal.md",
            "has_tasks_md": (entry / "tasks.md").exists(),
            "has_design_md": (entry / "design.md").exists(),
            "has_spec_delta": (entry / "specs").is_dir() or any(
                f.suffix == ".md" and f.name not in ("proposal.md", "design.md", "tasks.md")
                for f in entry.iterdir()
            ),
            "has_branch": has_branch,
            "branch_name": branch_name,
            "code_changes_outside_proposal": code_changes,
        })

    return proposals


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_proposals(refresh: bool = False) -> dict[str, Any]:
    """Enumerate (or return cached) OpenSpec proposals.

    Returns the full ProposalListResponse payload.
    Raises RuntimeError("git_unavailable") when .git is absent.
    """
    repo = _get_repo_root()

    if not _has_git_dir(repo):
        raise RuntimeError("git_unavailable")

    cache_key = f"openspec_proposals:{repo}"

    async with _cache_lock:
        if not refresh and cache_key in _cache:
            minted_at, cached_proposals = _cache[cache_key]
            age = time.monotonic() - minted_at
            if age < _CACHE_TTL_SECONDS:
                return {
                    "generated_at_iso": datetime.fromtimestamp(
                        minted_at - time.monotonic() + time.time(), tz=UTC
                    ).isoformat(),
                    "source": "cache",
                    "cache_age_seconds": int(age),
                    "proposals": cached_proposals,
                }

        # Run the enumeration in a thread to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        proposals = await loop.run_in_executor(None, _enumerate_proposals, repo)

        now = time.monotonic()
        _cache[cache_key] = (now, proposals)

        return {
            "generated_at_iso": datetime.now(tz=UTC).isoformat(),
            "source": "live",
            "cache_age_seconds": 0,
            "proposals": proposals,
        }

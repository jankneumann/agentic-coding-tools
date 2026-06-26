"""Source descriptor parsing, local repo derivation, and hybrid cache warmup.

Public surface:
  SourceDescriptor — dataclass(kind, spec, repo)
  ParseWarning     — dataclass(entry, reason)
  LocalSourceCache — dataclass(proposals, minted_at, degraded, warning)
  parse_sources(env_val) -> (list[SourceDescriptor], list[ParseWarning])
  derive_local_repo(path) -> (repo_str, warning_str | None)
  warm_local_sources(sources) -> dict[str, LocalSourceCache]
  get_or_walk_local(src) -> (LocalSourceCache, "live" | "cache")
  invalidate_local_walk_cache() -> None
"""
from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_GIT_TIMEOUT = 2  # seconds per subprocess call for remote URL lookup

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceDescriptor:
    """A single parsed source entry from OPENSPEC_SOURCES."""

    kind: Literal["local", "github"]
    spec: str  # path for local, lowercase owner/repo for github
    repo: str  # derived <owner>/<repo> for label/cluster attribution


@dataclass(frozen=True)
class ParseWarning:
    """A warning produced when a source entry cannot be parsed."""

    entry: str
    reason: str


@dataclass
class LocalSourceCache:
    """Cached result of a local source walk."""

    proposals: list[dict[str, Any]]
    minted_at: float  # time.monotonic()
    degraded: bool = False
    warning: str | None = None


# ---------------------------------------------------------------------------
# Module-level cache for local sources
# ---------------------------------------------------------------------------

# key: spec (path string)
_local_cache: dict[str, LocalSourceCache] = {}


# ---------------------------------------------------------------------------
# parse_sources
# ---------------------------------------------------------------------------


def parse_sources(env_val: str) -> tuple[list[SourceDescriptor], list[ParseWarning]]:
    """Parse OPENSPEC_SOURCES env var value into SourceDescriptors.

    Each CSV entry is either ``local:<path>`` or ``github:<owner>/<repo>``.
    Invalid entries produce a ParseWarning; they do NOT prevent valid entries
    from being returned (per spec: only the endpoint itself fails closed on
    invalid config, not the parser — the endpoint checks for warnings).
    """
    descriptors: list[SourceDescriptor] = []
    warnings: list[ParseWarning] = []

    if not env_val.strip():
        return descriptors, warnings

    for raw in env_val.split(","):
        entry = raw.strip()
        if not entry:
            continue

        if entry.startswith("local:"):
            path_str = entry[len("local:"):]
            if not path_str:
                warnings.append(
                    ParseWarning(entry=entry, reason="empty path after 'local:'")
                )
                continue
            descriptors.append(
                SourceDescriptor(kind="local", spec=path_str, repo="")
            )

        elif entry.startswith("github:"):
            repo_part = entry[len("github:"):]
            normalized = repo_part.lower()
            if not _REPO_PATTERN.match(normalized):
                warnings.append(
                    ParseWarning(
                        entry=entry,
                        reason=f"'{repo_part}' does not match <owner>/<repo> pattern",
                    )
                )
                continue
            descriptors.append(
                SourceDescriptor(kind="github", spec=normalized, repo=normalized)
            )

        else:
            warnings.append(
                ParseWarning(entry=entry, reason="unknown prefix (expected 'local:' or 'github:')")
            )

    return descriptors, warnings


# ---------------------------------------------------------------------------
# derive_local_repo
# ---------------------------------------------------------------------------

# HTTPS forms: https://github.com/owner/repo.git  https://github.com/owner/repo
_HTTPS_PATTERN = re.compile(
    r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?$"
)
# SSH forms: git@github.com:owner/repo.git  git@github.com:owner/repo
_SSH_PATTERN = re.compile(
    r"git@github\.com:([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?$"
)


def derive_local_repo(path: Path) -> tuple[str, str | None]:
    """Derive <owner>/<repo> from a local checkout's git remote origin URL.

    Returns (repo, warning_if_any).

    On success: ("owner/repo", None) — lowercased.
    On fallback: ("local/<basename>", warning_str) — preserves owner/repo
      shape (R1-004) so the result passes ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$.
    """
    basename = path.name or "unknown"

    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        warning = f"git remote get-url failed for {path}: {exc}; falling back to local/{basename}"
        logger.warning(warning)
        return f"local/{basename}", warning

    if result.returncode != 0:
        warning = (
            f"No git remote 'origin' for {path} "
            f"(exit {result.returncode}); falling back to local/{basename}"
        )
        logger.warning(warning)
        return f"local/{basename}", warning

    origin_url = result.stdout.strip()

    # Try HTTPS pattern
    m = _HTTPS_PATTERN.match(origin_url)
    if m:
        repo = f"{m.group(1)}/{m.group(2)}".lower()
        return repo, None

    # Try SSH pattern
    m = _SSH_PATTERN.match(origin_url)
    if m:
        repo = f"{m.group(1)}/{m.group(2)}".lower()
        return repo, None

    # URL exists but can't be parsed as a GitHub URL
    warning = (
        f"Cannot parse GitHub owner/repo from origin URL '{origin_url}' "
        f"for {path}; falling back to local/{basename}"
    )
    logger.warning(warning)
    return f"local/{basename}", warning


# ---------------------------------------------------------------------------
# Local source walking (reuses openspec_proposals_api logic)
# ---------------------------------------------------------------------------


def _walk_local_source(src: SourceDescriptor) -> LocalSourceCache:
    """Walk a local source path and return a LocalSourceCache.

    Imports _enumerate_proposals from openspec_proposals_api to reuse the
    existing filesystem walk + git-timestamp logic unchanged.
    """
    path = Path(src.spec)
    minted_at = time.monotonic()

    if not path.exists() or not path.is_dir():
        warning = f"Local source path does not exist or is not a directory: {path}"
        logger.warning(warning)
        return LocalSourceCache(
            proposals=[], minted_at=minted_at, degraded=True, warning=warning
        )

    # Derive the repo identifier if not already set on the descriptor
    repo = src.repo
    if not repo:
        repo, _w = derive_local_repo(path)

    try:
        # Import here to avoid circular imports at module level
        from src.openspec_proposals_api import _enumerate_proposals

        raw_proposals = _enumerate_proposals(path)
    except Exception as exc:
        warning = f"Failed to walk local source {path}: {exc}"
        logger.warning(warning)
        return LocalSourceCache(
            proposals=[], minted_at=minted_at, degraded=True, warning=warning
        )

    # Inject repo + change_id_namespaced into each proposal
    proposals: list[dict[str, Any]] = []
    for p in raw_proposals:
        enriched = dict(p)
        enriched["repo"] = repo
        change_id = p.get("change_id")
        enriched["change_id_namespaced"] = (
            f"{repo}/{change_id}" if repo and change_id else None
        )
        proposals.append(enriched)

    return LocalSourceCache(proposals=proposals, minted_at=minted_at)


# ---------------------------------------------------------------------------
# warm_local_sources
# ---------------------------------------------------------------------------


def warm_local_sources(sources: list[SourceDescriptor]) -> dict[str, LocalSourceCache]:
    """Walk all local sources eagerly (boot warmup).

    Populates the module-level _local_cache and returns the full cache dict.
    Non-existent paths are marked degraded — boot does NOT crash.
    """
    global _local_cache

    for src in sources:
        if src.kind != "local":
            continue
        cache_entry = _walk_local_source(src)
        _local_cache[src.spec] = cache_entry
        if cache_entry.degraded:
            logger.warning(
                "Local source %s marked degraded at boot: %s",
                src.spec,
                cache_entry.warning,
            )
        else:
            logger.debug(
                "Warmed local source %s: %d proposals",
                src.spec,
                len(cache_entry.proposals),
            )

    return {k: v for k, v in _local_cache.items()}


# ---------------------------------------------------------------------------
# get_or_walk_local
# ---------------------------------------------------------------------------


def get_or_walk_local(
    src: SourceDescriptor,
) -> tuple[LocalSourceCache, Literal["live", "cache"]]:
    """Return cached local walk or trigger a new walk if cache is empty.

    Status:
      "cache" — served from _local_cache (populated by warm_local_sources or
                a prior get_or_walk_local call)
      "live"  — freshly walked (cache was absent or invalidated)
    """
    if src.spec in _local_cache:
        return _local_cache[src.spec], "cache"

    # Cache miss — walk now
    entry = _walk_local_source(src)
    _local_cache[src.spec] = entry
    return entry, "live"


# ---------------------------------------------------------------------------
# invalidate_local_walk_cache
# ---------------------------------------------------------------------------


def invalidate_local_walk_cache() -> None:
    """Bust the local source cache — all sources will be re-walked on next access."""
    global _local_cache
    _local_cache = {}

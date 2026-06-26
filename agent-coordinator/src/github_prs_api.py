"""GET /github/prs endpoint — list open pull requests across configured repos.

Authentication: Bearer API key (same dependency as other coordinator endpoints).
Data source: GitHub REST API, server-side PAT.
Cache: 60s in-process TTL, single-flight mutex, ?refresh=true cache-bust.
503 fail-closed when GITHUB_PAT is not set.
503 fail-closed when GITHUB_REPOS contains invalid entries.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from .github_classifier import classify_pr, from_rest_pr, to_pr_card_origin

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CACHE_TTL_SECONDS = 60
_DEFAULT_REPOS = "jankneumann/agentic-coding-tools"
_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_MAX_CONCURRENT_REVIEW_FETCHES = 20

# ---------------------------------------------------------------------------
# In-process cache: { cache_key: (minted_at_float, payload_list) }
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_cache_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_repos() -> list[str] | None:
    """Parse GITHUB_REPOS env var.  Returns None on validation error."""
    raw = os.environ.get("GITHUB_REPOS", _DEFAULT_REPOS).strip()
    repos = [r.strip() for r in raw.split(",") if r.strip()]
    for repo in repos:
        if not _REPO_PATTERN.match(repo):
            return None
    return repos


def reduce_reviews(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """Reduce a GitHub reviews payload to a ReviewSummary.

    State precedence (highest → lowest): changes_requested > approved > commented > none.
    Dismissed reviews are excluded.
    Per reviewer, only the most recent non-dismissed review counts.
    Returns: {"state": str, "reviewer_count": int, "last_reviewed_at_iso": str|None}
    """
    # Build latest non-dismissed review per reviewer
    latest_per_reviewer: dict[str, dict[str, Any]] = {}
    for review in reviews:
        state = review.get("state", "").upper()
        if state == "DISMISSED":
            continue
        user = review.get("user") or {}
        login = user.get("login", "unknown")
        submitted_at = review.get("submitted_at", "")
        prev = latest_per_reviewer.get(login)
        if prev is None or submitted_at >= prev.get("submitted_at", ""):
            latest_per_reviewer[login] = {
                "state": state,
                "submitted_at": submitted_at,
            }

    if not latest_per_reviewer:
        return {"state": "none", "reviewer_count": 0, "last_reviewed_at_iso": None}

    # Determine aggregate state (precedence: changes_requested > approved > commented)
    states = {v["state"] for v in latest_per_reviewer.values()}
    if "CHANGES_REQUESTED" in states:
        agg_state = "changes_requested"
    elif "APPROVED" in states:
        agg_state = "approved"
    else:
        agg_state = "commented"

    # Find the latest timestamp across all non-dismissed reviews
    last_ts = max(
        (v["submitted_at"] for v in latest_per_reviewer.values() if v["submitted_at"]),
        default=None,
    )

    return {
        "state": agg_state,
        "reviewer_count": len(latest_per_reviewer),
        "last_reviewed_at_iso": last_ts,
    }


def derive_pr_status(*, is_draft: bool, review_summary: dict[str, Any]) -> str:
    """Derive PRCard.status from draft flag + review summary.

    Precedence ladder:
      1. draft → "draft"
      2. changes_requested → "changes_requested"
      3. approved → "approved"
      4. reviewer_count > 0 (commented) → "review"
      5. else → "open"
    """
    if is_draft:
        return "draft"
    state = review_summary.get("state", "none")
    if state == "changes_requested":
        return "changes_requested"
    if state == "approved":
        return "approved"
    if review_summary.get("reviewer_count", 0) > 0:
        return "review"
    return "open"


async def _fetch_reviews(
    client: httpx.AsyncClient, repo: str, pr_number: int, pat: str
) -> list[dict[str, Any]]:
    """Fetch reviews for a single PR.  Returns empty list on error."""
    try:
        response = await client.get(
            f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews",
            headers={
                "Authorization": f"Bearer {pat}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        if response.status_code == 200:
            return response.json()  # type: ignore[no-any-return]
        logger.warning(
            "Reviews fetch failed for %s#%d: HTTP %d",
            repo,
            pr_number,
            response.status_code,
        )
        return []
    except Exception:
        logger.exception("Error fetching reviews for %s#%d", repo, pr_number)
        return []


async def _fetch_prs_for_repo(repo: str, pat: str) -> list[dict[str, Any]]:
    """Fetch all open PRs for a single repo from GitHub REST API."""
    url = f"https://api.github.com/repos/{repo}/pulls"
    prs: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        page = 1
        while True:
            params: dict[str, int | str] = {
                "state": "open",
                "per_page": 100,
                "page": page,
            }
            resp = await client.get(
                url,
                params=params,
                headers={
                    "Authorization": f"Bearer {pat}",
                    "Accept": "application/vnd.github.v3+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            resp.raise_for_status()
            page_data: list[dict[str, Any]] = resp.json()
            if not page_data:
                break
            prs.extend(page_data)
            if len(page_data) < 100:
                break
            page += 1

        # Fetch reviews concurrently (cap at _MAX_CONCURRENT_REVIEW_FETCHES)
        # Skip draft PRs — drafts have no review state worth surfacing (R6 mitigation)
        sem = asyncio.Semaphore(_MAX_CONCURRENT_REVIEW_FETCHES)

        async def _guarded_fetch(pr: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
            if pr.get("draft", False):
                return pr, []
            async with sem:
                reviews = await _fetch_reviews(client, repo, pr["number"], pat)
            return pr, reviews

        pairs = await asyncio.gather(*[_guarded_fetch(pr) for pr in prs])

    # Build PRCard dicts
    result: list[dict[str, Any]] = []
    for rest_pr, reviews in pairs:
        adapted = from_rest_pr(rest_pr)
        classification = classify_pr(adapted)
        review_summary = reduce_reviews(reviews)
        is_draft: bool = rest_pr.get("draft", False)
        pr_status = derive_pr_status(is_draft=is_draft, review_summary=review_summary)
        card_origin = to_pr_card_origin(classification["origin"])
        number = rest_pr["number"]

        result.append({
            "kind": "pr",
            "id": f"pr:{repo}:{number}",
            "change_id": classification.get("change_id"),
            "repo": repo,
            "number": number,
            "title": rest_pr.get("title", ""),
            "author": adapted["author"].get("login", "unknown"),
            "head_branch": adapted["headRefName"],
            "base_branch": adapted["baseRefName"],
            "origin": card_origin,
            "status": pr_status,
            "review_summary": review_summary,
            "is_draft": is_draft,
            "url": adapted["url"],
            "created_at_iso": adapted["createdAt"],
            "updated_at_iso": adapted["updatedAt"],
        })

    return result


async def get_prs(refresh: bool = False) -> dict[str, Any]:
    """Fetch (or return cached) PRs across all configured repos.

    Returns the full PRListResponse payload.
    Raises ValueError with an error code string on config problems.
    Raises RuntimeError with an error code string when PAT is missing.
    """
    pat = os.environ.get("GITHUB_PAT", "").strip()
    if not pat:
        raise RuntimeError("github_pat_missing")

    repos = _parse_repos()
    if repos is None:
        raise ValueError("github_repos_invalid")

    cache_key = "github_prs:" + ",".join(sorted(repos))

    async with _cache_lock:
        if not refresh and cache_key in _cache:
            minted_at, cached_prs = _cache[cache_key]
            age = time.monotonic() - minted_at
            if age < _CACHE_TTL_SECONDS:
                return {
                    "generated_at_iso": datetime.fromtimestamp(
                        minted_at - time.monotonic() + time.time(), tz=UTC
                    ).isoformat(),
                    "source": "cache",
                    "cache_age_seconds": int(age),
                    "prs": cached_prs,
                }

        # Fetch all repos concurrently
        repo_results = await asyncio.gather(
            *[_fetch_prs_for_repo(repo, pat) for repo in repos],
            return_exceptions=True,
        )

        all_prs: list[dict[str, Any]] = []
        for result in repo_results:
            if isinstance(result, BaseException):
                logger.warning("Failed to fetch PRs for a repo: %s", result)
                continue
            all_prs.extend(result)

        # Sort by updated_at descending (newest first)
        all_prs.sort(key=lambda p: p.get("updated_at_iso", ""), reverse=True)

        now = time.monotonic()
        _cache[cache_key] = (now, all_prs)

        return {
            "generated_at_iso": datetime.now(tz=UTC).isoformat(),
            "source": "live",
            "cache_age_seconds": 0,
            "prs": all_prs,
        }

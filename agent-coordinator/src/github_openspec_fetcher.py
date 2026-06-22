"""GitHub REST fetcher for OpenSpec proposals.

Public surface:
  fetch_proposals_from_github(source, pat, budget) -> (proposals, warnings)

Implements D5 (reuse GITHUB_PAT), D6 (degraded mode), D7 (budget cap).
REST field-shape adapter invariant: proposal_path comes from html_url field.
"""
from __future__ import annotations

import base64
import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx

from src.openspec_sources import SourceDescriptor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PER_SOURCE_TIMEOUT = 10.0  # seconds
_GITHUB_API_BASE = "https://api.github.com"
_DEFAULT_BUDGET = 50

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _github_headers(pat: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _parse_h1_title(text: str) -> str:
    """Extract the first H1 heading from proposal.md text."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.removeprefix("# ").strip()
    return ""


def _b64decode(content: str) -> str:
    """Decode base64 content from GitHub API (may include newlines)."""
    cleaned = content.replace("\n", "").replace(" ", "")
    return base64.b64decode(cleaned).decode("utf-8", errors="replace")


def _make_warning(source: SourceDescriptor, error: str, **extra: Any) -> dict[str, Any]:
    w: dict[str, Any] = {
        "source": f"github:{source.spec}",
        "error": error,
    }
    w.update(extra)
    return w


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


# ---------------------------------------------------------------------------
# fetch_proposals_from_github
# ---------------------------------------------------------------------------


async def fetch_proposals_from_github(
    source: SourceDescriptor,
    pat: str,
    budget: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch all proposals from a github source, respecting the budget cap.

    Returns (proposals, warnings).
    Never raises — all errors become warnings in the return value.

    REST field-shape contract (critical invariant):
      - Only type == "dir" entries from /contents/openspec/changes are processed.
      - The "archive" directory is excluded by name.
      - proposal_path is sourced from the html_url field of the proposal.md
        entry, NOT manually concatenated.
      - Title is parsed from base64-decoded content field.
    """
    if budget is None:
        env_cap = os.environ.get("OPENSPEC_SOURCES_GITHUB_CAP", "").strip()
        budget = int(env_cap) if env_cap.isdigit() else _DEFAULT_BUDGET

    owner_repo = source.spec
    proposals: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    try:
        async with httpx.AsyncClient(timeout=_PER_SOURCE_TIMEOUT) as client:
            proposals, warnings = await _do_fetch(
                client, source, owner_repo, pat, budget
            )
    except httpx.TimeoutException:
        logger.warning("Timeout fetching proposals from github:%s", owner_repo)
        warnings.append(_make_warning(source, "github_timeout"))
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response else 0
        if status == 404:
            warnings.append(_make_warning(source, "github_404", status=404))
        elif status in (401, 403):
            warnings.append(_make_warning(source, "github_pat_denied", status=status))
        else:
            warnings.append(_make_warning(source, f"github_http_{status}", status=status))
    except Exception as exc:
        logger.warning("Unexpected error fetching from github:%s: %s", owner_repo, exc)
        warnings.append(_make_warning(source, "github_error", message=str(exc)))

    return proposals, warnings


async def _do_fetch(
    client: httpx.AsyncClient,
    source: SourceDescriptor,
    owner_repo: str,
    pat: str,
    budget: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Internal: perform the REST calls and return (proposals, warnings).

    May raise httpx exceptions — the caller wraps them.
    """
    warnings: list[dict[str, Any]] = []
    request_count = 0

    # Step 1: directory listing
    listing_url = f"{_GITHUB_API_BASE}/repos/{owner_repo}/contents/openspec/changes"
    resp = await client.get(listing_url, headers=_github_headers(pat))
    request_count += 1

    if resp.status_code == 404:
        warnings.append(_make_warning(source, "github_404", status=404))
        return [], warnings
    if resp.status_code in (401, 403):
        warnings.append(
            _make_warning(source, "github_pat_denied", status=resp.status_code)
        )
        return [], warnings
    if resp.status_code >= 400:
        warnings.append(
            _make_warning(source, f"github_http_{resp.status_code}", status=resp.status_code)
        )
        return [], warnings

    listing: list[dict[str, Any]] = resp.json()

    # Step 2: filter to non-archive dirs, sort alphabetically for determinism
    change_dirs = sorted(
        [
            entry
            for entry in listing
            if entry.get("type") == "dir" and entry.get("name") != "archive"
        ],
        key=lambda e: e["name"],
    )

    # Step 3: enforce budget cap
    total = len(change_dirs)
    if total > budget:
        truncated = total - budget
        change_dirs = change_dirs[:budget]
        warnings.append(
            _make_warning(
                source,
                "github_budget_exceeded",
                message=f"{truncated} changes truncated",
            )
        )

    # Step 4: for each change dir, fetch its contents to find proposal.md
    proposals: list[dict[str, Any]] = []

    for change_entry in change_dirs:
        change_id = change_entry["name"]

        contents_url = (
            f"{_GITHUB_API_BASE}/repos/{owner_repo}/contents/openspec/changes/{change_id}"
        )
        contents_resp = await client.get(contents_url, headers=_github_headers(pat))
        request_count += 1

        if contents_resp.status_code != 200:
            # Skip this dir (stray directory without proposal.md)
            logger.debug(
                "Skipping %s/%s: contents returned %d",
                owner_repo,
                change_id,
                contents_resp.status_code,
            )
            continue

        contents: list[dict[str, Any]] = contents_resp.json()

        # Find proposal.md entry
        proposal_entry = next(
            (
                e
                for e in contents
                if e.get("name") == "proposal.md" and e.get("type") == "file"
            ),
            None,
        )
        if proposal_entry is None:
            # 404 semantics — stray dir, skip
            continue

        # CRITICAL: proposal_path from html_url (NOT manually concatenated)
        proposal_path = proposal_entry["html_url"]

        # Title from base64-decoded content
        raw_content = proposal_entry.get("content", "")
        title = ""
        if raw_content:
            try:
                decoded = _b64decode(raw_content)
                title = _parse_h1_title(decoded)
            except Exception:
                pass

        # Check for tasks.md, design.md, specs/
        has_tasks_md = any(
            e.get("name") == "tasks.md" and e.get("type") == "file" for e in contents
        )
        has_design_md = any(
            e.get("name") == "design.md" and e.get("type") == "file" for e in contents
        )
        has_spec_delta = any(
            e.get("name") == "specs" and e.get("type") == "dir" for e in contents
        ) or any(
            e.get("type") == "file"
            and e.get("name", "").endswith(".md")
            and e.get("name") not in ("proposal.md", "design.md", "tasks.md")
            for e in contents
        )

        # Branch detection
        has_branch, branch_name, code_changes = await _probe_branch(
            client, owner_repo, change_id, pat
        )
        request_count += 2  # conservative upper bound for branch probe calls

        status = "in-impl" if code_changes > 0 else "drafted"

        proposals.append({
            "kind": "proposal",
            "id": f"proposal:{owner_repo}:{change_id}",
            "change_id": change_id,
            "repo": source.repo,
            "change_id_namespaced": f"{source.repo}/{change_id}",
            "title": title,
            "status": status,
            "created_at_iso": _now_iso(),
            "updated_at_iso": _now_iso(),
            "proposal_path": proposal_path,
            "has_tasks_md": has_tasks_md,
            "has_design_md": has_design_md,
            "has_spec_delta": has_spec_delta,
            "has_branch": has_branch,
            "branch_name": branch_name,
            "code_changes_outside_proposal": code_changes,
        })

    return proposals, warnings


async def _probe_branch(
    client: httpx.AsyncClient,
    owner_repo: str,
    change_id: str,
    pat: str,
) -> tuple[bool, str | None, int]:
    """Check if openspec/<change_id> or claude/<change_id> branch exists.

    Returns (has_branch, branch_name, code_changes_outside_proposal).
    """
    headers = _github_headers(pat)

    # Try openspec/<change_id> first, then claude/<change_id>
    for prefix in ("openspec", "claude"):
        branch_ref = f"{prefix}/{change_id}"
        branch_url = f"{_GITHUB_API_BASE}/repos/{owner_repo}/branches/{branch_ref}"
        try:
            resp = await client.get(branch_url, headers=headers)
        except Exception:
            continue

        if resp.status_code == 200:
            # Branch exists — count commits outside the proposal dir
            code_changes = await _count_outside_changes(
                client, owner_repo, branch_ref, change_id, pat
            )
            return True, branch_ref, code_changes

    return False, None, 0


async def _count_outside_changes(
    client: httpx.AsyncClient,
    owner_repo: str,
    branch_ref: str,
    change_id: str,
    pat: str,
) -> int:
    """Count commits on branch that touch files outside openspec/changes/{change_id}/."""
    compare_url = (
        f"{_GITHUB_API_BASE}/repos/{owner_repo}/compare/main...{branch_ref}"
    )
    try:
        resp = await client.get(compare_url, headers=_github_headers(pat))
    except Exception:
        return 0

    if resp.status_code != 200:
        return 0

    data: dict[str, Any] = resp.json()
    files: list[dict[str, Any]] = data.get("files", [])
    proposal_prefix = f"openspec/changes/{change_id}/"

    outside = sum(
        1
        for f in files
        if not f.get("filename", "").startswith(proposal_prefix)
    )
    return outside

"""GitHub PR classification — single-sourced for kanban-viz and merge-pull-requests skill.

This module is the canonical home for:
  - classify_pr()    — raw classification (9-value origin)
  - from_rest_pr()   — REST→gh-CLI field-name adapter (MUST be applied before classify_pr)
  - to_pr_card_origin() — fold 9-value origin → 6-value PRCard.origin enum

The merge-pull-requests skill imports classify_pr + helpers from here.
The kanban-viz endpoint chains from_rest_pr → classify_pr → to_pr_card_origin.

Origin values returned by classify_pr():
  openspec, codex, dependabot, renovate, sentinel, bolt, palette, jules, other

PRCard.origin enum (6 values, after to_pr_card_origin fold):
  openspec, codex, dependabot, renovate, jules, manual
"""
from __future__ import annotations

import re
from typing import Any

# =============================================================================
# Jules automation heuristics
# =============================================================================

# Label / branch / title patterns per Jules automation type.
# Title match alone is weak — only used when combined with author signal.
JULES_PATTERNS: dict[str, dict[str, list[str]]] = {
    "sentinel": {
        "labels": ["sentinel", "security"],
        "branch": ["sentinel", "security-fix"],
        "title": [r"\bsecurity\b", r"\bvulnerabilit", r"\bcve\b"],
    },
    "bolt": {
        "labels": ["bolt", "performance"],
        "branch": ["bolt", "perf-fix", "performance"],
        "title": [r"\bperformance\b", r"\boptimiz", r"\bspeed\b"],
    },
    "palette": {
        "labels": ["palette", "ux"],
        "branch": ["palette", "ux-fix", "ui-fix"],
        "title": [r"\bux\b", r"\bui\b", r"\baccessibilit"],
    },
}

# Known bot authors for Jules automations
JULES_AUTHORS: set[str] = {"jules", "jules[bot]", "jules-bot"}


# =============================================================================
# Helpers (also imported by skills/merge-pull-requests/scripts/discover_prs.py)
# =============================================================================


def safe_author(obj: dict[str, Any], key: str = "author") -> str:
    """Extract author login from a dict, handling null/missing author."""
    author = obj.get(key)
    if author is None:
        return "unknown"
    return author.get("login", "unknown") or "unknown"


def is_jules_author(author: str) -> bool:
    """Return True when the author string matches a known Jules bot handle."""
    return author.lower() in JULES_AUTHORS


# =============================================================================
# classify_pr
# =============================================================================


def classify_pr(pr: dict[str, Any]) -> dict[str, Any]:
    """Classify a PR dict (gh-CLI field names) into origin + change_id.

    Input field names expected: headRefName, body, title, labels[].name,
    author.login, isDraft, url, createdAt.

    For REST payloads, call from_rest_pr() first to adapt field names.

    Returns {"origin": str, "change_id": str | None}.
    The origin is one of: openspec, codex, dependabot, renovate,
    sentinel, bolt, palette, jules, other.
    """
    branch: str = pr.get("headRefName", "")
    body: str = pr.get("body", "") or ""
    title: str = pr.get("title", "")
    labels: list[str] = [label.get("name", "").lower() for label in pr.get("labels", [])]
    author: str = safe_author(pr)

    # OpenSpec detection
    # Body marker is checked first — explicit 'Implements OpenSpec:' gives us a
    # canonical change-id even on branches that don't follow openspec/* naming
    # (e.g. claude/* cloud-session branches that use OPENSPEC_BRANCH_OVERRIDE).
    body_match = re.search(r"Implements OpenSpec:\s*`?([a-z0-9-]+)`?", body)
    change_id_from_body: str | None = body_match.group(1) if body_match else None

    if branch.startswith("openspec/"):
        change_id = change_id_from_body or branch.removeprefix("openspec/")
        return {"origin": "openspec", "change_id": change_id}

    # claude/* branches: agent-authored OpenSpec work; branch slug is not a
    # reliable change-id (random suffix), so we only set it from body marker.
    if branch.startswith("claude/"):
        return {"origin": "openspec", "change_id": change_id_from_body}

    if change_id_from_body:
        return {"origin": "openspec", "change_id": change_id_from_body}

    # Dependabot detection
    if author.lower() in ("dependabot[bot]", "dependabot") or branch.startswith("dependabot/"):
        return {"origin": "dependabot", "change_id": None}

    # Renovate detection
    if author.lower() in ("renovate[bot]", "renovate") or branch.startswith("renovate/"):
        return {"origin": "renovate", "change_id": None}

    # Jules automation detection
    # Label or branch match is a strong signal on its own.
    # Title match alone is weak — only use it combined with author signal.
    author_is_jules = is_jules_author(author)

    for jules_type, patterns in JULES_PATTERNS.items():
        # Strong signals: labels or branch patterns
        if any(lbl in labels for lbl in patterns["labels"]):
            return {"origin": jules_type, "change_id": None}
        if any(tok in branch.lower() for tok in patterns["branch"]):
            return {"origin": jules_type, "change_id": None}
        # Weak signal: title match requires author confirmation
        if author_is_jules and any(
            re.search(p, title, re.IGNORECASE) for p in patterns["title"]
        ):
            return {"origin": jules_type, "change_id": None}

    # If author is Jules but no specific type matched, classify generically
    if author_is_jules:
        return {"origin": "jules", "change_id": None}

    # Codex detection
    if "codex" in author.lower() or "codex" in branch.lower():
        return {"origin": "codex", "change_id": None}

    return {"origin": "other", "change_id": None}


# =============================================================================
# from_rest_pr — REST API → gh-CLI field name adapter
# =============================================================================


def from_rest_pr(rest_payload: dict[str, Any]) -> dict[str, Any]:
    """Adapt a GitHub REST API pull-request payload to gh-CLI field names.

    This adapter MUST be applied to every REST payload before calling
    classify_pr().  Without it, headRefName is empty and every PR falls
    through to origin="other" / change_id=None.

    Translation table (REST → gh-CLI):
      head.ref         → headRefName
      user.login       → author.login
      draft            → isDraft
      created_at       → createdAt
      updated_at       → updatedAt
      html_url         → url
      base.ref         → baseRefName

    Pass-through: body, title, labels, number.
    """
    head: dict[str, Any] = rest_payload.get("head", {})
    user: dict[str, Any] = rest_payload.get("user", {})
    base: dict[str, Any] = rest_payload.get("base", {})

    return {
        "headRefName": head.get("ref", ""),
        "baseRefName": base.get("ref", ""),
        "author": {"login": user.get("login", "unknown")},
        "isDraft": rest_payload.get("draft", False),
        "createdAt": rest_payload.get("created_at", ""),
        "updatedAt": rest_payload.get("updated_at", ""),
        "url": rest_payload.get("html_url", ""),
        "number": rest_payload.get("number"),
        # pass-through fields
        "body": rest_payload.get("body", "") or "",
        "title": rest_payload.get("title", ""),
        "labels": rest_payload.get("labels", []),
    }


# =============================================================================
# to_pr_card_origin — fold 9-value → 6-value PRCard.origin enum
# =============================================================================

# Mapping for non-passthrough values.
_FOLD: dict[str, str] = {
    "sentinel": "jules",
    "bolt": "jules",
    "palette": "jules",
    "jules": "jules",
    "other": "manual",
}

# 6-value enum defined in the OpenAPI contract
_VALID_CARD_ORIGINS: frozenset[str] = frozenset(
    {"openspec", "codex", "dependabot", "renovate", "jules", "manual"}
)


def to_pr_card_origin(classifier_origin: str) -> str:
    """Fold the 9-value classifier origin to the 6-value PRCard.origin enum.

    Jules sub-types (sentinel, bolt, palette, jules) → "jules".
    "other" → "manual".
    openspec, codex, dependabot, renovate → passthrough.
    """
    result = _FOLD.get(classifier_origin, classifier_origin)
    assert result in _VALID_CARD_ORIGINS, (
        f"Unexpected classifier origin {classifier_origin!r} produced {result!r}; "
        f"update _FOLD map to cover new classifier outputs."
    )
    return result

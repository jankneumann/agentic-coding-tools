"""Portable GitHub pull-request classification shared by installed skills.

This module is the canonical home for the merge skill and coordinator PR
classification behavior.  It intentionally depends only on the standard
library so it can be copied with ``skills/shared`` into consumer repositories.
"""

from __future__ import annotations

import re
from typing import Any


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

JULES_AUTHORS: set[str] = {"jules", "jules[bot]", "jules-bot"}


def safe_author(obj: dict[str, Any], key: str = "author") -> str:
    """Extract an author login while tolerating missing and null authors."""
    author = obj.get(key)
    if author is None:
        return "unknown"
    return author.get("login", "unknown") or "unknown"


def is_jules_author(author: str) -> bool:
    """Return whether *author* is a known Jules bot handle."""
    return author.lower() in JULES_AUTHORS


def classify_pr(pr: dict[str, Any]) -> dict[str, Any]:
    """Classify a gh-CLI-shaped pull request into origin and change id."""
    branch: str = pr.get("headRefName", "")
    body: str = pr.get("body", "") or ""
    title: str = pr.get("title", "")
    labels = [label.get("name", "").lower() for label in pr.get("labels", [])]
    author = safe_author(pr)

    body_match = re.search(r"Implements OpenSpec:\s*`?([a-z0-9-]+)`?", body)
    change_id_from_body = body_match.group(1) if body_match else None

    if branch.startswith("openspec/"):
        return {
            "origin": "openspec",
            "change_id": change_id_from_body or branch.removeprefix("openspec/"),
        }
    if branch.startswith("claude/"):
        return {"origin": "openspec", "change_id": change_id_from_body}
    if change_id_from_body:
        return {"origin": "openspec", "change_id": change_id_from_body}

    if author.lower() in ("dependabot[bot]", "dependabot") or branch.startswith(
        "dependabot/"
    ):
        return {"origin": "dependabot", "change_id": None}
    if author.lower() in ("renovate[bot]", "renovate") or branch.startswith(
        "renovate/"
    ):
        return {"origin": "renovate", "change_id": None}

    author_is_jules = is_jules_author(author)
    for jules_type, patterns in JULES_PATTERNS.items():
        if any(label in labels for label in patterns["labels"]):
            return {"origin": jules_type, "change_id": None}
        if any(token in branch.lower() for token in patterns["branch"]):
            return {"origin": jules_type, "change_id": None}
        if author_is_jules and any(
            re.search(pattern, title, re.IGNORECASE) for pattern in patterns["title"]
        ):
            return {"origin": jules_type, "change_id": None}

    if author_is_jules:
        return {"origin": "jules", "change_id": None}
    if "codex" in author.lower() or "codex" in branch.lower():
        return {"origin": "codex", "change_id": None}
    return {"origin": "other", "change_id": None}


def from_rest_pr(rest_payload: dict[str, Any]) -> dict[str, Any]:
    """Adapt a GitHub REST pull-request payload to gh-CLI field names."""
    head = rest_payload.get("head", {})
    user = rest_payload.get("user", {})
    base = rest_payload.get("base", {})
    return {
        "headRefName": head.get("ref", ""),
        "baseRefName": base.get("ref", ""),
        "author": {"login": user.get("login", "unknown")},
        "isDraft": rest_payload.get("draft", False),
        "createdAt": rest_payload.get("created_at", ""),
        "updatedAt": rest_payload.get("updated_at", ""),
        "url": rest_payload.get("html_url", ""),
        "number": rest_payload.get("number"),
        "body": rest_payload.get("body", "") or "",
        "title": rest_payload.get("title", ""),
        "labels": rest_payload.get("labels", []),
    }


_FOLD: dict[str, str] = {
    "sentinel": "jules",
    "bolt": "jules",
    "palette": "jules",
    "jules": "jules",
    "other": "manual",
}
_VALID_CARD_ORIGINS = frozenset(
    {"openspec", "codex", "dependabot", "renovate", "jules", "manual"}
)


def to_pr_card_origin(classifier_origin: str) -> str:
    """Fold detailed classifier origins into the PR-card origin enum."""
    result = _FOLD.get(classifier_origin, classifier_origin)
    assert result in _VALID_CARD_ORIGINS, (
        f"Unexpected classifier origin {classifier_origin!r} produced {result!r}; "
        "update _FOLD map to cover new classifier outputs."
    )
    return result


__all__ = [
    "JULES_AUTHORS",
    "JULES_PATTERNS",
    "classify_pr",
    "from_rest_pr",
    "is_jules_author",
    "safe_author",
    "to_pr_card_origin",
]

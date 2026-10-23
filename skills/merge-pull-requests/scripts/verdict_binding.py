"""Bind a vendor review verdict to the code it reviewed and to the PR author.

A stored verdict is only evidence about one specific diff. ``bind`` records
which head (and which patch-id) the reviewers saw, who reviewed, and who
authored the PR, so that execution can later decide whether the verdict still
describes the live PR (``verdict_currency``) and whether it was independent of
the author (``independence_violation``).

Everything here is pure apart from the two ``git patch-id`` helpers. Nothing
calls ``gh``: callers pass ``gh`` output in.

Author identity is derived from commit trailers. That is advisory provenance,
not authentication: a trailer is text anyone can write.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

Currency = Literal["current", "rebased", "stale"]

#: Policy decisions that may stand in for a vendor review. Anything else that
#: makes a PR ineligible for review does not waive it.
POLICY_WAIVABLE_REASONS: frozenset[str] = frozenset({
    "skip_origin",
    "small_pr",
    "has_approval",
    "low_risk_judged",
    "automation_cheap_path",
})

# Model prefix decides first: a vendor CLI may run another family's model.
_MODEL_FAMILY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("claude-", "anthropic"),
    ("gpt-", "openai"),
    ("o1", "openai"),
    ("o3", "openai"),
    ("o4", "openai"),
    ("gemini-", "google"),
    ("grok-", "xai"),
)

_VENDOR_FAMILY: dict[str, str] = {
    "claude_code": "anthropic",
    "codex": "openai",
    "gemini": "google",
    "antigravity": "google",
    "grok": "xai",
}

# Lower-cased trailer prefix ("<Vendor>-Session:") to the vendor name used by
# the review dispatcher.
_SESSION_TRAILER_VENDOR: dict[str, str] = {
    "claude": "claude_code",
    "codex": "codex",
    "gemini": "gemini",
    "antigravity": "antigravity",
    "grok": "grok",
    "pi": "pi",
}

_SESSION_TRAILER = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)-Session:\s*(\S+)\s*$", re.IGNORECASE)
_CLAUDE_COAUTHOR = re.compile(r"^\s*Co-Authored-By:\s*Claude\b", re.IGNORECASE)
_SHA = re.compile(r"^[0-9a-f]{40}$")

_AUTHOR_KEYS = ("login", "vendor", "session_id")


def family_of(*, vendor: str | None, model: str | None) -> str | None:
    """Return the model family for a reviewer, or None when it is unknown."""
    if model:
        lowered = model.lower()
        for prefix, family in _MODEL_FAMILY_PREFIXES:
            if lowered.startswith(prefix):
                return family
    if vendor:
        return _VENDOR_FAMILY.get(vendor)
    return None


def _normalize_author(author: Mapping[str, Any] | None) -> dict[str, Any]:
    source = author if isinstance(author, Mapping) else {}
    return {key: source.get(key) or None for key in _AUTHOR_KEYS}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _same_family(reviewers: list[dict[str, Any]], author: dict[str, Any]) -> bool | None:
    author_family = family_of(vendor=author.get("vendor"), model=None)
    if author_family is None or not reviewers:
        return None
    families = [reviewer.get("family") for reviewer in reviewers]
    if author_family in families:
        return True
    if any(family is None for family in families):
        return None
    return False


def bind(
    review: Mapping[str, Any],
    *,
    head_sha: str | None,
    patch_id: str | None,
    author: Mapping[str, Any] | None,
    now: str | None = None,
) -> dict[str, Any]:
    """Return a copy of ``review`` carrying a ``binding`` block.

    Only reviewers whose dispatch succeeded are recorded: a failed lane saw
    nothing and vouches for nothing. The input is not modified.
    """
    reviewers: list[dict[str, Any]] = []
    for entry in review.get("vendors") or []:
        if not isinstance(entry, Mapping) or not entry.get("success"):
            continue
        vendor = entry.get("vendor")
        model = entry.get("model_used")
        reviewers.append({
            "vendor": vendor,
            "family": family_of(vendor=vendor, model=model),
            "model": model,
            "agent_id": entry.get("agent_id"),
        })
    normalized_author = _normalize_author(author)
    bound = dict(review)
    bound["binding"] = {
        "head_sha": head_sha,
        "patch_id": patch_id,
        "reviewers": reviewers,
        "author": normalized_author,
        "same_family": _same_family(reviewers, normalized_author),
        "bound_at": now or _now(),
    }
    return bound


def verdict_currency(
    binding: Any,
    live_head_sha: str | None,
    live_patch_id: str | None,
) -> Currency:
    """Classify a stored binding against the live PR.

    ``current`` when the head is unchanged, ``rebased`` when the head moved but
    both patch-ids are known and equal, ``stale`` otherwise (including when the
    verdict was never bound).
    """
    if not isinstance(binding, Mapping):
        return "stale"
    stored_head = binding.get("head_sha")
    if not stored_head:
        return "stale"
    if live_head_sha and stored_head == live_head_sha:
        return "current"
    stored_patch = binding.get("patch_id")
    if stored_patch and live_patch_id and stored_patch == live_patch_id:
        return "rebased"
    return "stale"


def stale_reason(binding: Any, live_head_sha: str | None) -> str:
    """Human-readable reason naming the reviewed and the live head."""
    stored = binding.get("head_sha") if isinstance(binding, Mapping) else None
    reviewed = stored[:7] if stored else "unbound"
    live = live_head_sha[:7] if live_head_sha else "unknown"
    return f"stale verdict: reviewed {reviewed}, live {live}"


def independence_violation(binding: Any) -> str | None:
    """Return why the review was not independent of the author, or None.

    A reviewer from the author's own vendor is accepted only when the author's
    session is known and differs from the reviewer's agent id.
    """
    if not isinstance(binding, Mapping):
        return None
    author = binding.get("author") if isinstance(binding.get("author"), Mapping) else {}
    author_vendor = author.get("vendor")
    if not author_vendor:
        return None
    session_id = author.get("session_id")
    for reviewer in binding.get("reviewers") or []:
        if not isinstance(reviewer, Mapping) or reviewer.get("vendor") != author_vendor:
            continue
        if not session_id:
            return (
                f"review independence cannot be shown: reviewer {author_vendor} shares the "
                "author's vendor and the author session is unknown"
            )
        if reviewer.get("agent_id") == session_id:
            return f"self-review: {author_vendor} session {session_id} reviewed its own PR"
    return None


def _message_lines(commit: Mapping[str, Any]) -> list[str]:
    text = "\n".join(
        str(commit.get(key) or "") for key in ("messageHeadline", "messageBody")
    )
    return text.splitlines()


def _session_from_url(value: str) -> str | None:
    segments = [segment for segment in value.split("/") if segment]
    return segments[-1] if segments else None


def _identity_from_commit(commit: Mapping[str, Any]) -> tuple[str, str | None] | None:
    coauthored_by_claude = False
    for line in _message_lines(commit):
        match = _SESSION_TRAILER.match(line)
        if match:
            vendor = _SESSION_TRAILER_VENDOR.get(match.group(1).lower())
            if vendor:
                return vendor, _session_from_url(match.group(2))
        if _CLAUDE_COAUTHOR.match(line):
            coauthored_by_claude = True
    if coauthored_by_claude:
        return "claude_code", None
    return None


def derive_author(pr_view: Mapping[str, Any]) -> dict[str, Any]:
    """Derive ``{login, vendor, session_id}`` from ``gh pr view --json author,commits``.

    The latest commit carrying an agent trailer decides; a PR with none is
    treated as human-authored (vendor and session null).
    """
    author = pr_view.get("author") if isinstance(pr_view, Mapping) else None
    login = author.get("login") if isinstance(author, Mapping) else None
    result: dict[str, Any] = {"login": login or None, "vendor": None, "session_id": None}
    commits = pr_view.get("commits") if isinstance(pr_view, Mapping) else None
    for commit in reversed(list(commits or [])):
        if not isinstance(commit, Mapping):
            continue
        identity = _identity_from_commit(commit)
        if identity:
            result["vendor"], result["session_id"] = identity
            break
    return result


def validate_binding(binding: Any) -> list[str]:
    """Return the shape errors of a binding block (empty when valid)."""
    if not isinstance(binding, Mapping):
        return ["binding is not an object"]
    errors: list[str] = []
    head_sha = binding.get("head_sha")
    if not isinstance(head_sha, str) or not _SHA.match(head_sha):
        errors.append("binding.head_sha must be a 40-character hex sha")
    if "patch_id" not in binding:
        errors.append("binding.patch_id is missing")
    elif binding["patch_id"] is not None and not isinstance(binding["patch_id"], str):
        errors.append("binding.patch_id must be a string or null")
    reviewers = binding.get("reviewers")
    if not isinstance(reviewers, list) or not all(isinstance(r, Mapping) for r in reviewers):
        errors.append("binding.reviewers must be a list of objects")
    author = binding.get("author")
    if not isinstance(author, Mapping) or any(key not in author for key in _AUTHOR_KEYS):
        errors.append("binding.author must be an object with login, vendor and session_id")
    if "same_family" not in binding or binding["same_family"] not in (True, False, None):
        errors.append("binding.same_family must be a boolean or null")
    if not isinstance(binding.get("bound_at"), str):
        errors.append("binding.bound_at must be a string")
    return errors


def patch_id_from_diff(diff_text: str) -> str | None:
    """Return the stable patch-id of a unified diff, or None when uncomputable."""
    if not diff_text or not diff_text.strip():
        return None
    try:
        result = subprocess.run(
            ["git", "patch-id", "--stable"],
            input=diff_text, capture_output=True, text=True, check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    fields = result.stdout.split()
    return fields[0] if fields else None


def patch_id(repo: str | Path, base: str, head: str) -> str | None:
    """Return the stable patch-id of ``head`` against its merge-base with ``base``."""
    try:
        merge_base = subprocess.run(
            ["git", "-C", str(repo), "merge-base", base, head],
            capture_output=True, text=True, check=False,
        )
        if merge_base.returncode != 0:
            return None
        diff = subprocess.run(
            ["git", "-C", str(repo), "diff", merge_base.stdout.strip(), head],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return None
    if diff.returncode != 0:
        return None
    return patch_id_from_diff(diff.stdout)

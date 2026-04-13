#!/usr/bin/env python3
"""Discover and classify open pull requests by origin.

Classifications:
  - openspec: branch matches openspec/* or body contains 'Implements OpenSpec:'
  - sentinel: Jules Sentinel (security) automation
  - bolt: Jules Bolt (performance) automation
  - palette: Jules Palette (UX) automation
  - codex: Created by Codex
  - dependabot: Dependabot dependency updates
  - renovate: Renovate dependency updates
  - other: Manual or unrecognized origin

Usage:
  python discover_prs.py [--dry-run]

Output: JSON array of PR objects to stdout.
"""

import argparse
import json
import re
import sys

from shared import check_clean_worktree, check_gh, run_gh, safe_author

# Jules automation heuristics: title patterns only match when combined
# with a label or author signal to avoid false positives on human PRs.
JULES_PATTERNS = {
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
JULES_AUTHORS = {"jules", "jules[bot]", "jules-bot"}


def get_default_branch() -> str:
    """Get the repository's default branch name."""
    try:
        raw = run_gh(["repo", "view", "--json", "defaultBranchRef"])
        data = json.loads(raw)
        ref = data.get("defaultBranchRef")
        if ref and ref.get("name"):
            return ref["name"]
    except (RuntimeError, json.JSONDecodeError, KeyError):
        pass
    print(
        "Warning: Could not determine default branch, falling back to 'main'.",
        file=sys.stderr,
    )
    return "main"


def fetch_open_prs() -> list[dict]:
    """Fetch all open PRs."""
    try:
        raw = run_gh([
            "pr", "list", "--state", "open", "--json",
            "number,title,author,headRefName,baseRefName,createdAt,labels,body,url,isDraft,isCrossRepository,autoMergeRequest",
            "--limit", "1000",
        ])
    except RuntimeError as e:
        print(f"Error fetching PRs: {e}", file=sys.stderr)
        sys.exit(1)
    if not raw:
        return []
    prs = json.loads(raw)
    if len(prs) >= 1000:
        print(
            "Warning: Fetched 1000 PRs (the maximum). "
            "Additional PRs may exist but were not retrieved.",
            file=sys.stderr,
        )
    return prs


def is_jules_author(author: str) -> bool:
    return author.lower() in JULES_AUTHORS


def classify_pr(pr: dict) -> dict:
    branch = pr.get("headRefName", "")
    body = pr.get("body", "") or ""
    title = pr.get("title", "")
    labels = [label.get("name", "").lower() for label in pr.get("labels", [])]
    author = safe_author(pr)

    # OpenSpec detection
    if branch.startswith("openspec/"):
        change_id = branch.removeprefix("openspec/")
        return {"origin": "openspec", "change_id": change_id}

    match = re.search(r"Implements OpenSpec:\s*`?([a-z0-9-]+)`?", body)
    if match:
        return {"origin": "openspec", "change_id": match.group(1)}

    # Dependabot detection
    if (author.lower() in ("dependabot[bot]", "dependabot")
            or branch.startswith("dependabot/")):
        return {"origin": "dependabot", "change_id": None}

    # Renovate detection
    if (author.lower() in ("renovate[bot]", "renovate")
            or branch.startswith("renovate/")):
        return {"origin": "renovate", "change_id": None}

    # Jules automation detection
    # Label or branch match is a strong signal on its own.
    # Title match alone is weak — only use it combined with author signal.
    author_is_jules = is_jules_author(author)

    for jules_type, patterns in JULES_PATTERNS.items():
        # Strong signals: labels or branch patterns
        if any(l in labels for l in patterns["labels"]):
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


def detect_dep_ecosystem(branch: str, origin: str) -> str | None:
    """Detect dependency ecosystem from Dependabot branch name.

    Dependabot branches follow the pattern: dependabot/<ecosystem>/<package>
    e.g. dependabot/npm_and_yarn/lodash-4.17.21, dependabot/pip/requests-2.28.0
    Renovate branches are less structured, so we don't attempt detection.
    """
    if origin != "dependabot":
        return None
    parts = branch.split("/")
    if len(parts) >= 3:
        return parts[1]  # e.g. "npm_and_yarn", "pip", "github_actions"
    return None


def discover() -> list[dict]:
    default_branch = get_default_branch()
    prs = fetch_open_prs()
    results = []
    for pr in prs:
        classification = classify_pr(pr)
        branch = pr.get("headRefName", "")
        base_branch = pr.get("baseRefName", default_branch)
        is_draft = pr.get("isDraft", False)
        is_stacked = base_branch != default_branch
        origin = classification["origin"]

        results.append({
            "number": pr["number"],
            "title": pr["title"],
            "author": safe_author(pr),
            "branch": branch,
            "base_branch": base_branch,
            "default_branch": default_branch,
            "created_at": pr.get("createdAt", ""),
            "labels": [label.get("name", "") for label in pr.get("labels", [])],
            "url": pr.get("url", ""),
            "is_draft": is_draft,
            "is_stacked": is_stacked,
            "is_fork": pr.get("isCrossRepository", False),
            "auto_merge_enabled": pr.get("autoMergeRequest") is not None,
            "dep_ecosystem": detect_dep_ecosystem(branch, origin),
            "origin": origin,
            "change_id": classification.get("change_id"),
        })
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Discover and classify open pull requests by origin.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only, no mutations")
    args = parser.parse_args()

    check_gh()
    check_clean_worktree()
    results = discover()

    if not results:
        print(json.dumps([], indent=2))
        if args.dry_run:
            print("# Dry-run: No open PRs found.", file=sys.stderr)
        return

    print(json.dumps(results, indent=2))

    if args.dry_run:
        drafts = sum(1 for r in results if r["is_draft"])
        stacked = sum(1 for r in results if r["is_stacked"])
        forks = sum(1 for r in results if r["is_fork"])
        auto_merge = sum(1 for r in results if r["auto_merge_enabled"])
        origins = {}
        for r in results:
            origins[r["origin"]] = origins.get(r["origin"], 0) + 1
        summary_parts = [f"{v} {k}" for k, v in sorted(origins.items())]
        flags = []
        if drafts:
            flags.append(f"{drafts} draft(s)")
        if stacked:
            flags.append(f"{stacked} stacked")
        if forks:
            flags.append(f"{forks} fork(s)")
        if auto_merge:
            flags.append(f"{auto_merge} auto-merge")
        flag_str = f", {', '.join(flags)}" if flags else ""
        print(
            f"# Dry-run: Found {len(results)} open PR(s) "
            f"({', '.join(summary_parts)}){flag_str}.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()

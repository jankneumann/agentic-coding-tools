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

import json
import re
import subprocess
import sys

GH_TIMEOUT = 30

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


def check_gh():
    try:
        subprocess.run(
            ["gh", "--version"], capture_output=True, text=True,
            check=True, timeout=GH_TIMEOUT,
        )
    except FileNotFoundError:
        print("Error: 'gh' CLI is not installed or not on PATH.", file=sys.stderr)
        sys.exit(1)


def run_gh(args: list[str]) -> str:
    result = subprocess.run(
        ["gh"] + args, capture_output=True, text=True,
        check=True, timeout=GH_TIMEOUT,
    )
    return result.stdout.strip()


def fetch_open_prs() -> list[dict]:
    """Fetch all open PRs using pagination (no hard limit)."""
    raw = run_gh([
        "pr", "list", "--state", "open", "--json",
        "number,title,author,headRefName,baseRefName,createdAt,labels,body,url,isDraft",
        "--limit", "1000",
    ])
    if not raw:
        return []
    return json.loads(raw)


def is_jules_author(author: str) -> bool:
    return author.lower() in JULES_AUTHORS


def classify_pr(pr: dict) -> dict:
    branch = pr.get("headRefName", "")
    body = pr.get("body", "") or ""
    title = pr.get("title", "")
    labels = [label.get("name", "").lower() for label in pr.get("labels", [])]
    author = pr.get("author", {}).get("login", "")
    base_branch = pr.get("baseRefName", "main")

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


def discover() -> list[dict]:
    prs = fetch_open_prs()
    results = []
    for pr in prs:
        classification = classify_pr(pr)
        base_branch = pr.get("baseRefName", "main")
        is_draft = pr.get("isDraft", False)
        is_stacked = base_branch != "main" and base_branch != "master"

        results.append({
            "number": pr["number"],
            "title": pr["title"],
            "author": pr.get("author", {}).get("login", "unknown"),
            "branch": pr.get("headRefName", ""),
            "base_branch": base_branch,
            "created_at": pr.get("createdAt", ""),
            "labels": [label.get("name", "") for label in pr.get("labels", [])],
            "url": pr.get("url", ""),
            "is_draft": is_draft,
            "is_stacked": is_stacked,
            "origin": classification["origin"],
            "change_id": classification.get("change_id"),
        })
    return results


def main():
    check_gh()
    dry_run = "--dry-run" in sys.argv
    results = discover()

    if not results:
        print(json.dumps([], indent=2))
        if dry_run:
            print("# Dry-run: No open PRs found.", file=sys.stderr)
        return

    print(json.dumps(results, indent=2))

    if dry_run:
        drafts = sum(1 for r in results if r["is_draft"])
        stacked = sum(1 for r in results if r["is_stacked"])
        origins = {}
        for r in results:
            origins[r["origin"]] = origins.get(r["origin"], 0) + 1
        summary_parts = [f"{v} {k}" for k, v in sorted(origins.items())]
        print(
            f"# Dry-run: Found {len(results)} open PR(s) "
            f"({', '.join(summary_parts)})"
            f"{f', {drafts} draft(s)' if drafts else ''}"
            f"{f', {stacked} stacked' if stacked else ''}.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()

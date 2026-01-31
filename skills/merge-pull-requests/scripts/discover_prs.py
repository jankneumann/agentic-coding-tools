#!/usr/bin/env python3
"""Discover and classify open pull requests by origin.

Classifications:
  - openspec: branch matches openspec/* or body contains 'Implements OpenSpec:'
  - sentinel: Jules Sentinel (security) automation
  - bolt: Jules Bolt (performance) automation
  - palette: Jules Palette (UX) automation
  - codex: Created by Codex
  - other: Manual or unrecognized origin

Usage:
  python discover_prs.py [--dry-run]

Output: JSON array of PR objects to stdout.
"""

import json
import re
import subprocess
import sys


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


def run_gh(args: list[str]) -> str:
    result = subprocess.run(
        ["gh"] + args, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def fetch_open_prs() -> list[dict]:
    raw = run_gh([
        "pr", "list", "--state", "open", "--json",
        "number,title,author,headRefName,createdAt,labels,body,url",
        "--limit", "100",
    ])
    if not raw:
        return []
    return json.loads(raw)


def classify_pr(pr: dict) -> dict:
    branch = pr.get("headRefName", "")
    body = pr.get("body", "") or ""
    title = pr.get("title", "")
    labels = [l.get("name", "").lower() for l in pr.get("labels", [])]
    author = pr.get("author", {}).get("login", "")

    # OpenSpec detection
    change_id = None
    if branch.startswith("openspec/"):
        change_id = branch.removeprefix("openspec/")
        return {"origin": "openspec", "change_id": change_id}

    match = re.search(r"Implements OpenSpec:\s*`?([a-z0-9-]+)`?", body)
    if match:
        return {"origin": "openspec", "change_id": match.group(1)}

    # Jules automation detection
    for jules_type, patterns in JULES_PATTERNS.items():
        if any(l in labels for l in patterns["labels"]):
            return {"origin": jules_type, "change_id": None}
        if any(tok in branch.lower() for tok in patterns["branch"]):
            return {"origin": jules_type, "change_id": None}
        if any(re.search(p, title, re.IGNORECASE) for p in patterns["title"]):
            return {"origin": jules_type, "change_id": None}

    # Codex detection
    if "codex" in author.lower() or "codex" in branch.lower():
        return {"origin": "codex", "change_id": None}

    return {"origin": "other", "change_id": None}


def discover() -> list[dict]:
    prs = fetch_open_prs()
    results = []
    for pr in prs:
        classification = classify_pr(pr)
        results.append({
            "number": pr["number"],
            "title": pr["title"],
            "author": pr.get("author", {}).get("login", "unknown"),
            "branch": pr.get("headRefName", ""),
            "created_at": pr.get("createdAt", ""),
            "labels": [l.get("name", "") for l in pr.get("labels", [])],
            "url": pr.get("url", ""),
            "origin": classification["origin"],
            "change_id": classification.get("change_id"),
        })
    return results


def main():
    dry_run = "--dry-run" in sys.argv
    results = discover()
    if not results:
        print(json.dumps([], indent=2))
        if dry_run:
            print("# Dry-run: No open PRs found.", file=sys.stderr)
        return
    print(json.dumps(results, indent=2))
    if dry_run:
        print(f"# Dry-run: Found {len(results)} open PR(s).", file=sys.stderr)


if __name__ == "__main__":
    main()

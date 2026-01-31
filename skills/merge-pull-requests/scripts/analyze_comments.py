#!/usr/bin/env python3
"""Fetch and summarize unresolved review comments for a pull request.

Usage:
  python analyze_comments.py <pr_number> [--dry-run]

Output: JSON object with comment threads to stdout.
"""

import json
import subprocess
import sys


def run_gh(args: list[str]) -> str:
    result = subprocess.run(
        ["gh"] + args, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def get_review_comments(pr_number: int) -> list[dict]:
    """Fetch review comments via gh api (includes thread/resolution info)."""
    raw = run_gh([
        "api", f"repos/{{owner}}/{{repo}}/pulls/{pr_number}/comments",
        "--paginate",
    ])
    if not raw:
        return []
    return json.loads(raw)


def get_reviews(pr_number: int) -> list[dict]:
    """Fetch top-level reviews (APPROVED, CHANGES_REQUESTED, etc.)."""
    raw = run_gh([
        "pr", "view", str(pr_number), "--json", "reviews",
    ])
    data = json.loads(raw)
    return data.get("reviews", [])


def group_into_threads(comments: list[dict]) -> list[dict]:
    """Group comments into threads by in_reply_to_id."""
    threads: dict[int, list[dict]] = {}
    root_map: dict[int, int] = {}

    for c in comments:
        cid = c["id"]
        reply_to = c.get("in_reply_to_id")

        if reply_to and reply_to in root_map:
            root = root_map[reply_to]
            root_map[cid] = root
            threads[root].append(c)
        elif reply_to and reply_to in threads:
            root_map[cid] = reply_to
            threads[reply_to].append(c)
        else:
            root_map[cid] = cid
            threads[cid] = [c]

    result = []
    for root_id, thread_comments in threads.items():
        first = thread_comments[0]
        result.append({
            "thread_id": root_id,
            "file": first.get("path", "unknown"),
            "line": first.get("original_line") or first.get("line"),
            "reviewer": first.get("user", {}).get("login", "unknown"),
            "comment_count": len(thread_comments),
            "first_comment": first.get("body", "")[:200],
            "last_comment": thread_comments[-1].get("body", "")[:200],
            "created_at": first.get("created_at", ""),
            "updated_at": thread_comments[-1].get("updated_at", ""),
        })

    return result


def analyze(pr_number: int) -> dict:
    comments = get_review_comments(pr_number)
    reviews = get_reviews(pr_number)

    threads = group_into_threads(comments)

    # Summarize review state
    review_states = {}
    for r in reviews:
        reviewer = r.get("author", {}).get("login", "unknown")
        state = r.get("state", "")
        # Keep the latest review per reviewer
        review_states[reviewer] = state

    return {
        "pr_number": pr_number,
        "total_comments": len(comments),
        "thread_count": len(threads),
        "threads": threads,
        "reviews": [
            {"reviewer": k, "state": v}
            for k, v in review_states.items()
        ],
        "has_unresolved": len(threads) > 0,
    }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = sys.argv[1:]

    if not args:
        print("Usage: analyze_comments.py <pr_number> [--dry-run]",
              file=sys.stderr)
        sys.exit(1)

    pr_number = int(args[0])
    dry_run = "--dry-run" in flags

    result = analyze(pr_number)

    if dry_run:
        result["dry_run"] = True
        print(
            f"# Dry-run: PR #{pr_number} has {result['thread_count']} comment thread(s).",
            file=sys.stderr,
        )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Fetch and summarize review comments for a pull request.

Uses the GraphQL API to get thread resolution status, which the REST API
does not expose.

Usage:
  python analyze_comments.py <pr_number> [--dry-run]

Output: JSON object with comment threads to stdout.
"""

import argparse
import json
import sys

from shared import check_gh, run_gh, safe_author

REVIEW_THREADS_QUERY = """
query($owner: String!, $repo: String!, $pr: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          comments(first: 50) {
            nodes {
              author { login }
              body
              createdAt
              updatedAt
            }
          }
        }
      }
    }
  }
}
"""


def get_repo_owner_name() -> tuple[str, str]:
    """Get owner and repo name from gh."""
    try:
        raw = run_gh(["repo", "view", "--json", "owner,name"])
    except RuntimeError as e:
        print(
            f"Error: Cannot determine repo owner/name. "
            f"Are you inside a git repo with a GitHub remote? ({e})",
            file=sys.stderr,
        )
        sys.exit(1)
    data = json.loads(raw)
    return data["owner"]["login"], data["name"]


def get_review_threads(pr_number: int) -> list[dict]:
    """Fetch review threads with resolution status via GraphQL."""
    owner, repo = get_repo_owner_name()
    all_threads = []
    cursor = None

    while True:
        gql_args = [
            "api", "graphql",
            "-F", f"owner={owner}",
            "-F", f"repo={repo}",
            "-F", f"pr={pr_number}",
            "-f", f"query={REVIEW_THREADS_QUERY}",
        ]
        if cursor:
            gql_args.extend(["-F", f"cursor={cursor}"])
        else:
            gql_args.extend(["-F", "cursor=null"])

        try:
            raw = run_gh(gql_args)
        except RuntimeError as e:
            stderr_msg = str(e).lower()
            if "scope" in stderr_msg or "permission" in stderr_msg:
                print(
                    "Error: GraphQL query failed — your gh token may lack "
                    "required scopes. Ensure 'read:discussion' scope is "
                    "granted. Run 'gh auth refresh -s read:discussion'.",
                    file=sys.stderr,
                )
            else:
                print(f"Error: GraphQL query failed: {e}", file=sys.stderr)
            sys.exit(1)

        data = json.loads(raw)

        # Handle GraphQL-level errors
        if "errors" in data:
            error_msgs = [e.get("message", "") for e in data["errors"]]
            print(
                f"Error: GraphQL returned errors: {'; '.join(error_msgs)}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Handle nonexistent PR (pullRequest is null)
        repo_data = data.get("data", {}).get("repository")
        if repo_data is None:
            print(
                f"Error: Repository {owner}/{repo} not found or inaccessible.",
                file=sys.stderr,
            )
            sys.exit(1)

        pr_data = repo_data.get("pullRequest")
        if pr_data is None:
            print(
                f"Error: PR #{pr_number} not found in {owner}/{repo}.",
                file=sys.stderr,
            )
            sys.exit(1)

        threads_data = pr_data.get("reviewThreads")
        if threads_data is None:
            break

        all_threads.extend(threads_data.get("nodes", []))

        page_info = threads_data.get("pageInfo", {})
        if page_info.get("hasNextPage"):
            cursor = page_info["endCursor"]
        else:
            break

    return all_threads


def get_reviews(pr_number: int) -> tuple[list[dict], str | None]:
    """Fetch top-level reviews (APPROVED, CHANGES_REQUESTED, etc.).

    Returns (reviews, warning). Warning is set if the fetch failed.
    """
    try:
        raw = run_gh(["pr", "view", str(pr_number), "--json", "reviews"])
    except RuntimeError as e:
        warning = f"Could not fetch reviews for PR #{pr_number}: {e}"
        print(f"Warning: {warning}", file=sys.stderr)
        return [], warning
    data = json.loads(raw)
    return data.get("reviews", []), None


def format_threads(raw_threads: list[dict]) -> list[dict]:
    """Convert GraphQL thread data into summary format."""
    result = []
    for thread in raw_threads:
        comments = thread.get("comments", {}).get("nodes", [])
        if not comments:
            continue
        first = comments[0]
        last = comments[-1]
        first_body = first.get("body", "")
        last_body = last.get("body", "")
        first_comment = first_body[:200] + ("…" if len(first_body) > 200 else "")
        last_comment = last_body[:200] + ("…" if len(last_body) > 200 else "")
        result.append({
            "thread_id": thread["id"],
            "file": thread.get("path", "unknown"),
            "line": thread.get("line"),
            "is_resolved": thread.get("isResolved", False),
            "is_outdated": thread.get("isOutdated", False),
            "reviewer": safe_author(first),
            "comment_count": len(comments),
            "first_comment": first_comment,
            "last_comment": last_comment,
            "created_at": first.get("createdAt", ""),
            "updated_at": last.get("updatedAt", ""),
        })
    return result


def analyze(pr_number: int) -> dict:
    raw_threads = get_review_threads(pr_number)
    reviews, review_warning = get_reviews(pr_number)
    threads = format_threads(raw_threads)

    warnings = []
    if review_warning:
        warnings.append(review_warning)

    unresolved = [t for t in threads if not t["is_resolved"]]
    resolved = [t for t in threads if t["is_resolved"]]
    outdated = [t for t in threads if t["is_outdated"]]

    # Summarize review state — keep latest per reviewer
    review_states = {}
    for r in reviews:
        reviewer = safe_author(r)
        state = r.get("state", "")
        review_states[reviewer] = state

    result = {
        "pr_number": pr_number,
        "total_threads": len(threads),
        "unresolved_count": len(unresolved),
        "resolved_count": len(resolved),
        "outdated_count": len(outdated),
        "threads": threads,
        "unresolved_threads": unresolved,
        "reviews": [
            {"reviewer": k, "state": v}
            for k, v in review_states.items()
        ],
        "has_unresolved": len(unresolved) > 0,
    }
    if warnings:
        result["warnings"] = warnings
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Fetch and summarize review comments for a pull request.",
    )
    parser.add_argument("pr_number", type=int, help="PR number to analyze")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no mutations")
    args = parser.parse_args()

    check_gh()

    result = analyze(args.pr_number)

    if args.dry_run:
        result["dry_run"] = True
        print(
            f"# Dry-run: PR #{args.pr_number} has {result['unresolved_count']} "
            f"unresolved / {result['resolved_count']} resolved thread(s).",
            file=sys.stderr,
        )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

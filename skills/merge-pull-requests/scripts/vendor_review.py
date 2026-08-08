#!/usr/bin/env python3
"""Conditional multi-vendor review for pull requests.

Dispatches vendor-diverse reviews for PRs that warrant deeper analysis
(large changes, no existing reviews) and synthesizes a consensus report.
Skips review for small changes, bot PRs, and PRs with existing reviews.

Usage:
  python vendor_review.py <pr_number> --origin <origin> [--reviews-json <path>]
                          [--dry-run] [--timeout <seconds>]

Output: JSON result to stdout with review findings or skip reason.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _helpers import capture_head, check_gh, run_gh, verify_and_restore_head

# ---------------------------------------------------------------------------
# Thresholds — PRs below these are "small" and skip vendor review
# ---------------------------------------------------------------------------

SMALL_PR_MAX_CHANGED_LINES = 50
SMALL_PR_MAX_FILES = 3
DEFAULT_TIMEOUT = 300

# Origins that always skip vendor review (scoped automated fixes / dep bumps)
SKIP_ORIGINS = frozenset({
    "sentinel", "bolt", "palette", "jules",
    "dependabot", "renovate",
})

# Origins that are candidates for vendor review
REVIEW_ORIGINS = frozenset({"openspec", "codex", "other"})


# ---------------------------------------------------------------------------
# PR size computation
# ---------------------------------------------------------------------------

def compute_pr_size(pr_number: int) -> dict:
    """Compute changed lines and file count from PR diff.

    Returns:
        {"additions": int, "deletions": int, "changed_lines": int,
         "changed_files": int, "files": [str]}
    """
    try:
        raw = run_gh([
            "pr", "diff", str(pr_number), "--name-only",
        ])
    except RuntimeError as e:
        print(f"Warning: Could not fetch diff file list for PR #{pr_number}: {e}",
              file=sys.stderr)
        return {"additions": 0, "deletions": 0, "changed_lines": 0,
                "changed_files": 0, "files": []}

    files = [f for f in raw.strip().splitlines() if f.strip()]
    changed_files = len(files)

    # Get line-level stats via the --stat flag
    additions = 0
    deletions = 0
    try:
        stat_raw = run_gh([
            "pr", "view", str(pr_number), "--json", "additions,deletions",
        ])
        stat_data = json.loads(stat_raw)
        additions = stat_data.get("additions", 0)
        deletions = stat_data.get("deletions", 0)
    except (RuntimeError, json.JSONDecodeError) as e:
        print(f"Warning: Could not fetch PR stats for #{pr_number}: {e}",
              file=sys.stderr)

    return {
        "additions": additions,
        "deletions": deletions,
        "changed_lines": additions + deletions,
        "changed_files": changed_files,
        "files": files,
    }


# ---------------------------------------------------------------------------
# Review eligibility
# ---------------------------------------------------------------------------

def check_review_eligibility(
    pr_number: int,
    origin: str,
    pr_size: dict,
    existing_reviews: list[dict] | None = None,
    is_draft: bool = False,
) -> dict:
    """Determine whether a PR warrants multi-vendor review.

    Returns:
        {"eligible": bool, "reason": str, "details": dict}
    """
    # Draft PRs never get reviewed
    if is_draft:
        return {
            "eligible": False,
            "reason": "draft_pr",
            "details": {"message": "Draft PRs are not reviewed"},
        }

    # Bot/automation origins always skip
    if origin in SKIP_ORIGINS:
        return {
            "eligible": False,
            "reason": "skip_origin",
            "details": {"origin": origin,
                         "message": f"Origin '{origin}' is auto-skip (scoped automation or dependency update)"},
        }

    # Small PRs skip
    changed_lines = pr_size.get("changed_lines", 0)
    changed_files = pr_size.get("changed_files", 0)
    if changed_lines <= SMALL_PR_MAX_CHANGED_LINES and changed_files <= SMALL_PR_MAX_FILES:
        return {
            "eligible": False,
            "reason": "small_pr",
            "details": {
                "changed_lines": changed_lines,
                "changed_files": changed_files,
                "threshold_lines": SMALL_PR_MAX_CHANGED_LINES,
                "threshold_files": SMALL_PR_MAX_FILES,
                "message": f"PR is small ({changed_lines} lines, {changed_files} files) — skipping review",
            },
        }

    # Check existing reviews — skip if there's a fresh approval
    if existing_reviews:
        approvals = [
            r for r in existing_reviews
            if r.get("state") == "APPROVED"
        ]
        if approvals:
            return {
                "eligible": False,
                "reason": "has_approval",
                "details": {
                    "approvals": len(approvals),
                    "reviewers": [r.get("reviewer", "unknown") for r in approvals],
                    "message": f"PR already has {len(approvals)} approval(s) — skipping review",
                },
            }
        changes_requested = [
            r for r in existing_reviews
            if r.get("state") == "CHANGES_REQUESTED"
        ]
        if changes_requested:
            return {
                "eligible": False,
                "reason": "changes_requested",
                "details": {
                    "message": "PR has unresolved change requests — vendor review deferred until addressed",
                },
            }

    # Eligible for review
    return {
        "eligible": True,
        "reason": "needs_review",
        "details": {
            "origin": origin,
            "changed_lines": changed_lines,
            "changed_files": changed_files,
            "message": f"PR qualifies for vendor review ({changed_lines} lines, {changed_files} files, origin={origin})",
        },
    }


# ---------------------------------------------------------------------------
# Review prompt construction
# ---------------------------------------------------------------------------

def build_review_prompt(pr_number: int, pr_size: dict) -> str:
    """Build a review prompt for vendor dispatch."""
    files_list = "\n".join(f"  - {f}" for f in pr_size.get("files", []))
    return f"""Review pull request #{pr_number}.

This PR modifies {pr_size['changed_files']} files with {pr_size['additions']} additions and {pr_size['deletions']} deletions.

Changed files:
{files_list}

Review checklist:
1. **Correctness**: Logic errors, edge cases, off-by-one errors
2. **Security**: Input validation, injection risks, auth/authz gaps, secrets exposure
3. **Architecture**: Follows codebase patterns, appropriate abstractions, no unnecessary coupling
4. **Performance**: Inefficient algorithms, N+1 queries, missing indexes, resource leaks
5. **Style**: Naming conventions, code organization, dead code

For each finding, output JSON conforming to this structure:
{{
  "review_type": "implementation",
  "target": "PR #{pr_number}",
  "reviewer_vendor": "<your-vendor-name>",
  "findings": [
    {{
      "id": 1,
      "type": "correctness|security|architecture|performance|style|spec_gap|contract_mismatch|observability|compatibility|resilience",
      "criticality": "low|medium|high|critical",
      "description": "What the issue is",
      "resolution": "How to fix it",
      "disposition": "fix|accept",
      "axis": "correctness|readability|architecture|security|performance",
      "severity": "critical|nit|optional|fyi|none",
      "file_path": "path/to/file",
      "line_range": {{"start": 10, "end": 20}}
    }}
  ]
}}

Output ONLY the JSON object, no additional text.
Use `gh pr diff {pr_number}` to read the actual diff before reviewing.
"""


# ---------------------------------------------------------------------------
# Dispatch reviews
# ---------------------------------------------------------------------------

def dispatch_vendor_reviews(
    pr_number: int,
    pr_size: dict,
    timeout_seconds: int = DEFAULT_TIMEOUT,
    dry_run: bool = False,
) -> dict:
    """Dispatch reviews to available vendors and synthesize consensus.

    Returns:
        {"dispatched": bool, "vendors": [...], "consensus": {...} | None,
         "error": str | None}
    """
    if dry_run:
        return {
            "dispatched": False,
            "vendors": [],
            "consensus": None,
            "error": None,
            "dry_run": True,
            "message": "Dry-run: would dispatch vendor reviews",
        }

    # Import review infrastructure — lives in parallel-infrastructure
    dispatcher_dir = (
        Path(__file__).resolve().parent.parent.parent
        / "parallel-infrastructure" / "scripts"
    )
    if not dispatcher_dir.exists():
        return {
            "dispatched": False,
            "vendors": [],
            "consensus": None,
            "error": f"Review dispatcher not found at {dispatcher_dir}",
        }

    sys.path.insert(0, str(dispatcher_dir))
    try:
        from review_dispatcher import ReviewOrchestrator, ReviewResult
        from consensus_synthesizer import (
            ConsensusSynthesizer,
            Finding,
            VendorResult,
            validate_consensus_payload,
        )
        from review_attempts import sanitize_diagnostic, validate_review_attempt_chain
        from review_result_policy import is_quorum_eligible
    except ImportError as e:
        return {
            "dispatched": False,
            "vendors": [],
            "consensus": None,
            "error": f"Could not import review infrastructure: {e}",
        }

    # Build orchestrator — try coordinator first, fall back to agents.yaml
    orch = ReviewOrchestrator.from_coordinator()
    if not orch.adapters and not orch.sdk_adapters:
        orch = ReviewOrchestrator.from_agents_yaml()

    if not orch.adapters and not orch.sdk_adapters:
        return {
            "dispatched": False,
            "vendors": [],
            "consensus": None,
            "error": "No vendor CLIs configured in coordinator or agents.yaml",
        }

    # Discover available reviewers (exclude claude since we're running as claude)
    reviewers = orch.discover_reviewers(exclude_vendor="claude_code")
    available = [r for r in reviewers if r.available]

    if not available:
        return {
            "dispatched": False,
            "vendors": [],
            "consensus": None,
            "error": "No vendor CLIs available for review dispatch",
        }

    # Build prompt and dispatch
    prompt = build_review_prompt(pr_number, pr_size)
    cwd = Path.cwd()

    # Vendor CLIs run against the shared working tree with full ambient
    # authority and have been observed checking out FETCH_HEAD, silently
    # detaching the operator's HEAD (issue #349). Snapshot HEAD before
    # dispatch and verify/restore after.
    head_before = capture_head()

    results: list[ReviewResult] = orch.dispatch_and_wait(
        review_type="implementation",
        dispatch_mode="review",
        prompt=prompt,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        exclude_vendor="claude_code",
    )

    head_guard = verify_and_restore_head(head_before)
    if head_guard["drift_detected"]:
        print(
            f"WARNING: vendor review dispatch moved HEAD "
            f"({head_before['branch'] or 'detached'}@{head_before['sha'][:8]} -> "
            f"{head_guard['after']['branch'] or 'detached'}@{head_guard['after']['sha'][:8]}); "
            f"restore {'succeeded' if head_guard['restored'] else 'FAILED: ' + str(head_guard['error'])}",
            file=sys.stderr,
        )

    # Collect successful vendor results for consensus
    vendor_results: list[VendorResult] = []
    vendor_summaries = []
    seen_terminal_vendors: set[str] = set()
    for r in results:
        logical_result = {
            "logical_request_id": r.logical_request_id,
            "requested_vendor": r.requested_vendor,
            "requested_routing": r.requested_routing,
            "deadline_at": r.deadline_at,
            "budget": r.budget,
            "attempts": r.attempts,
            "terminal_outcome": r.terminal_outcome,
            "terminal_vendor": r.terminal_vendor,
            "quorum_eligible": r.quorum_eligible,
        }
        valid_chain = False
        if r.attempts:
            try:
                validate_review_attempt_chain(logical_result)
                valid_chain = True
            except (TypeError, ValueError):
                pass
        eligible = valid_chain and is_quorum_eligible(logical_result)
        terminal_vendor = r.terminal_vendor if isinstance(r.terminal_vendor, str) else r.vendor
        distinct_eligible = eligible and terminal_vendor not in seen_terminal_vendors
        if distinct_eligible:
            seen_terminal_vendors.add(terminal_vendor)
        sanitized_error, _error_truncated = sanitize_diagnostic(r.error)
        summary = {
            "vendor": r.vendor,
            "success": distinct_eligible,
            "model_used": r.model_used,
            "elapsed_seconds": r.elapsed_seconds,
            "error": sanitized_error,
            "findings_count": len(r.findings.get("findings", [])) if r.findings else 0,
            "logical_request_id": r.logical_request_id if valid_chain else None,
            "requested_vendor": r.requested_vendor if valid_chain else None,
            "requested_routing": dict(r.requested_routing or {}) if valid_chain else {},
            "attempts": list(r.attempts) if valid_chain else [],
            "terminal_outcome": r.terminal_outcome if valid_chain else None,
            "terminal_vendor": r.terminal_vendor if valid_chain else None,
            "quorum_eligible": eligible,
        }
        vendor_summaries.append(summary)

        if distinct_eligible and r.findings is not None:
            findings = [
                Finding.from_dict(f, vendor=terminal_vendor)
                for f in r.findings.get("findings", [])
            ]
            vendor_results.append(VendorResult(
                vendor=terminal_vendor,
                findings=findings,
                elapsed_seconds=r.elapsed_seconds,
                logical_result=logical_result,
            ))

    # Synthesize consensus if we have results
    consensus_dict = None
    if vendor_results:
        synth = ConsensusSynthesizer(quorum=1)  # quorum=1 since single vendor is acceptable for PR review
        report = synth.synthesize(
            review_type="implementation",
            target=f"PR #{pr_number}",
            vendor_results=vendor_results,
        )
        consensus_dict = synth.to_dict(report)
        validate_consensus_payload(consensus_dict)

    return {
        "dispatched": True,
        "vendors": vendor_summaries,
        "consensus": consensus_dict,
        "head_guard": head_guard,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Conditional multi-vendor review for pull requests.",
    )
    parser.add_argument("pr_number", type=int, help="PR number to review")
    parser.add_argument("--origin", required=True,
                        help="PR origin classification (openspec, codex, other, etc.)")
    parser.add_argument("--reviews-json",
                        help="Path to JSON file with existing review data from analyze_comments.py")
    parser.add_argument("--is-draft", action="store_true",
                        help="Whether the PR is a draft")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report eligibility without dispatching reviews")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"Per-vendor timeout in seconds (default: {DEFAULT_TIMEOUT})")
    args = parser.parse_args()

    check_gh()

    # Compute PR size
    pr_size = compute_pr_size(args.pr_number)

    # Load existing reviews if provided
    existing_reviews = None
    if args.reviews_json:
        try:
            data = json.loads(Path(args.reviews_json).read_text())
            existing_reviews = data.get("reviews", [])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Warning: Could not load reviews from {args.reviews_json}: {e}",
                  file=sys.stderr)

    # Check eligibility
    eligibility = check_review_eligibility(
        pr_number=args.pr_number,
        origin=args.origin,
        pr_size=pr_size,
        existing_reviews=existing_reviews,
        is_draft=args.is_draft,
    )

    result = {
        "pr_number": args.pr_number,
        "origin": args.origin,
        "pr_size": {
            "additions": pr_size["additions"],
            "deletions": pr_size["deletions"],
            "changed_lines": pr_size["changed_lines"],
            "changed_files": pr_size["changed_files"],
        },
        "eligibility": eligibility,
    }

    if not eligibility["eligible"]:
        # Not eligible — output result and exit
        print(json.dumps(result, indent=2))
        if args.dry_run:
            print(
                f"# Dry-run: PR #{args.pr_number} skipped for vendor review — "
                f"{eligibility['reason']}: {eligibility['details']['message']}",
                file=sys.stderr,
            )
        return 0

    # Eligible — dispatch vendor reviews
    review_result = dispatch_vendor_reviews(
        pr_number=args.pr_number,
        pr_size=pr_size,
        timeout_seconds=args.timeout,
        dry_run=args.dry_run,
    )
    result["review"] = review_result

    print(json.dumps(result, indent=2))

    if args.dry_run:
        print(
            f"# Dry-run: PR #{args.pr_number} eligible for vendor review — "
            f"{eligibility['details']['message']}",
            file=sys.stderr,
        )
        return 0

    # Summary to stderr
    if review_result.get("dispatched"):
        succeeded = sum(1 for v in review_result.get("vendors", []) if v["success"])
        total = len(review_result.get("vendors", []))
        consensus = review_result.get("consensus")
        if consensus:
            summary = consensus.get("summary", {})
            print(
                f"# Vendor review: {succeeded}/{total} vendors, "
                f"{summary.get('total_unique_findings', 0)} findings "
                f"({summary.get('confirmed_count', 0)} confirmed, "
                f"{summary.get('blocking_count', 0)} blocking)",
                file=sys.stderr,
            )
        else:
            print(
                f"# Vendor review: {succeeded}/{total} vendors — no findings produced",
                file=sys.stderr,
            )
    elif review_result.get("error"):
        print(
            f"# Vendor review failed: {review_result['error']}",
            file=sys.stderr,
        )

    # Fail loudly when a vendor CLI mutated the checkout, even if HEAD was
    # restored — the operator must know the shared tree was touched.
    head_guard = review_result.get("head_guard")
    if head_guard and head_guard.get("drift_detected"):
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

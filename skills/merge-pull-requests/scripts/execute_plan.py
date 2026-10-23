#!/usr/bin/env python3
"""Execute one PR node from a durable merge plan."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def canonical_scripts_dir(source_file: Path | None = None) -> Path:
    """Resolve helpers from canonical ``skills/`` even when run via a mirror."""

    current = (source_file or Path(__file__)).resolve()
    for ancestor in (current.parent, *current.parents):
        if not (ancestor / ".git").exists():
            continue
        candidate = ancestor / "skills" / "merge-pull-requests" / "scripts"
        if candidate.is_dir():
            return candidate
    raise RuntimeError(
        "repository-root canonical skills/merge-pull-requests/scripts not found",
    )


CANONICAL_SCRIPTS_DIR = canonical_scripts_dir()
if str(CANONICAL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(CANONICAL_SCRIPTS_DIR))

from _helpers import run_gh  # noqa: E402
from analyze_comments import analyze as analyze_pr_comments  # noqa: E402
from check_staleness import check_staleness as check_pr_staleness  # noqa: E402
from execution_safety import (  # noqa: E402
    POLICY_APPROVER,
    default_sync_point_guard,
    live_terminal_outcome,
    record_preclaim_blocker,
    refreshed_branch_block_reason,
    vendor_review_block_reason,
)
from merge_pr import (  # noqa: E402
    merge_pr,
    refresh_branch,
    validate_pr,
)
from plan_storage import FilePlanStore  # noqa: E402
from verdict_binding import (  # noqa: E402
    POLICY_WAIVABLE_REASONS,
    bind,
    derive_author,
    independence_violation,
    patch_id_from_diff,
    stale_reason,
    verdict_currency,
)
from vendor_review import (  # noqa: E402
    check_review_eligibility,
    compute_pr_size,
    dispatch_vendor_reviews,
)


@dataclass(frozen=True)
class ExecutionDependencies:
    guard_sync_point: Callable[[Path], dict[str, Any]]
    get_live_status: Callable[[int], dict[str, Any]]
    check_staleness: Callable[[int, str], dict[str, Any]]
    refresh_branch: Callable[[int], dict[str, Any]]
    analyze_comments: Callable[[int], dict[str, Any]]
    review_vendor: Callable[[int, str, dict[str, Any], dict[str, Any]], dict[str, Any]]
    #: ``merge(pr, strategy, expected_head_sha, review_waiver)``
    merge: Callable[[int, str, str | None, dict[str, Any] | None], dict[str, Any]]
    #: Unified diff of the PR, read from GitHub without checking the branch out.
    pr_diff: Callable[[int], str]
    #: ``{login, vendor, session_id}`` of the PR author.
    pr_author: Callable[[int], dict[str, Any]]


def _default_vendor_review(
    pr_number: int,
    origin: str,
    comments: dict[str, Any],
    author: dict[str, Any],
) -> dict[str, Any]:
    size = compute_pr_size(pr_number)
    eligibility = check_review_eligibility(
        pr_number,
        origin,
        size,
        existing_reviews=comments.get("reviews", []),
    )
    if not eligibility["eligible"]:
        return {"eligibility": eligibility, "consensus": None}
    try:
        result = dispatch_vendor_reviews(
            pr_number=pr_number,
            pr_size=size,
            author_vendor=(author or {}).get("vendor"),
        )
    except Exception as exc:  # noqa: BLE001 - boundary must fail closed
        return {
            "eligibility": eligibility,
            "dispatched": False,
            "vendors": [],
            "consensus": None,
            "error": f"vendor review dispatch raised {type(exc).__name__}: {exc}",
        }
    result["eligibility"] = eligibility
    return result


def _default_pr_diff(pr_number: int) -> str:
    return run_gh(["pr", "diff", str(pr_number)])


def _default_pr_author(pr_number: int) -> dict[str, Any]:
    view = json.loads(run_gh(["pr", "view", str(pr_number), "--json", "author,commits"]))
    return derive_author(view)


DEFAULT_DEPENDENCIES = ExecutionDependencies(
    guard_sync_point=default_sync_point_guard,
    get_live_status=validate_pr,
    check_staleness=check_pr_staleness,
    refresh_branch=refresh_branch,
    analyze_comments=analyze_pr_comments,
    review_vendor=_default_vendor_review,
    merge=lambda pr_number, strategy, head_sha, review_waiver: merge_pr(
        pr_number,
        strategy,
        expected_head_sha=head_sha,
        review_waiver=review_waiver,
    ),
    pr_diff=_default_pr_diff,
    pr_author=_default_pr_author,
)

CHEAP_PATH_REASON = "automation_cheap_path"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ineligible_reason(review: Any) -> str | None:
    eligibility = review.get("eligibility") if isinstance(review, dict) else None
    if isinstance(eligibility, dict) and not eligibility.get("eligible"):
        return eligibility.get("reason")
    return None


def _policy_waiver(eligibility_reason: str, reason: str) -> dict[str, Any]:
    return {
        "reason": reason,
        "source": "policy",
        "approver": POLICY_APPROVER,
        "recorded_at": _now(),
        "eligibility_reason": eligibility_reason,
    }


def _operator_waiver(reason: str, approver: str | None, review: Any) -> dict[str, Any]:
    return {
        "reason": reason.strip(),
        "source": "operator",
        "approver": (approver or "").strip() or "operator",
        "recorded_at": _now(),
        "eligibility_reason": _ineligible_reason(review),
    }


def _find_node(plan: dict[str, Any], pr_number: int) -> dict[str, Any]:
    node = next(
        (candidate for candidate in plan["nodes"] if candidate["pr"] == pr_number),
        None,
    )
    if node is None:
        raise KeyError(f"PR #{pr_number} is not present in the merge plan")
    return node


def _ci_state(live: dict[str, Any]) -> str:
    if live.get("checks_failed"):
        return "blocked"
    if live.get("checks_pending"):
        return "unstable"
    if live.get("checks_passing"):
        return "clean"
    return "unknown"


def _security_failures(live: dict[str, Any]) -> list[str]:
    security_markers = (
        "security",
        "codeql",
        "secret",
        "dependency review",
        "trivy",
        "bandit",
    )
    passing = {"SUCCESS", "NEUTRAL", "SKIPPED"}
    failures = []
    for check in live.get("check_details", []) or []:
        name = str(check.get("name", "unknown"))
        state = str(check.get("state", "UNKNOWN")).upper()
        if any(marker in name.lower() for marker in security_markers) and state not in passing:
            failures.append(name)
    return failures


def _comment_summary(comments: dict[str, Any]) -> str | None:
    threads = comments.get("unresolved_threads", []) or []
    if not threads:
        return None
    summaries = []
    for thread in threads[:10]:
        location = str(thread.get("file", "unknown"))
        text = str(thread.get("first_comment") or thread.get("last_comment") or "")
        summaries.append(f"{location}: {text}".strip())
    return "; ".join(summaries)


def _mark_downstream(plan: dict[str, Any], merged_pr: int) -> list[int]:
    downstream: set[int] = set()
    frontier = [merged_pr]
    while frontier:
        dependency = frontier.pop()
        for node in plan["nodes"]:
            number = node["pr"]
            if number in downstream:
                continue
            if dependency in node["definition"]["depends_on"]:
                downstream.add(number)
                frontier.append(number)
    for node in plan["nodes"]:
        if node["pr"] in downstream and node["state"]["outcome"] == "pending":
            node["state"]["needs_revalidation"] = True
    return sorted(downstream)


def _delegation_commands(node: dict[str, Any], branch: str) -> list[str]:
    definition = node["definition"]
    pr_number = int(node["pr"])
    change_id = definition.get("change_id") or (
        branch.removeprefix("openspec/") if branch.startswith("openspec/") else f"pr-{pr_number}"
    )
    skill = definition.get("remediation_skill")
    if skill == "iterate-on-plan":
        return [f"/iterate-on-plan {change_id} --vendor-review"]
    if skill == "iterate-on-implementation":
        return [f"/iterate-on-implementation {change_id} --vendor-review"]
    return [f'/quick-task "Address unresolved review comments on PR #{pr_number}"']


def _review_evidence(
    review: dict[str, Any],
    waiver: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact, operator-readable record of the vendor review a result acted on.

    The full verdict is persisted in ``state["vendor_verdict"]``; this copy rides
    on the result so a merge through an eligible review is visible without
    opening the plan file (PR #484 merged with 23 unconfirmed findings while the
    result said only ``merged``). Vendor errors are clipped: a billing error can
    carry a whole JSON body. ``binding`` says which head the verdict describes,
    and ``review_waiver`` says who let a merge through without one.
    """
    consensus = review.get("consensus")
    summary = consensus.get("summary") if isinstance(consensus, dict) else None
    vendors = []
    for vendor in review.get("vendors") or []:
        if not isinstance(vendor, dict):
            continue
        error = vendor.get("error")
        vendors.append({
            "vendor": vendor.get("vendor"),
            "success": vendor.get("success"),
            "findings_count": vendor.get("findings_count"),
            "error": str(error)[:200] if error else None,
        })
    return {
        "eligible": (review.get("eligibility") or {}).get("eligible"),
        "skipped": bool(review.get("skipped")),
        "error": review.get("error"),
        "vendors": vendors,
        "summary": summary,
        "workspace_guard": review.get("workspace_guard"),
        "binding": review.get("binding"),
        "reused_stored_verdict": bool(review.get("reused_stored_verdict")),
        "superseded_verdict": review.get("superseded_verdict"),
        "review_waiver": waiver,
    }


def _persist_pending(
    store: FilePlanStore,
    plan: dict[str, Any],
    state: dict[str, Any],
    reason: str,
) -> None:
    state["outcome"] = "pending"
    state["claimed_by"] = None
    state["blocking_reason"] = reason
    store.save(plan)


def _reconcile_terminal(
    store: FilePlanStore,
    plan: dict[str, Any],
    state: dict[str, Any],
    pr_number: int,
    outcome: str,
) -> dict[str, Any]:
    state["outcome"] = outcome
    state["claimed_by"] = None
    state["blocking_reason"] = None
    downstream = _mark_downstream(plan, pr_number) if outcome == "merged" else []
    store.save(plan)
    return {
        "action": "reconciled",
        "outcome": outcome,
        "pr": pr_number,
        "downstream_revalidation": downstream,
    }


def execute_node(
    plan_path: Path,
    pr_number: int,
    *,
    approve_gate: bool = False,
    proposal_accepted: bool = False,
    claim_id: str | None = None,
    store: FilePlanStore | None = None,
    dependencies: ExecutionDependencies = DEFAULT_DEPENDENCIES,
    waive_review: str | None = None,
    waiver_approver: str | None = None,
) -> dict[str, Any]:
    """Execute exactly one planned PR and persist every resulting state change.

    ``waive_review`` records an operator waiver: it lets the merge through
    without a bound consensus verdict, except over unresolved change requests.
    """

    if waive_review is not None and not waive_review.strip():
        raise ValueError("--waive-review needs a non-empty reason")

    store = store or FilePlanStore(plan_path)
    plan = store.load()
    node = _find_node(plan, pr_number)
    state = node["state"]
    definition = node["definition"]

    if state["outcome"] in {"merged", "closed", "deferred", "failed"}:
        return {
            "action": "already_terminal",
            "outcome": state["outcome"],
            "pr": pr_number,
        }

    execution_claim = claim_id or f"file-executor:{os.getpid()}"
    replaying = (
        state["outcome"] == "in_progress" and state.get("claimed_by") == execution_claim
    )
    if state["outcome"] == "in_progress":
        recovery_live = dependencies.get_live_status(pr_number)
        terminal = live_terminal_outcome(recovery_live)
        if terminal is not None:
            return _reconcile_terminal(store, plan, state, pr_number, terminal)
        if state.get("claimed_by") != execution_claim:
            return {
                "action": "execution_in_progress",
                "outcome": "in_progress",
                "pr": pr_number,
                "claimed_by": state.get("claimed_by"),
                "reason": "another execution claim must be reconciled before replay",
            }

    blocked_by = [
        dependency
        for dependency in definition["depends_on"]
        if _find_node(plan, dependency)["state"]["outcome"] != "merged"
    ]
    if blocked_by:
        reason = "waiting for prerequisites: " + ", ".join(f"#{number}" for number in blocked_by)
        conflict = record_preclaim_blocker(store, pr_number, reason)
        if conflict:
            return conflict
        return {
            "action": "blocked",
            "outcome": state["outcome"],
            "pr": pr_number,
            "blocked_by": blocked_by,
            "reason": reason,
        }

    plan_gates = list(definition["gates"])
    openspec_gate = node["origin"] == "openspec" or "proposal_acceptance" in plan_gates
    if openspec_gate and not proposal_accepted:
        surfaced_gates = plan_gates or ["proposal_acceptance"]
        reason = (
            "OpenSpec proposal acceptance must be completed by its approval workflow"
        )
        conflict = record_preclaim_blocker(store, pr_number, reason)
        if conflict:
            return conflict
        return {
            "action": "human_gate",
            "outcome": state["outcome"],
            "pr": pr_number,
            "gates": surfaced_gates,
            "reason": reason,
            "override_allowed": False,
        }
    if (not node["auto_executable"] or plan_gates) and not approve_gate and not proposal_accepted:
        surfaced_gates = plan_gates or ["requires_human_approval"]
        reason = (
            "OpenSpec proposal acceptance must be completed by its approval workflow"
            if openspec_gate
            else "explicit operator approval required"
        )
        conflict = record_preclaim_blocker(store, pr_number, reason)
        if conflict:
            return conflict
        return {
            "action": "human_gate",
            "outcome": state["outcome"],
            "pr": pr_number,
            "gates": surfaced_gates,
            "reason": reason,
            "override_allowed": not openspec_gate,
        }

    guard = dependencies.guard_sync_point(CANONICAL_SCRIPTS_DIR.parents[2])
    if guard.get("allowed") is not True:
        reason = str(guard.get("reason") or "sync-point guard did not allow execution")
        conflict = record_preclaim_blocker(store, pr_number, reason)
        if conflict:
            return conflict
        return {
            "action": "sync_point_blocked",
            "outcome": state["outcome"],
            "pr": pr_number,
            "reason": reason,
            "guard": guard,
        }

    live = dependencies.get_live_status(pr_number)
    terminal = live_terminal_outcome(live)
    if terminal is not None:
        return _reconcile_terminal(store, plan, state, pr_number, terminal)

    plan, acquired = store.claim_node(pr_number, execution_claim)
    node = _find_node(plan, pr_number)
    state = node["state"]
    definition = node["definition"]
    if not acquired:
        if state["outcome"] in {"merged", "closed", "deferred", "failed"}:
            return {
                "action": "already_terminal",
                "outcome": state["outcome"],
                "pr": pr_number,
            }
        return {
            "action": "execution_in_progress",
            "outcome": state["outcome"],
            "pr": pr_number,
            "claimed_by": state.get("claimed_by"),
            "reason": "another execution claim must be reconciled before replay",
        }

    state["ci_state"] = _ci_state(live)
    try:
        staleness = dependencies.check_staleness(pr_number, node["origin"])
    except Exception as exc:  # noqa: BLE001 - live safety signal must fail closed
        reason = f"live staleness check failed: {type(exc).__name__}: {exc}"
        _persist_pending(store, plan, state, reason)
        return {"action": "staleness_gate", "outcome": "pending", "pr": pr_number, "reason": reason}
    state["staleness"] = str(staleness.get("staleness", "unknown"))
    if state["staleness"] == "obsolete":
        reason = str(staleness.get("summary") or "live staleness check marked PR obsolete")
        _persist_pending(store, plan, state, reason)
        return {"action": "staleness_gate", "outcome": "pending", "pr": pr_number, "reason": reason}
    if state["staleness"] == "unknown":
        reason = "live staleness could not be determined"
        _persist_pending(store, plan, state, reason)
        return {"action": "staleness_gate", "outcome": "pending", "pr": pr_number, "reason": reason}

    needs_refresh = state.get("needs_revalidation", False) or state["staleness"] == "stale"
    if needs_refresh:
        refreshed = dependencies.refresh_branch(pr_number)
        if not refreshed.get("success"):
            reason = str(
                refreshed.get("reason") or refreshed.get("error") or "branch refresh failed"
            )
            _persist_pending(store, plan, state, reason)
            return {
                "action": "revalidation_failed",
                "outcome": "pending",
                "pr": pr_number,
                "reason": reason,
            }
        live = dependencies.get_live_status(pr_number)
        terminal = live_terminal_outcome(live)
        if terminal is not None:
            return _reconcile_terminal(store, plan, state, pr_number, terminal)
        state["ci_state"] = _ci_state(live)
        refreshed_staleness = dependencies.check_staleness(pr_number, node["origin"])
        state["staleness"] = str(refreshed_staleness.get("staleness", "unknown"))
        refresh_reason = refreshed_branch_block_reason(
            refreshed_staleness,
            live,
            state["ci_state"],
        )
        if refresh_reason:
            reason = refresh_reason
            _persist_pending(store, plan, state, reason)
            return {
                "action": "revalidation_failed",
                "outcome": "pending",
                "pr": pr_number,
                "reason": reason,
            }
        state["needs_revalidation"] = False

    security_failures = _security_failures(live)
    if security_failures:
        reason = "failing required security check(s): " + ", ".join(security_failures)
        _persist_pending(store, plan, state, reason)
        return {
            "action": "security_gate",
            "outcome": "pending",
            "pr": pr_number,
            "reason": reason,
        }

    if live.get("can_merge") is not True:
        reason = "live PR state is not currently mergeable"
        _persist_pending(store, plan, state, reason)
        return {
            "action": "live_state_gate",
            "outcome": "pending",
            "pr": pr_number,
            "reason": reason,
            "live": live,
        }

    comments = dependencies.analyze_comments(pr_number)
    state["unresolved_comments"] = int(comments.get("unresolved_count", 0))
    state["unresolved_comment_summary"] = _comment_summary(comments)
    if state["unresolved_comments"]:
        reason = f"{state['unresolved_comments']} unresolved review comment(s)"
        _persist_pending(store, plan, state, reason)
        return {
            "action": "delegate_comments",
            "outcome": "pending",
            "pr": pr_number,
            "reason": reason,
            "delegation": _delegation_commands(node, str(live.get("branch", ""))),
        }

    live_head = live.get("head_sha") or None
    if not live_head:
        reason = "live head SHA could not be determined"
        _persist_pending(store, plan, state, reason)
        return {"action": "live_state_gate", "outcome": "pending", "pr": pr_number, "reason": reason}

    patch_ids: dict[str, str | None] = {}

    def live_patch_id() -> str | None:
        if "live" not in patch_ids:
            try:
                patch_ids["live"] = patch_id_from_diff(dependencies.pr_diff(pr_number))
            except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
                patch_ids["live"] = None
        return patch_ids["live"]

    waiver: dict[str, Any] | None = None
    review_patch_id: str | None = None
    cheap_path = (
        definition.get("kind") == "automation"
        or definition.get("remediation_skill") == "none"
    )
    if cheap_path:
        review = bind(
            {
                "eligibility": {"eligible": False, "reason": CHEAP_PATH_REASON},
                "consensus": None,
                "skipped": True,
            },
            head_sha=live_head,
            patch_id=None,
            author=None,
        )
        waiver = _policy_waiver(
            CHEAP_PATH_REASON,
            "automation cheap path: green CI, no unresolved comments",
        )
    else:
        try:
            author = dependencies.pr_author(pr_number)
        except Exception as exc:  # noqa: BLE001 - independence must be shown
            reason = f"PR author could not be determined: {type(exc).__name__}: {exc}"
            _persist_pending(store, plan, state, reason)
            return {"action": "vendor_review_gate", "outcome": "pending", "pr": pr_number, "reason": reason}

        review = None
        superseded: str | None = None
        stored = state.get("vendor_verdict")
        binding = stored.get("binding") if isinstance(stored, dict) else None
        if isinstance(binding, dict):
            stored_pid = None if binding.get("head_sha") == live_head else live_patch_id()
            if verdict_currency(binding, live_head, stored_pid) == "stale":
                superseded = stale_reason(binding, live_head)
            elif (
                vendor_review_block_reason(
                    stored, live_head_sha=live_head, live_patch_id=stored_pid,
                ) is None
                and independence_violation({**binding, "author": author}) is None
            ):
                review = dict(stored)
                review["reused_stored_verdict"] = True
                review_patch_id = stored_pid

        if review is None:
            try:
                fresh = dependencies.review_vendor(pr_number, node["origin"], comments, author)
            except Exception as exc:  # noqa: BLE001 - dispatch failures block
                fresh = {
                    "eligibility": {"eligible": True, "reason": "review_required"},
                    "dispatched": False,
                    "vendors": [],
                    "consensus": None,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            if not isinstance(fresh, dict):
                fresh = {"eligibility": None, "consensus": None}
            if superseded:
                fresh["superseded_verdict"] = superseded
            review = bind(fresh, head_sha=live_head, patch_id=live_patch_id(), author=author)
            ineligible = _ineligible_reason(review)
            if ineligible in POLICY_WAIVABLE_REASONS:
                waiver = _policy_waiver(
                    ineligible, f"vendor review not required by policy ({ineligible})",
                )

    if waive_review is not None:
        waiver = _operator_waiver(waive_review, waiver_approver, review)
    elif replaying:
        stored_waiver = state.get("review_waiver")
        if isinstance(stored_waiver, dict) and stored_waiver.get("source") == "operator":
            waiver = stored_waiver

    state["vendor_verdict"] = review
    state["review_waiver"] = waiver
    vendor_reason = vendor_review_block_reason(
        review,
        waiver=waiver,
        live_head_sha=live_head,
        live_patch_id=review_patch_id,
    )
    if vendor_reason:
        _persist_pending(store, plan, state, vendor_reason)
        return {
            "action": "vendor_review_gate",
            "outcome": "pending",
            "pr": pr_number,
            "reason": vendor_reason,
            "vendor_review": _review_evidence(review, waiver),
        }

    result = dependencies.merge(pr_number, node["strategy"], live_head, waiver)
    if not result.get("success"):
        live_after_failure = dependencies.get_live_status(pr_number)
        terminal = live_terminal_outcome(live_after_failure)
        if terminal is not None:
            return _reconcile_terminal(store, plan, state, pr_number, terminal)
        if result.get("head_mismatch"):
            reason = (
                f"head mismatch: the PR head moved after the review check "
                f"(merge pinned to {live_head[:7]})"
            )
        else:
            reason = str(result.get("reason") or result.get("error") or "merge failed")
        _persist_pending(store, plan, state, reason)
        return {
            "action": "merge_failed",
            "outcome": "pending",
            "pr": pr_number,
            "reason": reason,
            "merge": result,
        }

    state["outcome"] = "merged"
    state["claimed_by"] = None
    state["blocking_reason"] = None
    plan["last_merged_pr"] = pr_number
    plan["compact_requested"] = True
    downstream = _mark_downstream(plan, pr_number)
    store.save(plan)
    return {
        "action": "merged",
        "outcome": "merged",
        "pr": pr_number,
        "downstream_revalidation": downstream,
        "compact_requested": True,
        "merge": result,
        "vendor_review": _review_evidence(review, waiver),
    }


def _operator_identity() -> str:
    """Who recorded an operator waiver: the login user, else the git identity."""

    user = (os.environ.get("USER") or "").strip()
    if user:
        return user
    try:
        email = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True, text=True, check=False,
        ).stdout.strip()
    except OSError:
        email = ""
    return email or "operator"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", required=True, type=Path, metavar="PLAN")
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument(
        "--approve-gate",
        action="store_true",
        help="Record explicit operator approval for this node's human gates",
    )
    parser.add_argument(
        "--claim-id",
        help="Stable execution claim id; reuse it only to resume the same attempt",
    )
    parser.add_argument(
        "--proposal-accepted",
        action="store_true",
        help="Record that the dedicated OpenSpec proposal-acceptance workflow completed",
    )
    parser.add_argument(
        "--waive-review",
        metavar="REASON",
        help=(
            "Record an operator review waiver with this reason; the merge may then "
            "proceed without a bound vendor verdict (never over change requests)"
        ),
    )
    args = parser.parse_args()
    if args.waive_review is not None and not args.waive_review.strip():
        parser.error("--waive-review needs a non-empty reason")

    result = execute_node(
        args.execute,
        args.pr,
        approve_gate=args.approve_gate,
        proposal_accepted=args.proposal_accepted,
        claim_id=args.claim_id,
        dependencies=DEFAULT_DEPENDENCIES,
        waive_review=args.waive_review,
        waiver_approver=_operator_identity() if args.waive_review is not None else None,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["outcome"] == "merged" else 2


if __name__ == "__main__":
    raise SystemExit(main())

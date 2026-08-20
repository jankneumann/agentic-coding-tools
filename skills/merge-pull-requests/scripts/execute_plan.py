#!/usr/bin/env python3
"""Execute one PR node from a durable merge plan."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
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

from analyze_comments import analyze as analyze_pr_comments  # noqa: E402
from check_staleness import check_staleness as check_pr_staleness  # noqa: E402
from merge_pr import (  # noqa: E402
    merge_pr,
    refresh_branch,
    validate_pr,
)
from plan_storage import FilePlanStore  # noqa: E402
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
    review_vendor: Callable[[int, str, dict[str, Any]], dict[str, Any]]
    merge: Callable[[int, str], dict[str, Any]]


def _default_vendor_review(
    pr_number: int,
    origin: str,
    comments: dict[str, Any],
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
        result = dispatch_vendor_reviews(pr_number=pr_number, pr_size=size)
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


def _default_sync_point_guard(repo_root: Path) -> dict[str, Any]:
    """Reuse the merge skill's active-agent guard and fail closed on errors."""

    skills_root = repo_root / "skills"
    if str(skills_root) not in sys.path:
        sys.path.insert(0, str(skills_root))
    try:
        from shared.active_agents import check_no_active_agents

        clear, active = check_no_active_agents(repo_root=repo_root)
    except Exception as exc:  # noqa: BLE001 - a missing guard must block
        return {
            "allowed": False,
            "reason": f"active-agent guard unavailable: {type(exc).__name__}: {exc}",
        }
    if clear:
        return {"allowed": True, "reason": "no active agents"}
    labels = [getattr(agent, "label", str(agent)) for agent in active]
    return {
        "allowed": False,
        "reason": "active agents hold worktrees: " + ", ".join(labels),
        "active_agents": labels,
    }


DEFAULT_DEPENDENCIES = ExecutionDependencies(
    guard_sync_point=_default_sync_point_guard,
    get_live_status=validate_pr,
    check_staleness=check_pr_staleness,
    refresh_branch=refresh_branch,
    analyze_comments=analyze_pr_comments,
    review_vendor=_default_vendor_review,
    merge=lambda pr_number, strategy: merge_pr(pr_number, strategy),
)


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


def _blocking_vendor_count(review: dict[str, Any]) -> int | None:
    consensus = review.get("consensus")
    if consensus is None and isinstance(review.get("review"), dict):
        consensus = review["review"].get("consensus")
    if not isinstance(consensus, dict):
        return None
    summary = consensus.get("summary")
    if not isinstance(summary, dict) or "blocking_count" not in summary:
        return None
    try:
        return int(summary["blocking_count"])
    except (TypeError, ValueError):
        return None


def _vendor_review_block_reason(review: dict[str, Any]) -> str | None:
    eligibility = review.get("eligibility")
    if not isinstance(eligibility, dict):
        return "vendor review returned no eligibility decision"
    if not eligibility.get("eligible"):
        if eligibility.get("reason") == "changes_requested":
            return "existing review has unresolved change requests"
        return None
    if review.get("error"):
        return f"eligible vendor review failed: {review['error']}"
    if review.get("dispatched") is not True:
        return "eligible vendor review was not dispatched"
    vendors = review.get("vendors")
    if not isinstance(vendors, list) or not any(
        isinstance(vendor, dict) and vendor.get("success") for vendor in vendors
    ):
        return "eligible vendor review produced no successful reviewer result"
    blocking = _blocking_vendor_count(review)
    if blocking is None:
        return "eligible vendor review produced no consensus verdict"
    if blocking:
        return f"vendor review reported {blocking} blocking finding(s)"
    return None


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


def _delegation_commands(pr_number: int, branch: str) -> list[str]:
    change_id = branch.removeprefix("openspec/") if branch.startswith("openspec/") else f"pr-{pr_number}"
    return [
        f"/iterate-on-implementation {change_id}",
        f'/quick-task "Address unresolved review comments on PR #{pr_number}"',
    ]


def _live_terminal_outcome(live: dict[str, Any]) -> str | None:
    state = str(live.get("state") or live.get("status") or "").upper()
    if live.get("merged") is True or state == "MERGED":
        return "merged"
    if state == "CLOSED":
        return "closed"
    return None


def _repo_root() -> Path:
    return CANONICAL_SCRIPTS_DIR.parents[2]


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
    claim_id: str | None = None,
    store: FilePlanStore | None = None,
    dependencies: ExecutionDependencies = DEFAULT_DEPENDENCIES,
) -> dict[str, Any]:
    """Execute exactly one planned PR and persist every resulting state change."""

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

    blocked_by = [
        dependency
        for dependency in definition["depends_on"]
        if _find_node(plan, dependency)["state"]["outcome"] != "merged"
    ]
    if blocked_by:
        reason = "waiting for prerequisites: " + ", ".join(
            f"#{number}" for number in blocked_by
        )
        state["blocking_reason"] = reason
        store.save(plan)
        return {
            "action": "blocked",
            "outcome": state["outcome"],
            "pr": pr_number,
            "blocked_by": blocked_by,
            "reason": reason,
        }

    plan_gates = list(definition["gates"])
    openspec_gate = node["origin"] == "openspec" or "proposal_acceptance" in plan_gates
    if openspec_gate or ((not node["auto_executable"] or plan_gates) and not approve_gate):
        surfaced_gates = plan_gates or ["requires_human_approval"]
        reason = (
            "OpenSpec proposal acceptance must be completed by its approval workflow"
            if openspec_gate
            else "explicit operator approval required"
        )
        state["blocking_reason"] = reason
        store.save(plan)
        return {
            "action": "human_gate",
            "outcome": state["outcome"],
            "pr": pr_number,
            "gates": surfaced_gates,
            "reason": reason,
            "override_allowed": not openspec_gate,
        }

    guard = dependencies.guard_sync_point(_repo_root())
    if guard.get("allowed") is not True:
        reason = str(guard.get("reason") or "sync-point guard did not allow execution")
        state["blocking_reason"] = reason
        store.save(plan)
        return {
            "action": "sync_point_blocked",
            "outcome": state["outcome"],
            "pr": pr_number,
            "reason": reason,
            "guard": guard,
        }

    live = dependencies.get_live_status(pr_number)
    terminal = _live_terminal_outcome(live)
    if terminal is not None:
        return _reconcile_terminal(store, plan, state, pr_number, terminal)

    execution_claim = claim_id or f"file-executor:{os.getpid()}"
    if state["outcome"] == "in_progress" and state.get("claimed_by") != execution_claim:
        return {
            "action": "execution_in_progress",
            "outcome": "in_progress",
            "pr": pr_number,
            "claimed_by": state.get("claimed_by"),
            "reason": "another execution claim must be reconciled before replay",
        }

    # The durable claim is the crash boundary: no refresh, review dispatch, or
    # merge side effect occurs until this write succeeds.
    state["outcome"] = "in_progress"
    state["claimed_by"] = execution_claim
    state["blocking_reason"] = None
    store.save(plan)

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
            reason = str(refreshed.get("reason") or refreshed.get("error") or "branch refresh failed")
            _persist_pending(store, plan, state, reason)
            return {
                "action": "revalidation_failed",
                "outcome": "pending",
                "pr": pr_number,
                "reason": reason,
            }
        live = dependencies.get_live_status(pr_number)
        terminal = _live_terminal_outcome(live)
        if terminal is not None:
            return _reconcile_terminal(store, plan, state, pr_number, terminal)
        state["ci_state"] = _ci_state(live)
        refreshed_staleness = dependencies.check_staleness(pr_number, node["origin"])
        state["staleness"] = str(refreshed_staleness.get("staleness", "unknown"))
        if state["staleness"] != "fresh":
            reason = f"PR remains {state['staleness']} after branch refresh"
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
            "delegation": _delegation_commands(pr_number, str(live.get("branch", ""))),
        }

    try:
        review = dependencies.review_vendor(pr_number, node["origin"], comments)
    except Exception as exc:  # noqa: BLE001 - dispatch failures block
        review = {
            "eligibility": {"eligible": True, "reason": "review_required"},
            "dispatched": False,
            "vendors": [],
            "consensus": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
    state["vendor_verdict"] = review
    vendor_reason = _vendor_review_block_reason(review)
    if vendor_reason:
        _persist_pending(store, plan, state, vendor_reason)
        return {
            "action": "vendor_review_gate",
            "outcome": "pending",
            "pr": pr_number,
            "reason": vendor_reason,
        }

    result = dependencies.merge(pr_number, node["strategy"])
    if not result.get("success"):
        live_after_failure = dependencies.get_live_status(pr_number)
        terminal = _live_terminal_outcome(live_after_failure)
        if terminal is not None:
            return _reconcile_terminal(store, plan, state, pr_number, terminal)
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
    downstream = _mark_downstream(plan, pr_number)
    store.save(plan)
    return {
        "action": "merged",
        "outcome": "merged",
        "pr": pr_number,
        "downstream_revalidation": downstream,
        "merge": result,
    }


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
    args = parser.parse_args()

    result = execute_node(
        args.execute,
        args.pr,
        approve_gate=args.approve_gate,
        claim_id=args.claim_id,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["outcome"] == "merged" else 2


if __name__ == "__main__":
    raise SystemExit(main())

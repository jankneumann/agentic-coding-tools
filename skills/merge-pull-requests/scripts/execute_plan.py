#!/usr/bin/env python3
"""Execute one PR node from a durable merge plan."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


def canonical_scripts_dir() -> Path:
    """Resolve helpers from canonical ``skills/`` even when run via a mirror."""

    current = Path(__file__).resolve()
    for ancestor in current.parents:
        candidate = ancestor / "skills" / "merge-pull-requests" / "scripts"
        if candidate.is_dir():
            return candidate
    raise RuntimeError("canonical skills/merge-pull-requests/scripts not found")


CANONICAL_SCRIPTS_DIR = canonical_scripts_dir()
if str(CANONICAL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(CANONICAL_SCRIPTS_DIR))

from analyze_comments import analyze as analyze_pr_comments  # noqa: E402
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
    get_live_status: Callable[[int], dict[str, Any]]
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
    result = dispatch_vendor_reviews(pr_number=pr_number, pr_size=size)
    result["eligibility"] = eligibility
    return result


DEFAULT_DEPENDENCIES = ExecutionDependencies(
    get_live_status=validate_pr,
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


def _blocking_vendor_count(review: dict[str, Any]) -> int:
    consensus = review.get("consensus")
    if consensus is None and isinstance(review.get("review"), dict):
        consensus = review["review"].get("consensus")
    if not isinstance(consensus, dict):
        return 0
    return int(consensus.get("summary", {}).get("blocking_count", 0))


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


def execute_node(
    plan_path: Path,
    pr_number: int,
    *,
    approve_gate: bool = False,
    dependencies: ExecutionDependencies = DEFAULT_DEPENDENCIES,
) -> dict[str, Any]:
    """Execute exactly one planned PR and persist every resulting state change."""

    store = FilePlanStore(plan_path)
    plan = store.load()
    node = _find_node(plan, pr_number)
    state = node["state"]
    definition = node["definition"]

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
    if (not node["auto_executable"] or plan_gates) and not approve_gate:
        surfaced_gates = plan_gates or ["requires_human_approval"]
        reason = "explicit operator approval required"
        state["blocking_reason"] = reason
        store.save(plan)
        return {
            "action": "human_gate",
            "outcome": state["outcome"],
            "pr": pr_number,
            "gates": surfaced_gates,
            "reason": reason,
        }

    live = dependencies.get_live_status(pr_number)
    state["ci_state"] = _ci_state(live)
    needs_refresh = state.get("needs_revalidation", False) or state["staleness"] == "stale"
    if needs_refresh:
        refreshed = dependencies.refresh_branch(pr_number)
        if not refreshed.get("success"):
            reason = str(refreshed.get("reason") or refreshed.get("error") or "branch refresh failed")
            state["blocking_reason"] = reason
            store.save(plan)
            return {
                "action": "revalidation_failed",
                "outcome": state["outcome"],
                "pr": pr_number,
                "reason": reason,
            }
        live = dependencies.get_live_status(pr_number)
        state["ci_state"] = _ci_state(live)
        state["staleness"] = "fresh"
        state["needs_revalidation"] = False

    security_failures = _security_failures(live)
    if security_failures:
        reason = "failing required security check(s): " + ", ".join(security_failures)
        state["blocking_reason"] = reason
        store.save(plan)
        return {
            "action": "security_gate",
            "outcome": state["outcome"],
            "pr": pr_number,
            "reason": reason,
        }

    comments = dependencies.analyze_comments(pr_number)
    state["unresolved_comments"] = int(comments.get("unresolved_count", 0))
    state["unresolved_comment_summary"] = _comment_summary(comments)
    if state["unresolved_comments"]:
        reason = f"{state['unresolved_comments']} unresolved review comment(s)"
        state["blocking_reason"] = reason
        store.save(plan)
        return {
            "action": "delegate_comments",
            "outcome": state["outcome"],
            "pr": pr_number,
            "reason": reason,
            "delegation": _delegation_commands(pr_number, str(live.get("branch", ""))),
        }

    review = dependencies.review_vendor(pr_number, node["origin"], comments)
    state["vendor_verdict"] = review
    blocking_findings = _blocking_vendor_count(review)
    if blocking_findings:
        reason = f"vendor review reported {blocking_findings} blocking finding(s)"
        state["blocking_reason"] = reason
        store.save(plan)
        return {
            "action": "vendor_review_gate",
            "outcome": state["outcome"],
            "pr": pr_number,
            "reason": reason,
        }

    result = dependencies.merge(pr_number, node["strategy"])
    if not result.get("success"):
        reason = str(result.get("reason") or result.get("error") or "merge failed")
        state["blocking_reason"] = reason
        store.save(plan)
        return {
            "action": "merge_failed",
            "outcome": state["outcome"],
            "pr": pr_number,
            "reason": reason,
            "merge": result,
        }

    state["outcome"] = "merged"
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
    args = parser.parse_args()

    result = execute_node(
        args.execute,
        args.pr,
        approve_gate=args.approve_gate,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["outcome"] == "merged" else 2


if __name__ == "__main__":
    raise SystemExit(main())

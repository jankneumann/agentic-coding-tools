"""Fail-closed safety predicates shared by merge-plan execution."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from plan_storage import FilePlanStore, PlanWriteConflict


def default_sync_point_guard(repo_root: Path) -> dict[str, Any]:
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


def blocking_vendor_count(review: dict[str, Any]) -> int | None:
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


def vendor_review_block_reason(review: dict[str, Any]) -> str | None:
    """Return why an eligible review blocks, or ``None`` for a usable result."""

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
    blocking = blocking_vendor_count(review)
    if blocking is None:
        return "eligible vendor review produced no consensus verdict"
    if blocking:
        return f"vendor review reported {blocking} blocking finding(s)"
    return None


def live_terminal_outcome(live: dict[str, Any]) -> str | None:
    """Map live GitHub terminal state onto the plan outcome vocabulary."""

    state = str(live.get("state") or live.get("status") or "").upper()
    if live.get("merged") is True or state == "MERGED":
        return "merged"
    if state == "CLOSED":
        return "closed"
    return None


def refreshed_branch_block_reason(
    staleness: dict[str, Any],
    live: dict[str, Any],
    ci_state: str,
) -> str | None:
    """Require current-base, fresh-CI live state after a branch refresh."""

    failures = []
    if staleness.get("ci_merge_base_stale") is not False:
        failures.append("merge base is not confirmed current")
    if ci_state != "clean":
        failures.append("CI is not fresh and passing")
    if live.get("can_merge") is not True:
        failures.append("live PR state is not mergeable")
    if failures:
        return "branch refresh incomplete: " + "; ".join(failures)
    return None


def record_preclaim_blocker(
    store: FilePlanStore,
    pr_number: int,
    reason: str,
) -> dict[str, Any] | None:
    """Persist a gate reason without overwriting a concurrent claim."""

    try:
        store.update_state(
            pr_number,
            expected_outcome="pending",
            blocking_reason=reason,
        )
    except PlanWriteConflict:
        plan = store.load()
        state = next(node["state"] for node in plan["nodes"] if node["pr"] == pr_number)
        if state["outcome"] == "in_progress":
            return {
                "action": "execution_in_progress",
                "outcome": "in_progress",
                "pr": pr_number,
                "claimed_by": state.get("claimed_by"),
                "reason": "another execution claim won before gate persistence",
            }
        return {
            "action": "state_conflict",
            "outcome": state["outcome"],
            "pr": pr_number,
            "reason": "plan state changed before gate persistence",
        }
    return None

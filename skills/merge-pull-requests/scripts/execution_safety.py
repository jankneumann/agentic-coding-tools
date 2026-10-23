"""Fail-closed safety predicates shared by merge-plan execution."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from plan_storage import FilePlanStore, PlanWriteConflict
from verdict_binding import (
    POLICY_WAIVABLE_REASONS,
    independence_violation,
    stale_reason,
    verdict_currency,
)


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


POLICY_APPROVER = "policy:merge-pull-requests"
_WAIVER_SOURCES = frozenset({"policy", "operator"})


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def valid_waiver(waiver: Any, live_ineligible_reason: str | None) -> bool:
    """Return True when ``waiver`` is a well-formed waiver for this review.

    Every waiver needs a non-blank reason, a known source, a non-blank approver,
    a recorded time and an explicit ``eligibility_reason`` key. A policy waiver
    additionally stands only for a reason in the closed policy set that equals
    the live ineligibility reason, and only under the policy approver.
    """

    if not isinstance(waiver, dict):
        return False
    if not _nonblank(waiver.get("reason")):
        return False
    source = waiver.get("source")
    if source not in _WAIVER_SOURCES:
        return False
    if not _nonblank(waiver.get("approver")) or not _nonblank(waiver.get("recorded_at")):
        return False
    if "eligibility_reason" not in waiver:
        return False
    if source == "policy":
        reason = waiver.get("eligibility_reason")
        return (
            reason in POLICY_WAIVABLE_REASONS
            and reason == live_ineligible_reason
            and waiver.get("approver") == POLICY_APPROVER
        )
    return True


def vendor_review_block_reason(
    review: Any,
    *,
    waiver: dict[str, Any] | None = None,
    live_head_sha: str | None = None,
    live_patch_id: str | None = None,
) -> str | None:
    """Return why a merge must not proceed on this review, or ``None``.

    The predicate is total: ``None`` comes back on exactly two paths, a valid
    recorded waiver, or a bound, current-or-rebased, independent consensus
    verdict with zero blocking findings. Unresolved change requests block even
    under a waiver. Every other input, including a missing, skipped or
    malformed review, blocks with a reason.
    """

    eligibility = review.get("eligibility") if isinstance(review, dict) else None
    live_ineligible_reason: str | None = None
    if isinstance(eligibility, dict) and not eligibility.get("eligible"):
        live_ineligible_reason = eligibility.get("reason")
        if live_ineligible_reason == "changes_requested":
            return "existing review has unresolved change requests"
    if valid_waiver(waiver, live_ineligible_reason):
        return None
    if not isinstance(review, dict):
        return "no vendor review result and no review waiver recorded"
    if not isinstance(eligibility, dict):
        return "vendor review returned no eligibility decision"
    if not eligibility.get("eligible"):
        return (
            f"vendor review ineligible ({live_ineligible_reason}) "
            "and no review waiver recorded"
        )
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
    binding = review.get("binding")
    if not isinstance(binding, dict):
        return "vendor verdict is not bound to a reviewed head"
    if verdict_currency(binding, live_head_sha, live_patch_id) == "stale":
        return stale_reason(binding, live_head_sha)
    return independence_violation(binding)


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

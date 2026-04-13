"""Main execution loop for roadmap autopilot.

Loads a roadmap and checkpoint, iterates through ready items in priority
order, advancing checkpoint phases for each item.  Actual implementation
dispatch is handled by an injected callback (similar to how autopilot.py
works in skills/autopilot/).

The orchestrator manages the state machine and checkpoint lifecycle;
the SKILL.md prompt layer provides the dispatch_fn that invokes
/implement-feature, /validate-feature, etc.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent / "roadmap-runtime" / "scripts"
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

from checkpoint import CheckpointManager  # type: ignore[import-untyped]
from learning import write_entry  # type: ignore[import-untyped]
from models import (  # type: ignore[import-untyped]
    CheckpointPhase,
    ItemStatus,
    LearningDecision,
    LearningEntry,
    LearningPhase,
    Roadmap,
    RoadmapItem,
    load_roadmap,
    save_roadmap,
)

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from policy import PolicyDecision, VendorLimit, evaluate_policy  # type: ignore[import-untyped]
from replanner import replan  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


# Phase progression for a single item
_ITEM_PHASES = [
    CheckpointPhase.PLANNING,
    CheckpointPhase.IMPLEMENTING,
    CheckpointPhase.REVIEWING,
    CheckpointPhase.VALIDATING,
    CheckpointPhase.COMPLETED,
]


# ---------------------------------------------------------------------------
# Dispatch callback type
# ---------------------------------------------------------------------------

# dispatch_fn(item_id, phase, context) -> outcome string
# Outcomes: "success", "failed:<reason>", "vendor_limit:<vendor>:<reason>"
DispatchFn = Callable[[str, str, dict[str, Any]], str]


def _default_dispatch(item_id: str, phase: str, context: dict[str, Any]) -> str:
    """Default dispatch that auto-succeeds (for testing / dry-run)."""
    logger.info("dispatch.default: item=%s phase=%s (auto-success)", item_id, phase)
    return "success"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def execute_roadmap(
    workspace: Path,
    repo_root: Path | None = None,
    dispatch_fn: DispatchFn | None = None,
    on_policy_decision: Callable[[PolicyDecision], None] | None = None,
) -> dict[str, Any]:
    """Execute a roadmap from the given workspace.

    Parameters
    ----------
    workspace:
        Directory containing roadmap.yaml and (optionally) checkpoint.json.
    repo_root:
        Repository root for schema validation. None skips validation.
    dispatch_fn:
        Callback invoked for each item phase. Receives (item_id, phase, context)
        and returns an outcome string. Defaults to auto-success stub.
    on_policy_decision:
        Optional callback notified when a policy decision is made.

    Returns
    -------
    Summary dict with completed_count, failed_count, blocked_count, status,
    and policy_decisions list.
    """
    dispatch = dispatch_fn or _default_dispatch
    policy_decisions: list[dict[str, Any]] = []

    # Load roadmap
    roadmap = load_roadmap(workspace / "roadmap.yaml", repo_root)
    logger.info("Loaded roadmap %s with %d items", roadmap.roadmap_id, len(roadmap.items))

    # Load or create checkpoint
    mgr = CheckpointManager(workspace, repo_root)
    if mgr.exists():
        checkpoint = mgr.load()
        logger.info(
            "Resumed checkpoint: item=%s phase=%s completed=%d",
            checkpoint.current_item_id,
            checkpoint.phase.value,
            len(checkpoint.completed_items),
        )
    else:
        checkpoint = mgr.create(roadmap)
        logger.info("Created new checkpoint for %s", roadmap.roadmap_id)

    # Track vendor switch attempts per item
    switch_attempts: dict[str, int] = {}

    # Main loop: process ready items
    while True:
        # Determine what to work on
        ready = _get_ready_items(roadmap, checkpoint)
        if not ready:
            logger.info("No more ready items — execution complete")
            break

        # Pick highest priority ready item
        current_item = ready[0]
        item_id = current_item.item_id

        # If checkpoint already points at this item mid-phase, resume there
        if checkpoint.current_item_id == item_id and checkpoint.phase not in (
            CheckpointPhase.COMPLETED,
            CheckpointPhase.FAILED,
            CheckpointPhase.BLOCKED,
        ):
            start_phase = checkpoint.phase
        else:
            # Start fresh for this item
            checkpoint.current_item_id = item_id
            start_phase = CheckpointPhase.PLANNING
            mgr.advance_phase(checkpoint, start_phase)

        # Mark item as in-progress on the roadmap
        current_item.status = ItemStatus.IN_PROGRESS

        # Walk through phases for this item
        item_succeeded = _execute_item_phases(
            item_id=item_id,
            start_phase=start_phase,
            roadmap=roadmap,
            checkpoint=checkpoint,
            mgr=mgr,
            dispatch=dispatch,
            policy_decisions=policy_decisions,
            switch_attempts=switch_attempts,
            workspace=workspace,
            on_policy_decision=on_policy_decision,
        )

        if item_succeeded:
            # Complete the item
            mgr.complete_item(checkpoint, item_id)
            current_item.status = ItemStatus.COMPLETED
            _write_success_learning(workspace, item_id)

            # Run adaptive reprioritization
            try:
                changes = replan(roadmap, workspace)
                if changes:
                    logger.info("Replanner adjusted priorities: %s", changes)
            except Exception:
                logger.debug("Replanner failed (non-fatal)", exc_info=True)

        # Save updated roadmap
        save_roadmap(roadmap, workspace / "roadmap.yaml")

    # Build summary
    return _build_summary(roadmap, checkpoint, policy_decisions)


# ---------------------------------------------------------------------------
# Item phase execution
# ---------------------------------------------------------------------------

def _execute_item_phases(
    *,
    item_id: str,
    start_phase: CheckpointPhase,
    roadmap: Roadmap,
    checkpoint: Any,
    mgr: CheckpointManager,
    dispatch: DispatchFn,
    policy_decisions: list[dict[str, Any]],
    switch_attempts: dict[str, int],
    workspace: Path,
    on_policy_decision: Callable[[PolicyDecision], None] | None,
) -> bool:
    """Walk an item through its phases. Returns True if item completed."""
    start_idx = _ITEM_PHASES.index(start_phase) if start_phase in _ITEM_PHASES else 0

    for phase in _ITEM_PHASES[start_idx:]:
        if phase == CheckpointPhase.COMPLETED:
            # All execution phases done
            break

        mgr.advance_phase(checkpoint, phase)

        context = {
            "item_id": item_id,
            "roadmap_id": roadmap.roadmap_id,
            "completed_items": list(checkpoint.completed_items),
        }

        outcome = dispatch(item_id, phase.value, context)

        if outcome == "success":
            logger.info("item.phase_success: item=%s phase=%s", item_id, phase.value)
            continue

        if outcome.startswith("failed:"):
            reason = outcome[len("failed:"):]
            logger.warning("item.phase_failed: item=%s phase=%s reason=%s", item_id, phase.value, reason)
            mgr.fail_item(checkpoint, item_id, reason, roadmap)
            return False

        if outcome.startswith("vendor_limit:"):
            parts = outcome.split(":", 2)
            vendor = parts[1] if len(parts) > 1 else "unknown"
            reason = parts[2] if len(parts) > 2 else "rate limit"

            decision = _handle_vendor_limit(
                roadmap=roadmap,
                item_id=item_id,
                vendor=vendor,
                reason=reason,
                switch_attempts=switch_attempts,
            )
            policy_decisions.append({
                "item_id": item_id,
                "phase": phase.value,
                "decision": {
                    "action": decision.action,
                    "reason": decision.reason,
                    "from_vendor": decision.from_vendor,
                    "to_vendor": decision.to_vendor,
                },
            })
            if on_policy_decision:
                on_policy_decision(decision)

            if decision.action == "fail_closed":
                mgr.fail_item(checkpoint, item_id, f"Policy fail_closed: {decision.reason}", roadmap)
                return False

            # For "wait" and "switch" — the orchestrator records the decision
            # but the actual vendor routing is handled by the prompt layer
            # via the dispatch_fn on the next call. We continue the phase loop
            # to let the dispatch_fn retry with the new context.
            logger.info(
                "policy.applied: item=%s action=%s vendor=%s->%s",
                item_id, decision.action, decision.from_vendor, decision.to_vendor,
            )
            continue

        # Unknown outcome — treat as failure
        logger.warning("item.unknown_outcome: item=%s outcome=%s", item_id, outcome)
        mgr.fail_item(checkpoint, item_id, f"Unknown dispatch outcome: {outcome}", roadmap)
        return False

    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_ready_items(roadmap: Roadmap, checkpoint: Any) -> list[RoadmapItem]:
    """Get items ready for execution, excluding already completed ones."""
    completed_ids = set(checkpoint.completed_items)
    failed_ids = {f.item_id for f in checkpoint.failed_items}
    skip_ids = completed_ids | failed_ids

    # Items whose deps are all completed and status allows execution
    ready = []
    for item in roadmap.items:
        if item.item_id in skip_ids:
            continue
        if item.status in (ItemStatus.APPROVED, ItemStatus.IN_PROGRESS):
            if all(dep in completed_ids for dep in item.depends_on):
                ready.append(item)

    # Sort by priority (lower = higher priority)
    ready.sort(key=lambda i: i.priority)
    return ready


def _handle_vendor_limit(
    roadmap: Roadmap,
    item_id: str,
    vendor: str,
    reason: str,
    switch_attempts: dict[str, int],
) -> PolicyDecision:
    """Delegate to the policy engine for a vendor limit event."""
    limit = VendorLimit(vendor=vendor, reason=reason)
    attempts = switch_attempts.get(item_id, 0)

    # Available vendors placeholder — in real usage, the prompt layer
    # would provide this from vendor-status checks
    available = ["claude", "codex", "gemini"]
    available = [v for v in available if v != vendor]

    decision = evaluate_policy(
        policy=roadmap.policy,
        vendor_limit=limit,
        available_vendors=available,
        switch_attempts=attempts,
    )

    if decision.action == "switch":
        switch_attempts[item_id] = attempts + 1

    return decision


def _write_success_learning(workspace: Path, item_id: str) -> None:
    """Write a learning entry for a successfully completed item."""
    entry = LearningEntry(
        schema_version=1,
        item_id=item_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        phase=LearningPhase.IMPLEMENTATION,
        decisions=[
            LearningDecision(
                title=f"Completed {item_id}",
                outcome="Item executed successfully through all phases",
            ),
        ],
    )
    try:
        write_entry(workspace, entry)
    except Exception:
        logger.debug("Failed to write learning entry for %s (non-fatal)", item_id, exc_info=True)


def _build_summary(
    roadmap: Roadmap,
    checkpoint: Any,
    policy_decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the execution summary dict."""
    completed_count = len(checkpoint.completed_items)
    failed_count = len(checkpoint.failed_items)

    blocked_count = sum(
        1 for item in roadmap.items
        if item.status == ItemStatus.BLOCKED
    )
    skipped_count = sum(
        1 for item in roadmap.items
        if item.status == ItemStatus.SKIPPED
    )

    total = len(roadmap.items)
    if completed_count == total:
        status = "completed"
    elif completed_count + failed_count + blocked_count >= total:
        status = "blocked_all"
    elif completed_count > 0:
        status = "partial"
    else:
        status = "blocked_all"

    return {
        "completed_count": completed_count,
        "failed_count": failed_count,
        "blocked_count": blocked_count,
        "skipped_count": skipped_count,
        "status": status,
        "policy_decisions": policy_decisions,
    }

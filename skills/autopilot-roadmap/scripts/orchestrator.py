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

import json
import logging
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol, Union

_SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent
_RUNTIME_DIR = _SKILLS_ROOT / "roadmap-runtime" / "scripts"
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))
# `shared.trust_posture` is imported as a package module, so the PARENT of
# `shared/` must be importable, not `shared/` itself.
if str(_SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILLS_ROOT))

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
    completed_external_refs,
    load_roadmap,
    save_roadmap,
)

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from policy import PolicyDecision, VendorLimit, evaluate_policy  # type: ignore[import-untyped]
from replanner import replan  # type: ignore[import-untyped]
from shared.trust_posture import Gate  # noqa: E402

logger = logging.getLogger(__name__)

#: Filename of the replan handoff written into the workspace on a proceed.
REPLAN_REQUEST_FILENAME = "replan-request.json"

#: Summary status returned when a replan request was emitted.
REPLAN_REQUESTED_STATUS = "replan_requested"


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

# dispatch_fn(item_id, phase, context) -> outcome string OR result payload
# Outcomes: "success", "failed:<reason>", "vendor_limit:<vendor>:<reason>"
#
# A dispatcher may instead return a mapping ``{"outcome": <outcome string>,
# "replan": <bool>}``. The mapping form exists solely so the agent that saw the
# failure can say whether the roadmap needs re-planning; nothing here infers
# that from the reason text.
DispatchResult = Union[str, Mapping[str, Any]]
DispatchFn = Callable[[str, str, dict[str, Any]], DispatchResult]


def _default_dispatch(item_id: str, phase: str, context: dict[str, Any]) -> str:
    """Default dispatch that auto-succeeds (for testing / dry-run)."""
    logger.info("dispatch.default: item=%s phase=%s (auto-success)", item_id, phase)
    return "success"


def _normalize_outcome(result: DispatchResult) -> tuple[str, bool]:
    """Split a dispatch result into ``(outcome string, replan signal)``.

    A bare string is the historical contract and never requests a replan.
    """
    if isinstance(result, Mapping):
        return str(result.get("outcome", "")), bool(result.get("replan", False))
    return str(result), False


# ---------------------------------------------------------------------------
# Gate evaluation seam
# ---------------------------------------------------------------------------

class GateEvaluator(Protocol):
    """The slice of ``shared.approval_gate.ApprovalGate`` this module uses.

    Injecting it is what keeps ``skills/autopilot-roadmap/scripts/`` free of any
    network or LLM call: the production evaluator (which talks to the
    coordinator) is constructed by the host, and tests pass a fake.
    """

    def evaluate(self, gate: Gate, context: dict[str, Any]) -> Any: ...


def _build_default_gate_evaluator() -> GateEvaluator:
    """Lazily construct the production gate.

    Imported inside the function, and called only once a gate is actually
    reached, so an ordinary run never opens a coordinator transport it does not
    need — and importing this module stays free of that dependency.
    """
    from shared.approval_gate import build_default_gate

    return build_default_gate(agent_id="autopilot-roadmap")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def execute_roadmap(
    workspace: Path,
    repo_root: Path | None = None,
    dispatch_fn: DispatchFn | None = None,
    on_policy_decision: Callable[[PolicyDecision], None] | None = None,
    gate_evaluator: GateEvaluator | None = None,
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
        and returns an outcome string, or a ``{"outcome": ..., "replan": ...}``
        payload. Defaults to auto-success stub.
    on_policy_decision:
        Optional callback notified when a policy decision is made.
    gate_evaluator:
        Object with ``evaluate(gate, context)`` used for ``Gate.REPLAN_REQUIRED``.
        Defaults to ``shared.approval_gate.build_default_gate()``, built lazily
        the first time a gate is actually reached.

    Returns
    -------
    Summary dict with completed_count, failed_count, blocked_count,
    skipped_count, superseded_count, status, policy_decisions, and
    gate_decisions. When a replan request was emitted the status is
    ``replan_requested`` and ``replan_request`` describes the handoff file.
    """
    dispatch = dispatch_fn or _default_dispatch
    policy_decisions: list[dict[str, Any]] = []
    gate_decisions: list[dict[str, Any]] = []
    # Mutable because _execute_item_phases reports "the run must stop and hand
    # off to the host" the same way it reports policy decisions — by filling a
    # container the caller owns — rather than by widening its bool return.
    replan_state: dict[str, Any] = {}

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
        # Cross-roadmap prerequisites: an external_depends_on ref is satisfied
        # once the referenced sibling item reaches 'completed'. Recomputed each
        # iteration so a prerequisite completing elsewhere is picked up without
        # a manual status edit here. Read-only scan of sibling roadmaps.
        external_completed = (
            completed_external_refs(repo_root) if repo_root else set()
        )

        # Determine what to work on
        ready = _get_ready_items(roadmap, checkpoint, external_completed)
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
            repo_root=repo_root,
            on_policy_decision=on_policy_decision,
            gate_evaluator=gate_evaluator,
            gate_decisions=gate_decisions,
            replan_state=replan_state,
        )

        if replan_state.get("requested"):
            # The gate said proceed: the roadmap's remaining shape is now the
            # host's to decide (`/plan-roadmap --replan`). Dispatching anything
            # else first would build on a plan we just declared stale.
            save_roadmap(roadmap, workspace / "roadmap.yaml", overwrite=True)
            break

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

        # Save updated roadmap (in-place update — overwrite is expected here)
        save_roadmap(roadmap, workspace / "roadmap.yaml", overwrite=True)

    # Build summary
    return _build_summary(roadmap, checkpoint, policy_decisions, gate_decisions, replan_state)


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
    repo_root: Path | None,
    on_policy_decision: Callable[[PolicyDecision], None] | None,
    gate_evaluator: GateEvaluator | None,
    gate_decisions: list[dict[str, Any]],
    replan_state: dict[str, Any],
) -> bool:
    """Walk an item through its phases. Returns True if item completed."""
    start_idx = _ITEM_PHASES.index(start_phase) if start_phase in _ITEM_PHASES else 0

    def _fail(reason: str, *, replan: bool = False) -> None:
        _handle_failure(
            item_id=item_id,
            reason=reason,
            replan=replan,
            roadmap=roadmap,
            checkpoint=checkpoint,
            mgr=mgr,
            workspace=workspace,
            repo_root=repo_root,
            gate_evaluator=gate_evaluator,
            gate_decisions=gate_decisions,
            replan_state=replan_state,
        )

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

        outcome, replan_signal = _normalize_outcome(dispatch(item_id, phase.value, context))

        if outcome == "success":
            logger.info("item.phase_success: item=%s phase=%s", item_id, phase.value)
            continue

        if outcome.startswith("failed:"):
            reason = outcome[len("failed:"):]
            logger.warning("item.phase_failed: item=%s phase=%s reason=%s", item_id, phase.value, reason)
            _fail(reason, replan=replan_signal)
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
                # A vendor-policy stop is not a plan problem — no replan signal.
                _fail(f"Policy fail_closed: {decision.reason}")
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
        _fail(f"Unknown dispatch outcome: {outcome}")
        return False

    return True


# ---------------------------------------------------------------------------
# Failure handling and the replan gate
# ---------------------------------------------------------------------------

def _handle_failure(
    *,
    item_id: str,
    reason: str,
    replan: bool,
    roadmap: Roadmap,
    checkpoint: Any,
    mgr: CheckpointManager,
    workspace: Path,
    repo_root: Path | None,
    gate_evaluator: GateEvaluator | None,
    gate_decisions: list[dict[str, Any]],
    replan_state: dict[str, Any],
) -> None:
    """Record the failure and, when a replan was signalled, run the gate once.

    The gate is evaluated **once per failure, not once per parked dependent**:
    one failure produces one re-planning question ("should the host re-decompose
    the subgraph this item was holding up?"). Asking it per dependent would put
    the same question to a human N times for one event, and N-1 of those answers
    could contradict the first.
    """
    mgr.fail_item(checkpoint, item_id, reason, roadmap, replan=replan)
    if not replan:
        return

    parked = sorted(
        i.item_id for i in roadmap.items if i.status == ItemStatus.REPLAN_REQUIRED
    )
    if not parked:
        # Nothing depended on the failed item, so there is no subgraph to
        # re-decompose and nothing to ask about.
        logger.info("replan.no_dependents: item=%s — gate not evaluated", item_id)
        return

    evaluator = gate_evaluator or _build_default_gate_evaluator()
    decision = evaluator.evaluate(
        Gate.REPLAN_REQUIRED,
        {
            "roadmap_id": roadmap.roadmap_id,
            "failed_item_id": item_id,
            "failure_reason": reason,
            "replan_required_items": parked,
            "workspace": str(workspace),
        },
    )
    record = _gate_decision_record(decision)
    gate_decisions.append(record)
    mgr.record_gate_decision(checkpoint, record)

    if not decision.proceed:
        # Fail closed: the items stay in replan_required (so they are not ready
        # and will not be dispatched), no request is written, and the run keeps
        # going with whatever else is ready.
        logger.info(
            "replan.gate_blocked: item=%s resolution=%s parked=%s",
            item_id, record.get("resolution"), ",".join(parked),
        )
        return

    request_path = _write_replan_request(
        workspace=workspace,
        repo_root=repo_root,
        roadmap=roadmap,
        failed_item_id=item_id,
        reason=reason,
        parked=parked,
        gate_decision=record,
    )
    replan_state["requested"] = True
    replan_state["items"] = parked
    replan_state["path"] = str(request_path)
    replan_state["failed_item_id"] = item_id
    logger.info("replan.requested: item=%s request=%s", item_id, request_path)


def _gate_decision_record(decision: Any) -> dict[str, Any]:
    """Flatten an ``ApprovalDecision`` to a ``gate-decision.schema.json`` record.

    ``to_audit_record()`` names the authorizing posture value
    ``authorizing_disposition``; the contract calls it ``disposition``. Both are
    emitted (the schema allows additional properties) so an audit reader that
    already parses the coordinator's records keeps working.
    """
    record = dict(decision.to_audit_record())
    record["disposition"] = decision.disposition.value
    record["recorded_at"] = datetime.now(timezone.utc).isoformat()
    return record


def _write_replan_request(
    *,
    workspace: Path,
    repo_root: Path | None,
    roadmap: Roadmap,
    failed_item_id: str,
    reason: str,
    parked: list[str],
    gate_decision: dict[str, Any],
) -> Path:
    """Write the ``ReplanRequest`` handoff file.

    A *file*, not a coordinator issue or an LLM call: the host-assisted
    invariant forbids network access from this package, and the workspace is
    already the durable handoff medium (roadmap.yaml, checkpoint.json,
    learnings/). ``/plan-roadmap --replan`` consumes and deletes it.
    """
    request: dict[str, Any] = {
        "schema_version": 1,
        "roadmap_id": roadmap.roadmap_id,
        "failed_item_id": failed_item_id,
        "failure_reason": reason,
        "replan_required_items": parked,
        "gate_decision": gate_decision,
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    learning_path = workspace / "learnings" / f"{failed_item_id}.md"
    if learning_path.exists():
        request["learning_entry"] = _repo_relative(learning_path, repo_root)

    path = workspace / REPLAN_REQUEST_FILENAME
    path.write_text(json.dumps(request, indent=2) + "\n")
    return path


def _repo_relative(path: Path, repo_root: Path | None) -> str:
    """Repo-relative path when it can be computed, absolute otherwise."""
    if repo_root:
        try:
            return str(path.resolve().relative_to(Path(repo_root).resolve()))
        except ValueError:
            pass
    return str(path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_ready_items(
    roadmap: Roadmap,
    checkpoint: Any,
    external_completed: set[str] | None = None,
) -> list[RoadmapItem]:
    """Get items ready for execution, excluding already completed ones.

    ``external_completed`` is the set of cross-roadmap item_refs
    ``<roadmap-id>:<item-id>`` whose referenced item has reached ``completed``
    (see :func:`models.completed_external_refs`). An item's
    ``external_depends_on`` refs must all be in that set for the item to be
    ready — so an item whose only remaining blocker is an external prerequisite
    becomes ready automatically when that prerequisite completes, with no
    manual status edit. ``superseded`` items are never ready (their status is
    not in the executable set), and neither is an item carrying a non-empty
    ``superseded_by`` edge whose status was never flipped — mirrors
    :meth:`Roadmap.ready_items`. Deterministic and side-effect-free.
    """
    external_completed = external_completed or set()
    completed_ids = set(checkpoint.completed_items)
    failed_ids = {f.item_id for f in checkpoint.failed_items}
    skip_ids = completed_ids | failed_ids

    # Items whose deps are all completed and status allows execution
    ready = []
    for item in roadmap.items:
        if item.item_id in skip_ids:
            continue
        if item.superseded_by:
            continue
        if item.status in (ItemStatus.APPROVED, ItemStatus.IN_PROGRESS):
            if all(dep in completed_ids for dep in item.depends_on) and all(
                ref in external_completed for ref in item.external_depends_on
            ):
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
    available = ["claude", "codex", "antigravity", "grok", "pi"]
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
    gate_decisions: list[dict[str, Any]] | None = None,
    replan_state: dict[str, Any] | None = None,
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
    # SUPERSEDED is terminal: the work migrated to another roadmap's item via a
    # ri-17 `superseded_by` edge, so it will never become ready here. Omitting
    # it from terminal_count leaves a roadmap whose remaining items are all
    # superseded permanently reporting "partial" — the run can never finish.
    superseded_count = sum(
        1 for item in roadmap.items
        if item.status == ItemStatus.SUPERSEDED
    )

    total = len(roadmap.items)
    terminal_count = (
        completed_count + failed_count + blocked_count
        + skipped_count + superseded_count
    )
    # A roadmap whose every item is either completed or superseded IS complete:
    # nothing remains to execute here. Requiring completed_count == total would
    # report "blocked_all" for a fully-resolved roadmap.
    if completed_count + superseded_count == total:
        status = "completed"
    elif terminal_count >= total:
        status = "blocked_all"
    elif completed_count > 0:
        status = "partial"
    else:
        status = "blocked_all"

    replan_required_count = sum(
        1 for item in roadmap.items
        if item.status == ItemStatus.REPLAN_REQUIRED
    )
    replan_state = replan_state or {}
    summary: dict[str, Any] = {
        "completed_count": completed_count,
        "failed_count": failed_count,
        "blocked_count": blocked_count,
        "skipped_count": skipped_count,
        "superseded_count": superseded_count,
        "replan_required_count": replan_required_count,
        "status": status,
        "policy_decisions": policy_decisions,
        "gate_decisions": list(gate_decisions or []),
    }
    if replan_state.get("requested"):
        # The run stopped deliberately to hand off to the host; that is a
        # different outcome from "blocked_all" and the host branches on it.
        summary["status"] = REPLAN_REQUESTED_STATUS
        summary["replan_request"] = {
            "path": replan_state.get("path"),
            "failed_item_id": replan_state.get("failed_item_id"),
            "replan_required_items": list(replan_state.get("items", [])),
        }
    return summary

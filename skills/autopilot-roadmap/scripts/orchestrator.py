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

import copy
import hashlib
import json
import logging
import re
import secrets
import sys
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence, Union


_SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent
_RUNTIME_DIR = _SKILLS_ROOT / "roadmap-runtime" / "scripts"
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))
# `shared.trust_posture` is imported as a package module, so the PARENT of
# `shared/` must be importable, not `shared/` itself.
if str(_SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILLS_ROOT))

from checkpoint import CheckpointManager  # type: ignore[import-untyped]
from dispatch_scheduler import (  # type: ignore[import-untyped]
    ReadyDispatchItem,
    select_safe_ready_batch,
)
from learning import write_entry  # type: ignore[import-untyped]
from readiness import _get_ready_items  # type: ignore[import-untyped]
from models import (  # type: ignore[import-untyped]
    CheckpointPhase,
    ItemStatus,
    LearningDecision,
    LearningEntry,
    LearningPhase,
    PolicyAction,
    Roadmap,
    RoadmapItem,
    completed_external_refs,
    load_roadmap,
    save_roadmap,
    validate_delegated_dispatch_attempt,
)

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
_BRIDGE_DIR = _SKILLS_ROOT / "coordination-bridge" / "scripts"
if str(_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_DIR))

from coordination_bridge import try_list_vendors  # type: ignore[import-untyped]
from policy import (  # type: ignore[import-untyped]
    PolicyDecision,
    VendorLimit,
    filter_registry_lanes,
    select_registry_lane,
)
from replanner import replan  # type: ignore[import-untyped]
from sanitizer import sanitize_dict  # type: ignore[import-untyped]
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


IsolationResolver = Callable[[RoadmapItem], Mapping[str, Any]]
RoutingResolver = Callable[
    [RoadmapItem, str, Mapping[str, Any]], Mapping[str, Any] | None
]
RoutingReconciler = Callable[[Mapping[str, Any]], Mapping[str, Any] | None]
_RESULT_REQUIRED = {
    "schema_version",
    "dispatch_id",
    "change_id",
    "attempt",
    "lease_generation",
    "outcome",
}
_RESULT_ALLOWED = _RESULT_REQUIRED | {
    "replan",
    "handoff_id",
    "worktree_path",
    "branch",
    "parked",
    "evidence",
}
_EXACT_CHANGE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_BATCH_ID = re.compile(r"^batch-[0-9a-f]{24}$")
_RESULT_OUTCOME = re.compile(r"^(success|failed:.+|vendor_limit:[^:]+:.+|parked)$")
_DATE_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
)
_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_TERMINAL_ATTEMPT_STATUSES = {"completed", "failed", "parked"}
_RESERVED_DISPATCH_CONTEXT_KEYS = frozenset(
    {
        "attempt",
        "change_id",
        "dispatch_id",
        "dispatch_result",
        "execution_mode",
        "isolation",
        "item_id",
        "lease_generation",
        "roadmap_id",
        "scope",
    }
)
_APPLICATION_STATES = (
    "result_bound",
    "callback_started",
    "callback_acknowledged",
    "terminal_persisted",
    "effects_applied",
)
_UNRESOLVED_ATTEMPT_STATUSES = {
    "prepared",
    "claimed",
    "acknowledged",
    "launched",
    "quarantined",
    "parked",
}


def _load_or_create_execution_state(
    workspace: Path,
    repo_root: Path,
) -> tuple[Roadmap, CheckpointManager, Any]:
    roadmap = load_roadmap(workspace / "roadmap.yaml", repo_root)
    manager = CheckpointManager(workspace, repo_root)
    checkpoint = manager.load() if manager.exists() else manager.create(roadmap)
    return roadmap, manager, checkpoint


def _copy_context(context: Mapping[str, Any] | None) -> dict[str, Any]:
    value = copy.deepcopy(dict(context or {}))
    collisions = sorted(value.keys() & _RESERVED_DISPATCH_CONTEXT_KEYS)
    if collisions:
        raise ValueError(
            f"dispatch context contains reserved keys: {', '.join(collisions)}"
        )
    return value


def _validated_isolation(value: Mapping[str, Any]) -> dict[str, str]:
    isolation = dict(value)
    if set(isolation) != {"mode", "worktree_path", "branch"}:
        raise ValueError("isolation must contain exactly mode, worktree_path, and branch")
    if isolation["mode"] not in {"managed_worktree", "harness_provided"}:
        raise ValueError("unsupported isolation mode")
    if not isinstance(isolation["worktree_path"], str) or not isolation["worktree_path"]:
        raise ValueError("isolation worktree_path must be non-empty")
    if not isinstance(isolation["branch"], str) or not isolation["branch"]:
        raise ValueError("isolation branch must be non-empty")
    return isolation  # type: ignore[return-value]


def _validated_routing_decision(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a detached routing decision with a canonical dg-05 assignment."""
    decision = copy.deepcopy(dict(value))
    decision_id = decision.get("decision_id")
    assignment = decision.get("assignment")
    if not isinstance(decision_id, str) or not decision_id:
        raise ValueError("routing decision_id must be a non-empty string")
    if not isinstance(assignment, Mapping):
        raise ValueError("routing assignment must be an object")
    required = {"agent_id", "vendor_type", "location", "isolation", "dispatch_mode", "model", "endpoint_kind"}
    if not required.issubset(assignment):
        raise ValueError("routing assignment is missing required fields")
    if any(
        not isinstance(assignment[field], str) or not assignment[field]
        for field in required
    ):
        raise ValueError("routing assignment fields must be non-empty strings")
    isolation = assignment.get("isolation")
    if isolation not in {"none", "worktree", "sandbox"}:
        raise ValueError("routing assignment has invalid isolation")
    return decision


def _prepare_routing_attempt(
    *,
    roadmap_id: str,
    item_id: str,
    phase: str,
    decision: Mapping[str, Any],
    checkpoint: Any,
    manager: CheckpointManager,
) -> dict[str, Any]:
    """Persist and return the immutable context for one routed host dispatch."""
    prior = [
        attempt
        for attempt in checkpoint.routing_attempts
        if attempt.get("item_id") == item_id and attempt.get("phase") == phase
    ]
    attempt_number = 1 + max(
        (int(attempt.get("attempt", 0)) for attempt in prior),
        default=0,
    )
    decision_id = str(decision["decision_id"])
    digest = hashlib.sha256(
        f"{roadmap_id}:{item_id}:{phase}:{attempt_number}:{decision_id}".encode()
    ).hexdigest()[:24]
    routing = {
        "schema_version": 1,
        "decision_id": decision_id,
        "item_id": item_id,
        "phase": phase,
        "attempt": attempt_number,
        "dispatch_work_id": f"route-{digest}",
        "assignment": copy.deepcopy(decision["assignment"]),
    }
    if isinstance(decision.get("provenance"), Mapping):
        routing["provenance"] = copy.deepcopy(decision["provenance"])
    record = copy.deepcopy(routing)
    record.update(
        status="prepared",
        prepared_at=datetime.now(timezone.utc).isoformat(),
    )
    checkpoint.routing_attempts.append(record)
    manager.save(checkpoint)
    return routing


def _finish_routing_attempt(
    *,
    checkpoint: Any,
    manager: CheckpointManager,
    routing: Mapping[str, Any],
    result: Mapping[str, Any],
    expected_ledger_status: str,
    failure_reason: str | None = None,
    policy_decision: PolicyDecision | None = None,
    policy_resume_at: str | None = None,
) -> str:
    """Verify routed result identity and durably close its prepared record."""
    proof = result.get("routing_proof")
    record = next(
        attempt
        for attempt in reversed(checkpoint.routing_attempts)
        if attempt.get("dispatch_work_id") == routing["dispatch_work_id"]
    )
    assignment = record["assignment"]
    expected = {
        "routing_decision_id": record["decision_id"],
        "dispatch_work_id": record["dispatch_work_id"],
        "observed_agent_id": assignment["agent_id"],
        "ledger_status": expected_ledger_status,
    }
    valid = (
        isinstance(proof, Mapping)
        and set(proof) == set(expected)
        and all(proof.get(key) == value for key, value in expected.items())
    )
    record["status"] = expected_ledger_status if valid else "failed"
    record["resolved_at"] = datetime.now(timezone.utc).isoformat()
    if not valid:
        record["failure_reason"] = "routing_proof_mismatch"
    elif failure_reason:
        record["failure_reason"] = failure_reason
    elif policy_decision is not None:
        record["policy_action"] = policy_decision.action
        if policy_decision.action in {"wait", "fail_closed"}:
            now = datetime.now(timezone.utc).isoformat()
            pause_state: dict[str, Any] = {
                "paused": True,
                "reason": policy_decision.reason,
                "paused_at": now,
                "blocked_vendor": policy_decision.from_vendor,
            }
            if policy_resume_at is not None:
                pause_state["expected_resume_at"] = policy_resume_at
            checkpoint.pause_state = sanitize_dict(pause_state)
            escalation_kind = None
            if policy_decision.action == "fail_closed":
                escalation_kind = "routing_switch_cap"
            elif policy_resume_at is None:
                escalation_kind = "routing_wait_resume_required"
            if escalation_kind is not None:
                safety = dict(checkpoint.execution_safety)
                safety["escalation"] = {
                    "kind": escalation_kind,
                    "reason": policy_decision.reason,
                    "item_id": record["item_id"],
                    "phase": record["phase"],
                    "created_at": now,
                }
                checkpoint.execution_safety = safety
    manager.save(checkpoint)

    if not valid:
        raise ValueError("routing result does not match the active durable attempt")
    return str(expected["observed_agent_id"])


def _reject_routing_attempt(
    *,
    checkpoint: Any,
    manager: CheckpointManager,
    routing: Mapping[str, Any],
    reason: str,
) -> None:
    record = next(
        attempt
        for attempt in reversed(checkpoint.routing_attempts)
        if attempt.get("dispatch_work_id") == routing["dispatch_work_id"]
    )
    record["status"] = "failed"
    record["failure_reason"] = reason
    record["resolved_at"] = datetime.now(timezone.utc).isoformat()
    manager.save(checkpoint)


def _routing_policy_decision(
    roadmap: Roadmap,
    *,
    vendor: str,
    reason: str,
    switch_count: int,
) -> PolicyDecision:
    if roadmap.policy.default_action == PolicyAction.WAIT:
        return PolicyDecision(
            action="wait",
            reason=f"Policy requires waiting for limited vendor {vendor}: {reason}",
            from_vendor=vendor,
        )
    if switch_count >= roadmap.policy.max_switch_attempts_per_item:
        return PolicyDecision(
            action="fail_closed",
            reason=(
                "Routing switch retry cap exhausted "
                f"({switch_count} >= {roadmap.policy.max_switch_attempts_per_item})"
            ),
            from_vendor=vendor,
            cost_guard="not_applicable",
        )
    if roadmap.policy.cost_ceiling_usd is not None:
        return PolicyDecision(
            action="fail_closed",
            reason="Routed switch has no authoritative cost estimate for configured ceiling",
            from_vendor=vendor,
            cost_guard="unavailable",
        )
    return PolicyDecision(
        action="switch",
        reason="Roadmap policy authorizes a fresh router decision",
        from_vendor=vendor,
        cost_guard="not_configured",
    )




def _durable_progress_fingerprint(checkpoint: Any) -> str:
    payload = {
        "current_item_id": checkpoint.current_item_id,
        "phase": checkpoint.phase.value,
        "completed_items": sorted(checkpoint.completed_items),
        "failed_items": sorted(item.item_id for item in checkpoint.failed_items),
        "routing_attempts": [
            [attempt.get("dispatch_work_id"), attempt.get("status")]
            for attempt in checkpoint.routing_attempts
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _park_execution(
    *,
    checkpoint: Any,
    manager: CheckpointManager,
    kind: str,
    reason: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    safety = dict(checkpoint.execution_safety)
    safety["escalation"] = {
        "kind": kind,
        "reason": reason,
        "item_id": checkpoint.current_item_id,
        "phase": checkpoint.phase.value,
        "created_at": now,
    }
    checkpoint.execution_safety = safety
    checkpoint.pause_state = {
        "paused": True,
        "reason": reason,
        "paused_at": now,
    }
    manager.save(checkpoint)


def _before_host_dispatch(
    *,
    checkpoint: Any,
    manager: CheckpointManager,
    max_iterations: int,
    max_no_progress: int,
) -> bool:
    safety = dict(checkpoint.execution_safety)
    iterations = int(safety.get("iteration_count", 0))
    if iterations >= max_iterations:
        _park_execution(
            checkpoint=checkpoint,
            manager=manager,
            kind="iteration_cap",
            reason=f"Global dispatch iteration cap reached ({max_iterations})",
        )
        return False

    fingerprint = _durable_progress_fingerprint(checkpoint)
    previous = safety.get("durable_progress_fingerprint")
    no_progress = int(safety.get("consecutive_no_progress", 0))
    no_progress = no_progress + 1 if previous == fingerprint else 0
    safety.update(
        iteration_count=iterations + 1,
        durable_progress_fingerprint=fingerprint,
        consecutive_no_progress=no_progress,
    )
    checkpoint.execution_safety = safety
    if no_progress >= max_no_progress:
        _park_execution(
            checkpoint=checkpoint,
            manager=manager,
            kind="no_progress_cap",
            reason=f"Consecutive no-progress cap reached ({max_no_progress})",
        )
        return False
    manager.save(checkpoint)
    return True


def _next_attempt_number(checkpoint: Any, item_id: str) -> int:
    return 1 + max(
        (
            int(attempt["attempt"])
            for attempt in checkpoint.dispatch_attempts
            if attempt.get("item_id") == item_id
        ),
        default=0,
    )


def _request_from_attempt(
    roadmap_id: str,
    attempt: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "dispatch_id": attempt["dispatch_id"],
        "roadmap_id": roadmap_id,
        "item_id": attempt["item_id"],
        "change_id": attempt["change_id"],
        "phase": attempt["phase"],
        "attempt": attempt["attempt"],
        "launch_token": attempt["launch_token"],
        "lease_generation": attempt["lease_generation"],
        "launch_marker_path": attempt["launch_marker_path"],
        "scope": copy.deepcopy(attempt["scope"]),
        "isolation": copy.deepcopy(attempt["isolation"]),
        "context": copy.deepcopy(attempt["context"]),
    }


def prepare_delegated_batch(
    workspace: Path,
    *,
    repo_root: Path,
    isolation_resolver: IsolationResolver,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist one scope-safe generation batch without invoking ``dispatch_fn``."""
    base_context = _copy_context(context)
    roadmap, manager, checkpoint = _load_or_create_execution_state(workspace, repo_root)
    unresolved_items = {
        attempt["item_id"]
        for attempt in checkpoint.dispatch_attempts
        if attempt.get("status") in _UNRESOLVED_ATTEMPT_STATUSES
    }
    ready = [
        item
        for item in _get_ready_items(
            roadmap,
            checkpoint,
            completed_external_refs(repo_root),
        )
        if item.item_id not in unresolved_items
    ]
    positions = {item.item_id: index for index, item in enumerate(roadmap.items)}
    plan = select_safe_ready_batch(
        repo_root,
        [
            ReadyDispatchItem(
                item.item_id, item.change_id, item.priority, positions[item.item_id]
            )
            for item in ready
        ],
        forced_serial_item_ids=checkpoint.serial_indeterminate_items,
    )
    failures = [
        {"item_id": failure.item_id, "reason": failure.reason}
        for failure in plan.failures
    ]
    if not plan.items:
        return {
            "batch_id": None,
            "requests": [],
            "failures": failures,
            "deferred_item_ids": list(plan.deferred_item_ids),
        }

    by_id = {item.item_id: item for item in roadmap.items}
    generation_specs: list[tuple[Any, RoadmapItem, int, dict[str, str]]] = []
    for selected in plan.items:
        item = by_id[selected.item_id]
        try:
            isolation = _validated_isolation(isolation_resolver(item))
        except Exception as exc:
            failures.append(
                {
                    "item_id": item.item_id,
                    "reason": f"isolation_resolution_failed:{type(exc).__name__[:64]}",
                }
            )
            continue
        generation_specs.append(
            (selected, item, _next_attempt_number(checkpoint, item.item_id), isolation)
        )
    pending_serial_items = set(checkpoint.serial_indeterminate_items)
    pending_serial_items.update(plan.serial_item_ids)
    pending_serial_items.difference_update(
        item.item_id for _, item, _, _ in generation_specs
    )
    checkpoint.serial_indeterminate_items = sorted(pending_serial_items)
    if not generation_specs:
        manager.save(checkpoint)
        return {
            "batch_id": None,
            "requests": [],
            "failures": failures,
            "deferred_item_ids": list(plan.deferred_item_ids),
        }
    digest_input = json.dumps(
        [
            [roadmap.roadmap_id, item.item_id, attempt_number]
            for _, item, attempt_number, _ in generation_specs
        ],
        separators=(",", ":"),
        ensure_ascii=True,
    )
    batch_id = f"batch-{hashlib.sha256(digest_input.encode()).hexdigest()[:24]}"
    prepared: list[dict[str, Any]] = []
    dispatch_ids: list[str] = []
    for selected, item, attempt_number, isolation in generation_specs:
        dispatch_id = f"{batch_id}:{item.item_id}:attempt-{attempt_number}"
        dispatch_ids.append(dispatch_id)
        prepared.append(
            {
                "dispatch_id": dispatch_id,
                "item_id": item.item_id,
                "change_id": selected.change_id,
                "phase": "autopilot",
                "attempt": attempt_number,
                "status": "prepared",
                "prepared_at": datetime.now(timezone.utc).isoformat(),
                "launch_token": secrets.token_urlsafe(24),
                "launch_marker_path": (
                    f".supervised-dispatch/{item.change_id}/"
                    f"{item.item_id}-attempt-{attempt_number}.marker"
                ),
                "lease_generation": 1,
                "launch_history": [],
                "scope": selected.scope.to_request_scope(),
                "isolation": isolation,
                "context": copy.deepcopy(base_context),
            }
        )

    for attempt in prepared:
        validate_delegated_dispatch_attempt(attempt)

    existing_ids = {attempt["dispatch_id"] for attempt in checkpoint.dispatch_attempts}
    if existing_ids.intersection(dispatch_ids):
        raise ValueError("duplicate delegated dispatch generation")
    checkpoint.dispatch_attempts.extend(copy.deepcopy(prepared))
    manager.save(checkpoint)
    for attempt in prepared:
        by_id[attempt["item_id"]].status = ItemStatus.IN_PROGRESS
    save_roadmap(roadmap, workspace / "roadmap.yaml", overwrite=True)

    return {
        "batch_id": batch_id,
        "requests": [
            _request_from_attempt(roadmap.roadmap_id, attempt) for attempt in prepared
        ],
        "failures": failures,
        "deferred_item_ids": list(plan.deferred_item_ids),
    }


def _validate_dispatch_result(result: Mapping[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(dict(result))
    missing = _RESULT_REQUIRED - value.keys()
    extra = value.keys() - _RESULT_ALLOWED
    if missing or extra:
        raise ValueError(
            "invalid supervised dispatch result fields: "
            f"missing={sorted(missing)} extra={sorted(extra)}"
        )
    if isinstance(value["schema_version"], bool) or value["schema_version"] != 1:
        raise ValueError("invalid supervised dispatch result schema_version")
    if not isinstance(value["dispatch_id"], str) or not 1 <= len(value["dispatch_id"]) <= 256:
        raise ValueError("invalid supervised dispatch result dispatch_id")
    change_id = value["change_id"]
    if (
        not isinstance(change_id, str)
        or len(change_id) > 160
        or _EXACT_CHANGE_ID.fullmatch(change_id) is None
    ):
        raise ValueError("invalid supervised dispatch result change_id")
    for field in ("attempt", "lease_generation"):
        number = value[field]
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise ValueError(f"invalid supervised dispatch result {field}")
    outcome = value["outcome"]
    if (
        not isinstance(outcome, str)
        or len(outcome) > 1024
        or _RESULT_OUTCOME.fullmatch(outcome) is None
    ):
        raise ValueError("invalid supervised dispatch result outcome")
    if "replan" in value and not isinstance(value["replan"], bool):
        raise ValueError("invalid supervised dispatch result replan")
    if "handoff_id" in value and (
        value["handoff_id"] is not None
        and (
            not isinstance(value["handoff_id"], str)
            or len(value["handoff_id"]) > 256
        )
    ):
        raise ValueError("invalid supervised dispatch result handoff_id")
    for field in ("worktree_path", "branch"):
        if field in value and (
            not isinstance(value[field], str) or not value[field]
        ):
            raise ValueError(f"invalid supervised dispatch result {field}")
    if "evidence" in value:
        evidence = value["evidence"]
        if not isinstance(evidence, dict) or set(evidence) - {
            "loop_state_path",
            "commit",
            "loop_state_digest",
        }:
            raise ValueError("invalid supervised dispatch result evidence")
        if not isinstance(evidence.get("loop_state_path"), str) or not evidence["loop_state_path"]:
            raise ValueError("invalid supervised dispatch result loop_state_path")
        if (
            not isinstance(evidence.get("commit"), str)
            or _HEX_40.fullmatch(evidence["commit"]) is None
        ):
            raise ValueError("invalid supervised dispatch result commit")
        if (
            not isinstance(evidence.get("loop_state_digest"), str)
            or _HEX_64.fullmatch(evidence["loop_state_digest"]) is None
        ):
            raise ValueError("invalid supervised dispatch result loop_state_digest")
    if outcome in {"success", "parked"}:
        required = {"worktree_path", "branch", "evidence"}
        if not required <= value.keys():
            raise ValueError(f"invalid {outcome} dispatch result evidence")
    if outcome == "success" and (
        not isinstance(value.get("handoff_id"), str) or not value["handoff_id"]
    ):
        raise ValueError("invalid success dispatch result handoff_id")
    if outcome == "parked":
        parked = value.get("parked")
        if (
            not isinstance(parked, dict)
            or set(parked) - {"kind", "reason", "gate", "deadline", "resume_hint"}
            or parked.get("kind") not in {"pending_gate", "policy_pause"}
            or not isinstance(parked.get("reason"), str)
            or not parked["reason"]
            or len(parked["reason"]) > 1024
            or not _valid_nullable_string(parked, "gate", 128)
            or not _valid_nullable_string(parked, "resume_hint", 512)
            or not _valid_nullable_date_time(parked, "deadline")
        ):
            raise ValueError("invalid parked dispatch result")
    elif "parked" in value:
        raise ValueError("non-parked dispatch result cannot contain parked state")
    return value


def _valid_nullable_string(value: Mapping[str, Any], field: str, limit: int) -> bool:
    candidate = value.get(field)
    return field not in value or candidate is None or (
        isinstance(candidate, str) and len(candidate) <= limit
    )


def _valid_nullable_date_time(value: Mapping[str, Any], field: str) -> bool:
    candidate = value.get(field)
    if field not in value or candidate is None:
        return True
    if not isinstance(candidate, str) or _DATE_TIME.fullmatch(candidate) is None:
        return False
    try:
        datetime.fromisoformat(candidate.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return False
    return True


def _result_digest(result: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        result,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _new_application_journal(result: Mapping[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": 1,
        "state": "result_bound",
        "result": copy.deepcopy(dict(result)),
        "result_digest": _result_digest(result),
        "bound_at": now,
    }


def _advance_application_journal(journal: dict[str, Any], state: str) -> None:
    current = journal.get("state")
    if current not in _APPLICATION_STATES or state not in _APPLICATION_STATES:
        raise ValueError("invalid delegated application journal state")
    if _APPLICATION_STATES.index(state) < _APPLICATION_STATES.index(current):
        raise ValueError("delegated application journal cannot move backward")
    journal["state"] = state
    timestamp_field = {
        "callback_started": "callback_started_at",
        "callback_acknowledged": "callback_acknowledged_at",
        "terminal_persisted": "terminal_persisted_at",
        "effects_applied": "effects_applied_at",
    }.get(state)
    if timestamp_field is not None:
        journal.setdefault(timestamp_field, datetime.now(timezone.utc).isoformat())


def _bound_application_journal(
    attempt: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any] | None:
    journal = attempt.get("application_journal")
    if journal is None:
        return None
    prior_result = journal.get("result") if isinstance(journal, dict) else None
    prior_generation = (
        prior_result.get("lease_generation") if isinstance(prior_result, dict) else None
    )
    current_generation = result.get("lease_generation")
    if (
        attempt.get("status") == "launched"
        and isinstance(attempt.get("continuation"), dict)
        and isinstance(journal, dict)
        and journal.get("state") == "effects_applied"
        and isinstance(prior_result, dict)
        and prior_result.get("outcome") == "parked"
        and isinstance(prior_generation, int)
        and isinstance(current_generation, int)
        and prior_generation < current_generation == attempt.get("lease_generation")
        and all(
            prior_result.get(field) == result.get(field)
            for field in ("dispatch_id", "change_id", "attempt")
        )
    ):
        return None
    if (
        not isinstance(journal, dict)
        or journal.get("result") != result
        or journal.get("result_digest") != _result_digest(result)
    ):
        raise ValueError(f"bound dispatch result mismatch for {attempt['dispatch_id']}")
    return journal


def _batch_attempts(checkpoint: Any, batch_id: str) -> list[dict[str, Any]]:
    if not isinstance(batch_id, str) or _BATCH_ID.fullmatch(batch_id) is None:
        raise ValueError(f"invalid delegated batch id: {batch_id}")
    prefix = f"{batch_id}:"
    attempts = [
        attempt
        for attempt in checkpoint.dispatch_attempts
        if str(attempt.get("dispatch_id", "")).startswith(prefix)
    ]
    if not attempts:
        raise ValueError(f"unknown delegated batch: {batch_id}")
    return attempts


def _validate_exact_result(
    attempt: Mapping[str, Any],
    result: Mapping[str, Any],
) -> None:
    for field in ("change_id", "attempt", "lease_generation"):
        if result[field] != attempt[field]:
            raise ValueError(f"{field} mismatch for dispatch {attempt['dispatch_id']}")
    isolation = attempt["isolation"]
    for field in ("worktree_path", "branch"):
        if field in result and result[field] != isolation[field]:
            raise ValueError(f"{field} mismatch for dispatch {attempt['dispatch_id']}")


def _dispatch_context(
    roadmap_id: str,
    attempt: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    context = copy.deepcopy(attempt["context"])
    context.update(
        {
            "item_id": attempt["item_id"],
            "roadmap_id": roadmap_id,
            "change_id": attempt["change_id"],
            "dispatch_id": attempt["dispatch_id"],
            "attempt": attempt["attempt"],
            "lease_generation": attempt["lease_generation"],
            "scope": copy.deepcopy(attempt["scope"]),
            "isolation": copy.deepcopy(attempt["isolation"]),
            "execution_mode": "delegated_lifecycle",
            "dispatch_result": copy.deepcopy(result),
        }
    )
    return context


def _terminal_attempt(
    attempt: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    terminal = copy.deepcopy(dict(attempt))
    now = datetime.now(timezone.utc).isoformat()
    if "lease" in terminal:
        terminal["lease"]["state"] = "released"
    outcome = result["outcome"]
    terminal.update(outcome=outcome, resolved_at=now)
    if outcome == "success":
        terminal.update(status="completed", handoff_id=result["handoff_id"])
    elif outcome == "parked":
        terminal.update(status="parked", parked=copy.deepcopy(result["parked"]))
    else:
        terminal["status"] = "failed"
    terminal.pop("continuation", None)
    journal = terminal.get("application_journal")
    if not isinstance(journal, dict):
        raise ValueError("terminal dispatch attempt requires an application journal")
    _advance_application_journal(journal, "terminal_persisted")
    validate_delegated_dispatch_attempt(terminal)
    return terminal


def apply_delegated_batch(
    workspace: Path,
    batch_id: str,
    results: Sequence[Mapping[str, Any]],
    dispatch_fn: DispatchFn,
    *,
    repo_root: Path,
    gate_evaluator: GateEvaluator | None = None,
) -> dict[str, Any]:
    """Validate and apply one exact persisted batch through ``dispatch_fn`` once."""
    roadmap, manager, checkpoint = _load_or_create_execution_state(workspace, repo_root)
    attempts = _batch_attempts(checkpoint, batch_id)
    if all(
        attempt["status"] in _TERMINAL_ATTEMPT_STATUSES
        and attempt.get("application_journal", {}).get("state") == "effects_applied"
        for attempt in attempts
    ):
        raise ValueError(f"delegated batch already applied: {batch_id}")

    validated = [_validate_dispatch_result(result) for result in results]
    dispatch_ids = [result["dispatch_id"] for result in validated]
    if len(dispatch_ids) != len(set(dispatch_ids)):
        raise ValueError("duplicate dispatch result")
    expected_ids = {attempt["dispatch_id"] for attempt in attempts}
    if set(dispatch_ids) != expected_ids:
        raise ValueError("result membership mismatch for delegated batch")
    result_by_id = {result["dispatch_id"]: result for result in validated}
    for attempt in attempts:
        result = result_by_id[attempt["dispatch_id"]]
        _validate_exact_result(attempt, result)
        _bound_application_journal(attempt, result)
        if attempt["status"] in _TERMINAL_ATTEMPT_STATUSES:
            if attempt.get("outcome") != result["outcome"]:
                raise ValueError(f"terminal outcome mismatch for {attempt['dispatch_id']}")
        elif attempt["status"] != "launched":
            raise ValueError(f"dispatch attempt not launched: {attempt['dispatch_id']}")

    completed: list[str] = []
    failed: list[str] = []
    parked: list[str] = []
    gate_decisions: list[dict[str, Any]] = []
    replan_state: dict[str, Any] = {}
    by_id = {item.item_id: item for item in roadmap.items}
    for attempt in attempts:
        result = result_by_id[attempt["dispatch_id"]]
        journal = _bound_application_journal(attempt, result)
        if attempt["status"] in _TERMINAL_ATTEMPT_STATUSES:
            if journal is None:
                journal = _new_application_journal(result)
                for state in (
                    "callback_started",
                    "callback_acknowledged",
                    "terminal_persisted",
                ):
                    _advance_application_journal(journal, state)
                attempt["application_journal"] = journal
                validate_delegated_dispatch_attempt(attempt)
                manager.save(checkpoint)
            elif journal["state"] not in {"terminal_persisted", "effects_applied"}:
                raise ValueError(
                    f"terminal application journal mismatch for {attempt['dispatch_id']}"
                )
        else:
            if journal is None:
                journal = _new_application_journal(result)
                attempt["application_journal"] = journal
                validate_delegated_dispatch_attempt(attempt)
                manager.save(checkpoint)

            should_dispatch = False
            if journal["state"] == "result_bound":
                _advance_application_journal(journal, "callback_started")
                validate_delegated_dispatch_attempt(attempt)
                manager.save(checkpoint)
                should_dispatch = True
            elif journal["state"] == "callback_started":
                # Invocation may already have happened. The bound result is
                # authoritative, so recovery favors at-most-once callback delivery.
                pass
            elif journal["state"] != "callback_acknowledged":
                raise ValueError(
                    f"launched application journal mismatch for {attempt['dispatch_id']}"
                )

            if should_dispatch:
                context = _dispatch_context(roadmap.roadmap_id, attempt, result)
                dispatched_outcome, replan_signal = _normalize_outcome(
                    dispatch_fn(attempt["item_id"], "autopilot", context)
                )
                if dispatched_outcome != result["outcome"]:
                    raise ValueError(
                        f"dispatch outcome mismatch for {attempt['dispatch_id']}"
                    )
                if replan_signal != bool(result.get("replan", False)):
                    raise ValueError(
                        f"dispatch replan mismatch for {attempt['dispatch_id']}"
                    )

            if journal["state"] == "callback_started":
                _advance_application_journal(journal, "callback_acknowledged")
                validate_delegated_dispatch_attempt(attempt)
                manager.save(checkpoint)

            terminal = _terminal_attempt(attempt, result)
            attempt.clear()
            attempt.update(terminal)
            journal = attempt["application_journal"]
            manager.save(checkpoint)

        if journal["state"] == "effects_applied":
            continue
        item_id = attempt["item_id"]
        dispatched_outcome = result["outcome"]
        replan_signal = bool(result.get("replan", False))
        if dispatched_outcome == "success":
            manager.complete_item(checkpoint, item_id)
            by_id[item_id].status = ItemStatus.COMPLETED
            _write_success_learning(workspace, item_id)
            completed.append(item_id)
        elif dispatched_outcome == "parked":
            by_id[item_id].status = ItemStatus.IN_PROGRESS
            parked.append(item_id)
        else:
            reason = (
                dispatched_outcome.split(":", 1)[1]
                if ":" in dispatched_outcome
                else dispatched_outcome
            )
            _handle_failure(
                item_id=item_id,
                reason=reason,
                replan=replan_signal,
                roadmap=roadmap,
                checkpoint=checkpoint,
                mgr=manager,
                workspace=workspace,
                repo_root=repo_root,
                gate_evaluator=gate_evaluator,
                gate_decisions=gate_decisions,
                replan_state=replan_state,
            )
            failed.append(item_id)
        save_roadmap(roadmap, workspace / "roadmap.yaml", overwrite=True)
        _advance_application_journal(journal, "effects_applied")
        validate_delegated_dispatch_attempt(attempt)
        manager.save(checkpoint)

    return {
        "batch_id": batch_id,
        "completed_item_ids": completed,
        "failed_item_ids": failed,
        "parked_item_ids": parked,
        "gate_decisions": gate_decisions,
    }


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
    registry_provider: Callable[..., dict[str, Any]] | None = None,
    agents_yaml_fallback: Callable[..., list[dict[str, Any]]] | None = None,
    routing_location: str | None = None,
    routing_resolver: RoutingResolver | None = None,
    routing_reconciler: RoutingReconciler | None = None,
    resume_escalation: bool = False,
    max_iterations: int = 1000,
    max_no_progress: int = 3,
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
    routing_resolver:
        Host-owned bridge adapter invoked before each dispatch. A supplied
        resolver must return a durable dg-04 decision with a canonical dg-05
        assignment; absence or malformed data fails closed before dispatch.
    routing_reconciler:
        Host-owned ledger lookup for a prepared routed attempt found on resume.
        Missing, nonterminal, or mismatched evidence parks before redispatch.
    max_iterations:
        Positive global host-dispatch cap persisted in checkpoint safety state.
    max_no_progress:
        Positive cap for unchanged item/phase/correlated-ledger fingerprints.
    resume_escalation:
        Explicit host acknowledgement that clears a durable execution pause so
        its prepared attempt can be reconciled before any new dispatch.

    Returns
    -------
    Summary dict with completed_count, failed_count, blocked_count,
    skipped_count, superseded_count, status, policy_decisions, and
    gate_decisions. When a replan request was emitted the status is
    ``replan_requested`` and ``replan_request`` describes the handoff file.
    """
    dispatch = dispatch_fn or _default_dispatch
    for name, value in (
        ("max_iterations", max_iterations),
        ("max_no_progress", max_no_progress),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    registry = registry_provider or try_list_vendors
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

    if (
        resume_escalation
        and checkpoint.pause_state.get("paused")
        and checkpoint.execution_safety.get("escalation")
    ):
        checkpoint.pause_state = {}
        checkpoint.execution_safety.pop("escalation", None)
        mgr.save(checkpoint)


    if _pause_is_active(checkpoint.pause_state):
        logger.info(
            "roadmap.policy_pause_active: vendor=%s resume_at=%s",
            checkpoint.pause_state.get("blocked_vendor"),
            checkpoint.pause_state.get("expected_resume_at"),
        )
        return _build_summary(
            roadmap,
            checkpoint,
            policy_decisions,
            gate_decisions,
            replan_state,
        )
    if checkpoint.pause_state.get("paused"):
        checkpoint.pause_state = {}
        mgr.save(checkpoint)

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
            registry_provider=registry,
            agents_yaml_fallback=agents_yaml_fallback,
            routing_location=routing_location,
            routing_resolver=routing_resolver,
            routing_reconciler=routing_reconciler,
            max_iterations=max_iterations,
            max_no_progress=max_no_progress,
        )

        if checkpoint.pause_state.get("paused"):
            save_roadmap(roadmap, workspace / "roadmap.yaml", overwrite=True)
            break

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
    registry_provider: Callable[..., dict[str, Any]],
    agents_yaml_fallback: Callable[..., list[dict[str, Any]]] | None,
    routing_location: str | None,
    routing_resolver: RoutingResolver | None,
    routing_reconciler: RoutingReconciler | None,
    max_iterations: int,
    max_no_progress: int,
) -> bool:
    """Walk an item through its phases. Returns True if item completed."""
    start_idx = _ITEM_PHASES.index(start_phase) if start_phase in _ITEM_PHASES else 0
    item = next(candidate for candidate in roadmap.items if candidate.item_id == item_id)

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
        selected_agent_id: str | None = None
        if routing_resolver is None and checkpoint.routing_attempts:
            _park_execution(
                checkpoint=checkpoint,
                manager=mgr,
                kind="routing_resolution_failed",
                reason="Routed checkpoint requires routing_resolver before resume",
            )
            return False
        prior_phase_limits = [
            attempt
            for attempt in checkpoint.routing_attempts
            if attempt.get("item_id") == item_id
            and attempt.get("phase") == phase.value
            and attempt.get("status") == "vendor_limit"
            and attempt.get("policy_action") == "switch"
        ]
        routed_exclusions = [
            str(attempt["assignment"]["agent_id"])
            for attempt in prior_phase_limits
        ]
        routed_switch_count = sum(
            1
            for attempt in checkpoint.routing_attempts
            if attempt.get("item_id") == item_id
            and attempt.get("status") == "vendor_limit"
            and attempt.get("policy_action") == "switch"
        )
        prior_routing_fail_closed = any(
            attempt.get("item_id") == item_id
            and attempt.get("status") == "vendor_limit"
            and attempt.get("policy_action") == "fail_closed"
            for attempt in checkpoint.routing_attempts
        )
        incomplete_routing_policy = any(
            attempt.get("item_id") == item_id
            and attempt.get("status") == "vendor_limit"
            and attempt.get("policy_action") is None
            for attempt in checkpoint.routing_attempts
        )
        if routing_resolver is not None:
            if incomplete_routing_policy:
                _park_execution(
                    checkpoint=checkpoint,
                    manager=mgr,
                    kind="ledger_reconciliation_required",
                    reason="Vendor-limit attempt is missing a durable policy action",
                )
                return False
            prepared = [
                attempt
                for attempt in checkpoint.routing_attempts
                if attempt.get("item_id") == item_id
                and attempt.get("phase") == phase.value
                and attempt.get("status") == "prepared"
            ]
            if prepared:
                attempt = prepared[-1]
                try:
                    reconciled = (
                        routing_reconciler(copy.deepcopy(attempt))
                        if routing_reconciler is not None
                        else None
                    )
                except Exception:
                    logger.warning(
                        "item.routing_reconciliation_failed: item=%s phase=%s",
                        item_id,
                        phase.value,
                        exc_info=True,
                    )
                    reconciled = None
                if not isinstance(reconciled, Mapping):
                    _park_execution(
                        checkpoint=checkpoint,
                        manager=mgr,
                        kind="ledger_reconciliation_required",
                        reason="Prepared routed attempt has no authoritative ledger result",
                    )
                    return False
                outcome, _ = _normalize_outcome(reconciled)
                is_vendor_limit = outcome.startswith("vendor_limit:")
                is_failed = outcome.startswith("failed:")
                if outcome != "success" and not is_vendor_limit and not is_failed:
                    _park_execution(
                        checkpoint=checkpoint,
                        manager=mgr,
                        kind="ledger_reconciliation_required",
                        reason="Prepared routed attempt has no terminal ledger result",
                    )
                    return False
                expected_status = "completed"
                failure_reason = None
                policy_decision = None
                policy_resume_at = None
                if is_vendor_limit:
                    expected_status = "vendor_limit"
                    parts = outcome.split(":", 2)
                    vendor = parts[1] if len(parts) > 1 else "unknown"
                    reason = parts[2] if len(parts) > 2 else "rate limit"
                    policy_decision = _routing_policy_decision(
                        roadmap,
                        vendor=vendor,
                        reason=reason,
                        switch_count=routed_switch_count,
                    )
                    policy_resume_at = _capacity_reset_at(reconciled)
                elif is_failed:
                    expected_status = "failed"
                    failure_reason = outcome[len("failed:"):]
                try:
                    observed_agent_id = _finish_routing_attempt(
                        checkpoint=checkpoint,
                        manager=mgr,
                        routing=attempt,
                        result=reconciled,
                        expected_ledger_status=expected_status,
                        failure_reason=failure_reason,
                        policy_decision=policy_decision,
                        policy_resume_at=policy_resume_at,
                    )
                except (StopIteration, ValueError):
                    _park_execution(
                        checkpoint=checkpoint,
                        manager=mgr,
                        kind="ledger_reconciliation_mismatch",
                        reason="Prepared routed attempt ledger proof did not match",
                    )
                    return False
                if outcome == "success":
                    continue
                if is_failed:
                    _fail(failure_reason or "Routed attempt failed")
                    return False
                decision = policy_decision
                if decision is None:
                    _park_execution(
                        checkpoint=checkpoint,
                        manager=mgr,
                        kind="ledger_reconciliation_mismatch",
                        reason="Vendor-limit result has no policy decision",
                    )
                    return False
                policy_decisions.append({
                    "item_id": item_id,
                    "phase": phase.value,
                    "decision": {
                        "action": decision.action,
                        "reason": decision.reason,
                        "from_vendor": decision.from_vendor,
                        "to_vendor": decision.to_vendor,
                        "to_agent_id": decision.to_agent_id,
                        "expected_cost_delta_usd": decision.expected_cost_delta_usd,
                        "cost_guard": decision.cost_guard,
                        "legacy_provider_scope": False,
                        "durable_persistence": "routing_attempt_ledger",
                    },
                })
                if on_policy_decision:
                    on_policy_decision(decision)
                logger.info(
                    "policy.applied: item=%s action=%s vendor=%s reason=%s cost_delta=%s",
                    item_id,
                    decision.action,
                    decision.from_vendor,
                    decision.reason,
                    decision.expected_cost_delta_usd,
                )

                if decision.action == "wait":
                    return False
                if decision.action == "fail_closed":
                    # _finish_routing_attempt committed the pause and
                    # escalation atomically with the terminal ledger record.
                    return False

                routed_switch_count += 1
                routed_exclusions.append(observed_agent_id)

            if (
                routed_switch_count > roadmap.policy.max_switch_attempts_per_item
                or (
                    prior_routing_fail_closed
                    and (
                        roadmap.policy.cost_ceiling_usd is not None
                        or routed_switch_count
                        >= roadmap.policy.max_switch_attempts_per_item
                    )
                )
            ):
                reason = (
                    "Configured routing cost ceiling still cannot be evaluated; "
                    "remove or change the ceiling before resuming"
                    if prior_routing_fail_closed
                    and roadmap.policy.cost_ceiling_usd is not None
                    else (
                        "Routing switch retry cap remains exhausted; "
                        "increase the item policy limit before resuming"
                    )
                )
                _park_execution(
                    checkpoint=checkpoint,
                    manager=mgr,
                    kind="routing_switch_cap",
                    reason=reason,
                )
                return False

        while True:
            if not _before_host_dispatch(
                checkpoint=checkpoint,
                manager=mgr,
                max_iterations=max_iterations,
                max_no_progress=max_no_progress,
            ):
                return False

            context = {
                "item_id": item_id,
                "roadmap_id": roadmap.roadmap_id,
                "completed_items": list(checkpoint.completed_items),
            }
            if selected_agent_id is not None:
                # dispatch_agent_id is the roadmap routing contract;
                # agent_id is the additive provider/phase carrier field.
                context["dispatch_agent_id"] = selected_agent_id
                context["agent_id"] = selected_agent_id
            if routed_exclusions:
                context["routing_exclusions"] = {
                    "agent_ids": list(routed_exclusions),
                }

            if routing_resolver is not None:
                try:
                    resolved = routing_resolver(item, phase.value, copy.deepcopy(context))
                    if resolved is None:
                        raise ValueError("resolver returned no routing decision")
                    routing = _validated_routing_decision(resolved)
                    prior_decision_ids = {
                        str(attempt.get("decision_id"))
                        for attempt in checkpoint.routing_attempts
                        if attempt.get("item_id") == item_id
                        and attempt.get("phase") == phase.value
                    }
                    if routing["decision_id"] in prior_decision_ids:
                        raise ValueError(
                            "resolver reused a routing decision for the same item phase"
                        )
                    routed_agent_id = str(routing["assignment"]["agent_id"])
                    if routed_agent_id in routed_exclusions:
                        raise ValueError("resolver returned an excluded routing lane")
                except Exception as exc:
                    logger.warning(
                        "item.routing_failed: item=%s phase=%s error=%s",
                        item_id,
                        phase.value,
                        type(exc).__name__,
                    )
                    _park_execution(
                        checkpoint=checkpoint,
                        manager=mgr,
                        kind="routing_resolution_failed",
                        reason=f"Routing resolution failed: {type(exc).__name__}",
                    )
                    return False
                context["routing"] = _prepare_routing_attempt(
                    roadmap_id=roadmap.roadmap_id,
                    item_id=item_id,
                    phase=phase.value,
                    decision=routing,
                    checkpoint=checkpoint,
                    manager=mgr,
                )
                context["isolation"] = routing["assignment"]["isolation"]

            dispatch_result = dispatch(item_id, phase.value, copy.deepcopy(context))
            outcome, replan_signal = _normalize_outcome(dispatch_result)
            dispatch_metadata = (
                dispatch_result if isinstance(dispatch_result, Mapping) else {}
            )
            dispatch_agent_id = (
                dispatch_metadata.get("dispatch_agent_id")
                or dispatch_metadata.get("agent_id")
            )
            capacity_reset_at = _capacity_reset_at(dispatch_metadata)
            if routing_resolver is not None and (
                outcome == "success"
                or outcome.startswith("vendor_limit:")
                or outcome.startswith("failed:")
            ):
                expected_status = "completed"
                failure_reason = None
                policy_decision = None
                if outcome.startswith("vendor_limit:"):
                    expected_status = "vendor_limit"
                    parts = outcome.split(":", 2)
                    vendor = parts[1] if len(parts) > 1 else "unknown"
                    reason = parts[2] if len(parts) > 2 else "rate limit"
                    policy_decision = _routing_policy_decision(
                        roadmap,
                        vendor=vendor,
                        reason=reason,
                        switch_count=routed_switch_count,
                    )
                elif outcome.startswith("failed:"):
                    expected_status = "failed"
                    failure_reason = outcome[len("failed:"):]
                try:
                    observed_agent_id = _finish_routing_attempt(
                        checkpoint=checkpoint,
                        manager=mgr,
                        routing=context["routing"],
                        result=dispatch_metadata,
                        expected_ledger_status=expected_status,
                        failure_reason=failure_reason,
                        policy_decision=policy_decision,
                        policy_resume_at=capacity_reset_at,
                    )
                except (StopIteration, ValueError) as exc:
                    _fail(f"Routing completion rejected: {type(exc).__name__}")
                    return False

                if outcome.startswith("vendor_limit:"):
                    decision = policy_decision
                    if decision is None:
                        _fail("Vendor-limit result has no policy decision")
                        return False
                    policy_decisions.append({
                        "item_id": item_id,
                        "phase": phase.value,
                        "decision": {
                            "action": decision.action,
                            "reason": decision.reason,
                            "from_vendor": decision.from_vendor,
                            "to_vendor": decision.to_vendor,
                            "to_agent_id": decision.to_agent_id,
                            "expected_cost_delta_usd": decision.expected_cost_delta_usd,
                            "cost_guard": decision.cost_guard,
                            "legacy_provider_scope": False,
                            "durable_persistence": "routing_attempt_ledger",
                        },
                    })
                    if on_policy_decision:
                        on_policy_decision(decision)
                    logger.info(
                        "policy.applied: item=%s action=%s vendor=%s reason=%s cost_delta=%s",
                        item_id,
                        decision.action,
                        decision.from_vendor,
                        decision.reason,
                        decision.expected_cost_delta_usd,
                    )

                    if decision.action == "wait":
                        return False
                    if decision.action == "fail_closed":
                        # _finish_routing_attempt committed the pause and
                        # escalation atomically with the terminal ledger record.
                        return False

                    routed_switch_count += 1
                    routed_exclusions.append(observed_agent_id)
                    continue


            if routing_resolver is not None and not (
                outcome == "success"
                or outcome.startswith("vendor_limit:")
                or outcome.startswith("failed:")
            ):
                try:
                    _reject_routing_attempt(
                        checkpoint=checkpoint,
                        manager=mgr,
                        routing=context["routing"],
                        reason=f"unknown_outcome:{outcome}",
                    )
                except StopIteration:
                    _fail("Routing attempt record missing")
                    return False


            if outcome == "success":
                logger.info(
                    "item.phase_success: item=%s phase=%s", item_id, phase.value
                )
                break

            if outcome.startswith("failed:"):
                reason = outcome[len("failed:"):]
                logger.warning(
                    "item.phase_failed: item=%s phase=%s reason=%s",
                    item_id,
                    phase.value,
                    reason,
                )
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
                    registry_provider=registry_provider,
                    agents_yaml_fallback=agents_yaml_fallback,
                    phase=phase.value,
                    dispatch_agent_id=(
                        str(dispatch_agent_id)
                        if dispatch_agent_id is not None
                        else None
                    ),
                    model=dispatch_metadata.get("model"),
                    prompt_tokens=dispatch_metadata.get("prompt_tokens"),
                    completion_tokens=dispatch_metadata.get("completion_tokens"),
                    location=routing_location,
                    reset_at=capacity_reset_at,
                )
                report_status = dispatch_metadata.get("capacity_report_status")
                if dispatch_agent_id is None:
                    durable_persistence = "skipped_ambiguous"
                elif report_status in {"persisted", "failed", "skipped"}:
                    durable_persistence = str(report_status)
                else:
                    durable_persistence = "delegated_unconfirmed"
                policy_decisions.append({
                    "item_id": item_id,
                    "phase": phase.value,
                    "decision": {
                        "action": decision.action,
                        "reason": decision.reason,
                        "from_vendor": decision.from_vendor,
                        "to_vendor": decision.to_vendor,
                        "to_agent_id": decision.to_agent_id,
                        "expected_cost_delta_usd": decision.expected_cost_delta_usd,
                        "cost_guard": decision.cost_guard,
                        "legacy_provider_scope": dispatch_agent_id is None,
                        "durable_persistence": durable_persistence,
                    },
                })
                if on_policy_decision:
                    on_policy_decision(decision)

                if decision.action == "fail_closed":
                    # A vendor-policy stop is not a plan problem.
                    _fail(f"Policy fail_closed: {decision.reason}")
                    return False
                if decision.action == "wait":
                    _persist_policy_pause(
                        checkpoint=checkpoint,
                        mgr=mgr,
                        decision=decision,
                        expected_resume_at=capacity_reset_at,
                    )
                    return False

                # Retry this exact phase. Switches carry the selected lane through
                # both the roadmap and provider field names at the boundary.
                if decision.action == "switch":
                    selected_agent_id = decision.to_agent_id
                elif dispatch_agent_id is not None:
                    selected_agent_id = str(dispatch_agent_id)
                logger.info(
                    "policy.applied: item=%s action=%s vendor=%s->%s",
                    item_id,
                    decision.action,
                    decision.from_vendor,
                    decision.to_vendor,
                )
                continue

            # Unknown outcome -- treat as failure.
            logger.warning(
                "item.unknown_outcome: item=%s outcome=%s", item_id, outcome
            )
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

def _parse_reset_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _capacity_reset_at(metadata: Mapping[str, Any]) -> str | None:
    reset_at = metadata.get("capacity_reset_at")
    if _parse_reset_at(reset_at) is not None:
        return str(reset_at)

    retry_after = metadata.get("capacity_retry_after_seconds")
    if (
        isinstance(retry_after, (int, float))
        and not isinstance(retry_after, bool)
        and retry_after >= 0
    ):
        return (
            datetime.now(timezone.utc) + timedelta(seconds=float(retry_after))
        ).isoformat()
    return None


def _pause_is_active(pause_state: Mapping[str, Any]) -> bool:
    if not pause_state.get("paused"):
        return False
    expected_resume_at = pause_state.get("expected_resume_at")
    parsed = _parse_reset_at(expected_resume_at)
    if parsed is None:
        return True
    return datetime.now(timezone.utc) < parsed


def _persist_policy_pause(
    *,
    checkpoint: Any,
    mgr: CheckpointManager,
    decision: PolicyDecision,
    expected_resume_at: str | None,
) -> None:
    pause_state: dict[str, Any] = {
        "paused": True,
        "reason": decision.reason,
        "paused_at": datetime.now(timezone.utc).isoformat(),
        "blocked_vendor": decision.from_vendor,
    }
    if expected_resume_at is not None:
        pause_state["expected_resume_at"] = expected_resume_at
    checkpoint.pause_state = sanitize_dict(pause_state)
    mgr.save(checkpoint)


def _handle_vendor_limit(
    roadmap: Roadmap,
    item_id: str,
    vendor: str,
    reason: str,
    switch_attempts: dict[str, int],
    *,
    registry_provider: Callable[..., dict[str, Any]] = try_list_vendors,
    agents_yaml_fallback: Callable[..., list[dict[str, Any]]] | None = None,
    phase: str = "implementing",
    dispatch_agent_id: str | None = None,
    model: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    location: str | None = None,
    reset_at: str | None = None,
) -> PolicyDecision:
    """Honor WAIT directly or select an exact alternate registry lane.

    WAIT does not require registry availability because it preserves the current lane.
    """
    vendor_limit = VendorLimit(vendor=vendor, reason=reason, reset_at=reset_at)
    if roadmap.policy.default_action == PolicyAction.WAIT:
        return select_registry_lane(
            policy=roadmap.policy,
            vendor_limit=vendor_limit,
            lanes=(),
            switch_attempts=switch_attempts.get(item_id, 0),
        )

    item = next((candidate for candidate in roadmap.items if candidate.item_id == item_id), None)
    capability = item.capability if item is not None else None
    archetype = {
        "planning": "architect",
        "implementing": "implementer",
        "reviewing": "reviewer",
        "validating": "validator",
    }.get(phase)
    dispatch_mode = "review" if phase == "reviewing" else "alternative"
    filters = {
        "capability": capability,
        "archetype": archetype,
        "dispatch_mode": dispatch_mode,
        "location": location,
        "available_only": False,
    }
    response = registry_provider(**filters)
    allow_unknown = False
    lanes: list[dict[str, Any]] = []
    if response.get("status") == "ok":
        payload = response.get("response")
        if isinstance(payload, dict) and isinstance(payload.get("vendors"), list):
            lanes = [lane for lane in payload["vendors"] if isinstance(lane, dict)]
        else:
            response = {"status": "error", "reason": "malformed_response"}
    if response.get("status") != "ok":
        if agents_yaml_fallback is None:
            return PolicyDecision(
                action="fail_closed",
                reason=(
                    "Vendor registry unavailable: "
                    f"{response.get('reason') or response.get('error') or 'unknown'}"
                ),
                from_vendor=vendor,
                cost_guard="unavailable",
            )
        lanes = agents_yaml_fallback(**filters)
        allow_unknown = True
        logger.warning("roadmap.registry_fallback: item=%s source=agents_yaml", item_id)

    eligible = filter_registry_lanes(
        lanes,
        capability=capability,
        archetype=archetype,
        dispatch_mode=dispatch_mode,
        location=location,
        model=model,
        allow_unknown=allow_unknown,
    )
    excluded_agent_ids = {dispatch_agent_id} if dispatch_agent_id else set()
    excluded_policy_vendors = set()
    if dispatch_agent_id is None:
        excluded_policy_vendors.add(vendor)
        logger.warning(
            "roadmap.vendor_limit_ambiguous: item=%s policy_vendor=%s "
            "durable_persistence=skipped",
            item_id,
            vendor,
        )
    decision = select_registry_lane(
        policy=roadmap.policy,
        vendor_limit=vendor_limit,
        lanes=eligible,
        switch_attempts=switch_attempts.get(item_id, 0),
        from_agent_id=dispatch_agent_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        allow_unknown=allow_unknown,
        excluded_agent_ids=excluded_agent_ids,
        excluded_policy_vendors=excluded_policy_vendors,
    )
    if decision.action == "switch":
        switch_attempts[item_id] = switch_attempts.get(item_id, 0) + 1
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
    if checkpoint.pause_state.get("paused"):
        summary["status"] = "paused"
        summary["pause_state"] = copy.deepcopy(checkpoint.pause_state)
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

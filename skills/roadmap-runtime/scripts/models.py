"""Roadmap artifact models with JSON Schema validation.

Provides dataclasses for roadmap.yaml, checkpoint.json, and learning-log
entries, plus load/save helpers that validate against the contract schemas.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema paths (relative to repo root)
# ---------------------------------------------------------------------------
_SCHEMAS_DIR = "openspec/schemas"
ROADMAP_SCHEMA = f"{_SCHEMAS_DIR}/roadmap.schema.json"
CHECKPOINT_SCHEMA = f"{_SCHEMAS_DIR}/checkpoint.schema.json"
LEARNING_SCHEMA = f"{_SCHEMAS_DIR}/learning-log.schema.json"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class RoadmapStatus(str, Enum):
    PLANNING = "planning"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class ItemStatus(str, Enum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    REPLAN_REQUIRED = "replan_required"
    SKIPPED = "skipped"
    SUPERSEDED = "superseded"


class Effort(str, Enum):
    XS = "XS"
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"


class PolicyAction(str, Enum):
    WAIT = "wait_if_budget_exceeded"
    SWITCH = "switch_if_time_saved"


class DepEdgeSource(str, Enum):
    """How a dependency edge was inferred."""
    DETERMINISTIC = "deterministic"
    LLM = "llm"
    SPLIT = "split"
    EXPLICIT = "explicit"
    CEILING_SKIPPED = "ceiling-skipped"


class CheckpointPhase(str, Enum):
    PLANNING = "planning"
    IMPLEMENTING = "implementing"
    REVIEWING = "reviewing"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class LearningPhase(str, Enum):
    PLANNING = "planning"
    IMPLEMENTATION = "implementation"
    REVIEW = "review"
    VALIDATION = "validation"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class DepEdge:
    """A dependency edge with source attribution and rationale.

    Carries metadata about how the edge was inferred so operators can
    audit and prune the DAG.  DepEdge records are stored in the
    ``dep_edges`` field of ``RoadmapItem``; the parallel ``depends_on``
    field keeps plain IDs for backward compatibility.
    """

    id: str
    source: DepEdgeSource = DepEdgeSource.EXPLICIT
    rationale: str = ""
    confidence: str | None = None  # "low" | "medium" | "high", LLM only

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "source": self.source.value,
            "rationale": self.rationale,
        }
        if self.confidence is not None:
            d["confidence"] = self.confidence
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DepEdge:
        return cls(
            id=data["id"],
            source=DepEdgeSource(data.get("source", "explicit")),
            rationale=data.get("rationale", ""),
            confidence=data.get("confidence"),
        )


@dataclass
class Scope:
    """Optional scope declaration for deterministic dependency inference.

    When both items in a pair declare scope, Tier A (deterministic
    overlap) can add or skip edges without LLM calls.
    """

    write_allow: list[str] = field(default_factory=list)
    read_allow: list[str] = field(default_factory=list)
    lock_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.write_allow:
            d["write_allow"] = self.write_allow
        if self.read_allow:
            d["read_allow"] = self.read_allow
        if self.lock_keys:
            d["lock_keys"] = self.lock_keys
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scope:
        return cls(
            write_allow=data.get("write_allow", []),
            read_allow=data.get("read_allow", []),
            lock_keys=data.get("lock_keys", []),
        )


@dataclass
class Policy:
    default_action: PolicyAction = PolicyAction.WAIT
    cost_ceiling_usd: float | None = None
    max_switch_attempts_per_item: int = 2
    preferred_vendor: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"default_action": self.default_action.value}
        if self.cost_ceiling_usd is not None:
            d["cost_ceiling_usd"] = self.cost_ceiling_usd
        d["max_switch_attempts_per_item"] = self.max_switch_attempts_per_item
        if self.preferred_vendor is not None:
            d["preferred_vendor"] = self.preferred_vendor
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Policy:
        return cls(
            default_action=PolicyAction(data["default_action"]),
            cost_ceiling_usd=data.get("cost_ceiling_usd"),
            max_switch_attempts_per_item=data.get("max_switch_attempts_per_item", 2),
            preferred_vendor=data.get("preferred_vendor"),
        )


@dataclass
class RoadmapItem:
    item_id: str
    title: str
    status: ItemStatus
    priority: int
    effort: Effort
    depends_on: list[str] = field(default_factory=list)
    description: str | None = None
    rationale: str | None = None
    change_id: str | None = None
    acceptance_outcomes: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    blocked_by: list[str] = field(default_factory=list)
    learning_refs: list[str] = field(default_factory=list)
    dep_edges: list[DepEdge] = field(default_factory=list)
    scope: Scope | None = None
    # Cross-roadmap edges. Each entry is an item_ref '<roadmap-id>:<item-id>'.
    external_depends_on: list[str] = field(default_factory=list)
    superseded_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "item_id": self.item_id,
            "title": self.title,
            "status": self.status.value,
            "priority": self.priority,
            "effort": self.effort.value,
        }
        # Serialize depends_on: use rich DepEdge format when available,
        # plain string list otherwise (backward compatible).
        if self.dep_edges:
            d["depends_on"] = [e.to_dict() for e in self.dep_edges]
        else:
            d["depends_on"] = self.depends_on
        if self.description:
            d["description"] = self.description
        if self.rationale:
            d["rationale"] = self.rationale
        if self.change_id:
            d["change_id"] = self.change_id
        if self.acceptance_outcomes:
            d["acceptance_outcomes"] = self.acceptance_outcomes
        if self.failure_reason:
            d["failure_reason"] = self.failure_reason
        if self.blocked_by:
            d["blocked_by"] = self.blocked_by
        if self.learning_refs:
            d["learning_refs"] = self.learning_refs
        if self.scope:
            d["scope"] = self.scope.to_dict()
        if self.external_depends_on:
            d["external_depends_on"] = self.external_depends_on
        if self.superseded_by:
            d["superseded_by"] = self.superseded_by
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoadmapItem:
        # Normalize depends_on: accept both ["id", ...] and [{id, source, ...}, ...]
        raw_deps = data.get("depends_on", [])
        depends_on: list[str] = []
        dep_edges: list[DepEdge] = []
        for entry in raw_deps:
            if isinstance(entry, str):
                depends_on.append(entry)
            elif isinstance(entry, dict):
                edge = DepEdge.from_dict(entry)
                depends_on.append(edge.id)
                dep_edges.append(edge)

        raw_scope = data.get("scope")
        scope = Scope.from_dict(raw_scope) if raw_scope else None

        return cls(
            item_id=data["item_id"],
            title=data["title"],
            status=ItemStatus(data["status"]),
            priority=data["priority"],
            effort=Effort(data["effort"]),
            depends_on=depends_on,
            description=data.get("description"),
            rationale=data.get("rationale"),
            change_id=data.get("change_id"),
            acceptance_outcomes=data.get("acceptance_outcomes", []),
            failure_reason=data.get("failure_reason"),
            blocked_by=data.get("blocked_by", []),
            learning_refs=data.get("learning_refs", []),
            dep_edges=dep_edges,
            scope=scope,
            # `or []` rather than a .get default: YAML renders a key with an
            # empty value (`external_depends_on:`) as None, and list(None)
            # raises TypeError. That exception is swallowed by the tolerant
            # sibling loader, so one blank line in a roadmap.yaml would drop
            # the whole workspace from cross-roadmap resolution.
            external_depends_on=list(data.get("external_depends_on") or []),
            superseded_by=list(data.get("superseded_by") or []),
        )


@dataclass
class Roadmap:
    schema_version: int
    roadmap_id: str
    source_proposal: str
    items: list[RoadmapItem]
    created_at: str | None = None
    updated_at: str | None = None
    status: RoadmapStatus = RoadmapStatus.PLANNING
    policy: Policy = field(default_factory=Policy)
    refinements: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "roadmap_id": self.roadmap_id,
            "source_proposal": self.source_proposal,
            "status": self.status.value,
            "policy": self.policy.to_dict(),
            "items": [item.to_dict() for item in self.items],
        }
        if self.created_at:
            d["created_at"] = self.created_at
        if self.updated_at:
            d["updated_at"] = self.updated_at
        if self.refinements:
            d["refinements"] = [dict(record) for record in self.refinements]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Roadmap:
        return cls(
            schema_version=data["schema_version"],
            roadmap_id=data["roadmap_id"],
            source_proposal=data["source_proposal"],
            items=[RoadmapItem.from_dict(i) for i in data["items"]],
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            status=RoadmapStatus(data.get("status", "planning")),
            policy=Policy.from_dict(data["policy"]) if "policy" in data else Policy(),
            refinements=[dict(record) for record in (data.get("refinements") or [])],
        )

    def get_item(self, item_id: str) -> RoadmapItem | None:
        for item in self.items:
            if item.item_id == item_id:
                return item
        return None

    def ready_items(
        self,
        external_completed: set[str] | None = None,
        *,
        include_in_progress: bool = False,
    ) -> list[RoadmapItem]:
        """Return items ready to execute.

        An item is ready when its status is ``approved``, every in-roadmap
        ``depends_on`` id is completed, and every ``external_depends_on``
        item_ref appears in ``external_completed`` (the set of cross-roadmap
        item_refs whose referenced item has reached ``completed``). Pass the
        set produced by :func:`completed_external_refs`. When omitted, external
        prerequisites are treated as unmet, so an item carrying any
        ``external_depends_on`` edge is withheld until callers supply the set.

        ``include_in_progress`` additionally admits ``in_progress`` items —
        the view a status surface (e.g. the supervise digest) needs, where
        "ready" means "in the executable frontier" rather than "awaiting
        dispatch". This keeps consumers on one admission rule instead of
        hand-rolling copies that drift.

        ``superseded`` items are never ready (their status is not ``approved``).
        Neither is an item carrying a non-empty ``superseded_by`` edge, whatever
        its status: declaring that another roadmap's item took over this work is
        sufficient on its own. Keying only on ``status`` would schedule an item
        whose ``superseded_by`` edge was added without the paired status flip —
        a one-field edit away, and the resulting run would duplicate work the
        successor item owns.

        This method performs no file IO and does not mutate anything.
        """
        external_completed = external_completed or set()
        admitted = {ItemStatus.APPROVED}
        if include_in_progress:
            admitted.add(ItemStatus.IN_PROGRESS)
        completed_ids = {i.item_id for i in self.items if i.status == ItemStatus.COMPLETED}
        return [
            i for i in self.items
            if i.status in admitted
            and not i.superseded_by
            and all(dep in completed_ids for dep in i.depends_on)
            and all(ref in external_completed for ref in i.external_depends_on)
        ]

    def has_cycle(self) -> bool:
        """Check for cycles in the dependency DAG."""
        visited: set[str] = set()
        in_stack: set[str] = set()
        id_map = {i.item_id: i for i in self.items}

        def _dfs(item_id: str) -> bool:
            if item_id in in_stack:
                return True
            if item_id in visited:
                return False
            visited.add(item_id)
            in_stack.add(item_id)
            item = id_map.get(item_id)
            if item:
                for dep in item.depends_on:
                    if _dfs(dep):
                        return True
            in_stack.discard(item_id)
            return False

        return any(_dfs(i.item_id) for i in self.items)


@dataclass
class VendorSwitch:
    from_vendor: str
    to_vendor: str
    reason: str
    timestamp: str
    expected_cost_delta_usd: float | None = None
    observed_cost_delta_usd: float | None = None
    expected_latency_delta_seconds: float | None = None
    observed_latency_delta_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "from_vendor": self.from_vendor,
            "to_vendor": self.to_vendor,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }
        for attr in ("expected_cost_delta_usd", "observed_cost_delta_usd",
                      "expected_latency_delta_seconds", "observed_latency_delta_seconds"):
            val = getattr(self, attr)
            if val is not None:
                d[attr] = val
        return d


@dataclass
class BlockedVendor:
    vendor: str
    reason: str
    blocked_since: str
    expected_resume: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "vendor": self.vendor,
            "reason": self.reason,
            "blocked_since": self.blocked_since,
        }
        if self.expected_resume:
            d["expected_resume"] = self.expected_resume
        return d


@dataclass
class FailedItem:
    item_id: str
    reason: str
    failed_at: str
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "reason": self.reason,
            "failed_at": self.failed_at,
            "retry_count": self.retry_count,
        }


_ATTEMPT_REQUIRED = {
    "dispatch_id",
    "item_id",
    "change_id",
    "phase",
    "attempt",
    "status",
    "prepared_at",
    "launch_token",
    "launch_marker_path",
    "lease_generation",
    "launch_history",
    "scope",
    "isolation",
    "context",
}
_SECRET_CONTEXT_KEY = re.compile(
    r"secret|token|password|credential|api[_-]?key|private[_-]?key|auth|cookie|"
    r"raw[_-]?response|transcript",
    re.IGNORECASE,
)


def _require_attempt_fields(value: dict[str, Any], fields: set[str], state: str) -> None:
    missing = sorted(fields - value.keys())
    if missing:
        raise ValueError(f"{state} dispatch attempt missing fields: {', '.join(missing)}")


def _validate_dispatch_context(value: Any, *, depth: int = 1) -> None:
    if not isinstance(value, dict) or depth > 4 or len(value) > 32:
        raise ValueError("dispatch context must be an object bounded to four levels")
    for key, child in value.items():
        if not isinstance(key, str) or not key or len(key) > 64:
            raise ValueError("dispatch context keys must be 1-64 character strings")
        if _SECRET_CONTEXT_KEY.search(key):
            raise ValueError(f"dispatch context contains forbidden key: {key}")
        if isinstance(child, dict):
            _validate_dispatch_context(child, depth=depth + 1)
        elif isinstance(child, list):
            if len(child) > 64 or any(isinstance(item, (dict, list)) for item in child):
                raise ValueError("dispatch context arrays must contain at most 64 scalars")
        elif not isinstance(child, (str, int, float, bool, type(None))):
            raise ValueError("dispatch context values must be JSON scalars")
        elif isinstance(child, str) and len(child) > 4096:
            raise ValueError("dispatch context strings must not exceed 4096 characters")
    if depth == 1:
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
        if len(canonical.encode("utf-8")) > 16 * 1024:
            raise ValueError("dispatch context canonical JSON must not exceed 16 KiB")


def validate_delegated_dispatch_attempt(attempt: dict[str, Any]) -> None:
    """Validate one delegated attempt before it enters durable state."""
    if not isinstance(attempt, dict):
        raise ValueError("dispatch attempt must be an object")
    _require_attempt_fields(attempt, _ATTEMPT_REQUIRED, "delegated")
    if attempt["phase"] != "autopilot":
        raise ValueError("dispatch attempt phase must be autopilot")
    generation = attempt["lease_generation"]
    if not isinstance(generation, int) or generation < 1:
        raise ValueError("dispatch attempt generation must be positive")
    history = attempt["launch_history"]
    if not isinstance(history, list) or len(history) > 64:
        raise ValueError("dispatch attempt launch_history must contain at most 64 entries")
    for entry in history:
        if not isinstance(entry, dict) or not isinstance(entry.get("generation"), int):
            raise ValueError("dispatch attempt launch_history entries require a generation")
        if entry["generation"] > generation:
            raise ValueError("dispatch attempt launch_history generation is future")
    _validate_dispatch_context(attempt["context"])

    status = attempt["status"]
    allowed = {
        "prepared",
        "claimed",
        "acknowledged",
        "launched",
        "quarantined",
        "parked",
        "completed",
        "failed",
    }
    if status not in allowed:
        raise ValueError(f"unsupported dispatch attempt status: {status}")
    lease = attempt.get("lease")
    evidence = attempt.get("launch_evidence")
    gate = attempt.get("launch_gate")
    for label, value in (("lease", lease), ("launch_evidence", evidence), ("launch_gate", gate)):
        if value is not None and (
            not isinstance(value, dict) or value.get("generation") != generation
        ):
            raise ValueError(f"dispatch attempt generation mismatch in {label}")
    if (
        evidence
        and gate
        and evidence.get("kind") == "host_ack"
        and evidence.get("handle") != gate.get("handle")
    ):
        raise ValueError("dispatch attempt host acknowledgement handle mismatch")

    outcome = attempt.get("outcome")
    if status in {"prepared", "claimed", "acknowledged", "launched", "quarantined"} and (
        outcome is not None or attempt.get("resolved_at") is not None
    ):
        raise ValueError(f"{status} dispatch attempt cannot be terminal")
    launch_fields = {"lease", "launch_evidence", "launch_gate"}
    if status == "prepared":
        if launch_fields & attempt.keys() or {"parked", "quarantine"} & attempt.keys():
            raise ValueError("prepared dispatch attempt cannot contain launch state")
    elif status == "claimed":
        _require_attempt_fields(attempt, launch_fields, status)
        if (
            lease.get("state") != "active"
            or evidence.get("kind") != "child_marker"
            or gate.get("state") != "waiting_ack"
            or any(gate.get(key) is not None for key in ("handle", "go_released_at", "entered_at"))
        ):
            raise ValueError("claimed dispatch attempt must hold an active pre-ack marker lease")
    elif status == "acknowledged":
        _require_attempt_fields(attempt, launch_fields, status)
        if (
            lease.get("state") != "active"
            or evidence.get("kind") != "host_ack"
            or gate.get("state") != "go_released"
            or not gate.get("handle")
            or not gate.get("go_released_at")
            or gate.get("entered_at") is not None
        ):
            raise ValueError("acknowledged dispatch attempt must release go before entry")
    elif status == "launched":
        _require_attempt_fields(attempt, launch_fields, status)
        if (
            lease.get("state") != "active"
            or evidence.get("kind") != "host_ack"
            or gate.get("state") != "entered"
            or not all(gate.get(key) for key in ("handle", "go_released_at", "entered_at"))
        ):
            raise ValueError("launched dispatch attempt must record entry with an active lease")
    elif status == "quarantined":
        _require_attempt_fields(attempt, launch_fields | {"quarantine"}, status)
        if (
            lease.get("state") != "uncertain"
            or evidence.get("kind") != "host_ack"
            or gate.get("state") not in {"go_released", "entered"}
            or not gate.get("handle")
            or not gate.get("go_released_at")
            or attempt["quarantine"].get("kind") != "unknown_liveness"
        ):
            raise ValueError("quarantined dispatch attempt must retain an uncertain post-go lease")
    elif status == "parked":
        _require_attempt_fields(
            attempt, launch_fields | {"parked", "outcome", "resolved_at"}, status
        )
        if (
            lease.get("state") != "released"
            or evidence.get("kind") != "host_ack"
            or gate.get("state") != "entered"
            or not all(gate.get(key) for key in ("handle", "go_released_at", "entered_at"))
            or outcome != "parked"
            or attempt["parked"].get("kind") not in {"pending_gate", "policy_pause"}
        ):
            raise ValueError("parked dispatch attempt must release a gate or policy pause")
    elif status == "completed":
        _require_attempt_fields(
            attempt, launch_fields | {"handoff_id", "outcome", "resolved_at"}, status
        )
        if lease.get("state") != "released" or outcome != "success" or not attempt["handoff_id"]:
            raise ValueError("completed dispatch attempt requires success and handoff")
    elif status == "failed":
        _require_attempt_fields(attempt, {"outcome", "resolved_at"}, status)
        if not isinstance(outcome, str) or not (
            outcome.startswith("failed:") or outcome.startswith("vendor_limit:")
        ):
            raise ValueError("failed dispatch attempt requires failure outcome")
        if lease is not None and lease.get("state") not in {"released", "expired"}:
            raise ValueError("failed dispatch attempt must release or expire its lease")

    if status != "parked" and "parked" in attempt:
        raise ValueError(f"{status} dispatch attempt cannot contain parked state")
    if status != "quarantined" and "quarantine" in attempt:
        raise ValueError(f"{status} dispatch attempt cannot contain quarantine state")
    continuation = attempt.get("continuation")
    if continuation is not None and (
        status != "prepared"
        or generation < 2
        or continuation.get("kind") not in {"pending_gate", "policy_pause"}
        or not continuation.get("approval_ref")
    ):
        raise ValueError("prepared continuation requires parked kind and approval reference")


@dataclass
class Checkpoint:
    schema_version: int
    roadmap_id: str
    current_item_id: str
    phase: CheckpointPhase
    created_at: str
    updated_at: str | None = None
    completed_items: list[str] = field(default_factory=list)
    failed_items: list[FailedItem] = field(default_factory=list)
    vendor_state: dict[str, Any] = field(default_factory=dict)
    pause_state: dict[str, Any] = field(default_factory=dict)
    dispatch_attempts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "roadmap_id": self.roadmap_id,
            "current_item_id": self.current_item_id,
            "phase": self.phase.value,
            "created_at": self.created_at,
        }
        if self.updated_at:
            d["updated_at"] = self.updated_at
        if self.completed_items:
            d["completed_items"] = self.completed_items
        if self.failed_items:
            d["failed_items"] = [f.to_dict() for f in self.failed_items]
        if self.vendor_state:
            d["vendor_state"] = self.vendor_state
        if self.pause_state:
            d["pause_state"] = self.pause_state
        if self.dispatch_attempts:
            for attempt in self.dispatch_attempts:
                validate_delegated_dispatch_attempt(attempt)
            d["dispatch_attempts"] = json.loads(json.dumps(self.dispatch_attempts))
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Checkpoint:
        dispatch_attempts = data.get("dispatch_attempts", [])
        for attempt in dispatch_attempts:
            validate_delegated_dispatch_attempt(attempt)
        return cls(
            schema_version=data["schema_version"],
            roadmap_id=data["roadmap_id"],
            current_item_id=data["current_item_id"],
            phase=CheckpointPhase(data["phase"]),
            created_at=data["created_at"],
            updated_at=data.get("updated_at"),
            completed_items=data.get("completed_items", []),
            failed_items=[
                FailedItem(
                    item_id=f["item_id"],
                    reason=f["reason"],
                    failed_at=f["failed_at"],
                    retry_count=f.get("retry_count", 0),
                )
                for f in data.get("failed_items", [])
            ],
            vendor_state=data.get("vendor_state", {}),
            pause_state=data.get("pause_state", {}),
            dispatch_attempts=json.loads(json.dumps(dispatch_attempts)),
        )

    @classmethod
    def create(cls, roadmap_id: str, first_item_id: str) -> Checkpoint:
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            schema_version=1,
            roadmap_id=roadmap_id,
            current_item_id=first_item_id,
            phase=CheckpointPhase.PLANNING,
            created_at=now,
        )


@dataclass
class LearningDecision:
    title: str
    outcome: str
    alternatives_rejected: list[str] = field(default_factory=list)


@dataclass
class LearningBlocker:
    description: str
    resolution: str
    duration_minutes: int | None = None


@dataclass
class LearningDeviation:
    from_plan: str
    actual: str
    reason: str


@dataclass
class LearningEntry:
    schema_version: int
    item_id: str
    timestamp: str
    decisions: list[LearningDecision]
    change_id: str | None = None
    phase: LearningPhase | None = None
    blockers: list[LearningBlocker] = field(default_factory=list)
    deviations: list[LearningDeviation] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    vendor_notes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "item_id": self.item_id,
            "timestamp": self.timestamp,
            "decisions": [
                {"title": dec.title, "outcome": dec.outcome,
                 **({"alternatives_rejected": dec.alternatives_rejected}
                    if dec.alternatives_rejected else {})}
                for dec in self.decisions
            ],
        }
        if self.change_id:
            d["change_id"] = self.change_id
        if self.phase:
            d["phase"] = self.phase.value
        if self.blockers:
            d["blockers"] = [
                {"description": b.description, "resolution": b.resolution,
                 **({"duration_minutes": b.duration_minutes}
                    if b.duration_minutes is not None else {})}
                for b in self.blockers
            ]
        if self.deviations:
            d["deviations"] = [
                {"from_plan": dv.from_plan, "actual": dv.actual, "reason": dv.reason}
                for dv in self.deviations
            ]
        if self.recommendations:
            d["recommendations"] = self.recommendations
        if self.vendor_notes:
            d["vendor_notes"] = self.vendor_notes
        return d


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _load_schema(schema_path: str, repo_root: Path) -> dict[str, Any]:
    full_path = repo_root / schema_path
    if not full_path.exists():
        raise FileNotFoundError(f"Schema not found: {full_path}")
    return json.loads(full_path.read_text())  # type: ignore[no-any-return]


def validate_against_schema(data: dict[str, Any], schema_path: str, repo_root: Path) -> list[str]:
    """Validate data against a JSON Schema. Returns list of error messages."""
    try:
        import jsonschema
    except ImportError:
        logger.warning("jsonschema not installed — skipping schema validation")
        return []

    schema = _load_schema(schema_path, repo_root)
    validator = jsonschema.Draft202012Validator(schema)
    return [e.message for e in validator.iter_errors(data)]


# ---------------------------------------------------------------------------
# Cross-roadmap helpers
# ---------------------------------------------------------------------------
ROADMAPS_DIRNAME = "openspec/roadmaps"


def parse_item_ref(ref: str) -> tuple[str, str]:
    """Split an item_ref ``<roadmap-id>:<item-id>`` into its two parts.

    Returns ``(roadmap_id, item_id)``. Raises ``ValueError`` when the ref is
    not exactly ``<roadmap-id>:<item-id>`` (both parts non-empty, exactly one
    colon).
    """
    parts = ref.split(":")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"Malformed item_ref {ref!r} — expected '<roadmap-id>:<item-id>'."
        )
    return parts[0], parts[1]


def is_valid_item_ref(ref: str) -> bool:
    """True when ``ref`` matches the ``<roadmap-id>:<item-id>`` grammar."""
    try:
        parse_item_ref(ref)
    except ValueError:
        return False
    return True


def load_all_roadmaps_strict(
    repo_root: Path,
) -> tuple[dict[str, Roadmap], list[str]]:
    """Load every sibling roadmap, reporting rather than swallowing failures.

    Returns ``({roadmap_id: Roadmap}, errors)``. Two classes of failure that
    :func:`load_all_roadmaps` hides are surfaced here as error strings:

    * a ``roadmap.yaml`` that does not parse or does not model — silently
      dropping it makes every cross-roadmap check *fail open*, because refs
      into it, cycles through it, and change_ids it claims all become
      invisible;
    * two directories declaring the same ``roadmap_id`` — last-writer-wins
      would discard one workspace's items entirely.

    Read-only and side-effect-free. Validation callers want this loader; the
    readiness path keeps the tolerant :func:`load_all_roadmaps`.
    """
    result: dict[str, Roadmap] = {}
    errors: list[str] = []
    origin: dict[str, Path] = {}
    roadmaps_dir = repo_root / ROADMAPS_DIRNAME
    if not roadmaps_dir.is_dir():
        return result, errors
    for path in sorted(roadmaps_dir.glob("*/roadmap.yaml")):
        try:
            data = yaml.safe_load(path.read_text())
            roadmap = Roadmap.from_dict(data)
        except Exception as exc:  # noqa: BLE001 — reported, not raised
            rel = path.relative_to(repo_root)
            errors.append(f"{rel}: could not be loaded ({type(exc).__name__}: {exc}).")
            continue
        if roadmap.roadmap_id in origin:
            rel = path.relative_to(repo_root)
            prev = origin[roadmap.roadmap_id].relative_to(repo_root)
            errors.append(
                f"{rel}: roadmap_id {roadmap.roadmap_id!r} is already declared "
                f"by {prev} — roadmap_id must be unique across workspaces."
            )
            continue
        origin[roadmap.roadmap_id] = path
        result[roadmap.roadmap_id] = roadmap
    return result, errors


def load_all_roadmaps(repo_root: Path) -> dict[str, Roadmap]:
    """Load every ``openspec/roadmaps/*/roadmap.yaml`` under ``repo_root``.

    Read-only and side-effect-free. Returns ``{roadmap_id: Roadmap}`` keyed by
    each roadmap's declared ``roadmap_id`` (not its directory name). Archived
    roadmaps under ``openspec/roadmaps/archive/<...>/roadmap.yaml`` are nested a
    level deeper and are naturally excluded by the ``*/roadmap.yaml`` glob.

    Tolerant by design: a malformed sibling must not break the readiness path.
    Failures are logged at WARNING (not debug) because a dropped roadmap
    silently withholds every item that externally depends on it — see
    :func:`load_all_roadmaps_strict` for the validation-side loader that
    reports failures instead of hiding them.
    """
    result, errors = load_all_roadmaps_strict(repo_root)
    for err in errors:
        logger.warning(
            "roadmap excluded from cross-roadmap resolution — %s "
            "Items with external_depends_on into it will stay non-ready.",
            err,
        )
    return result


def external_item_status(repo_root: Path) -> dict[str, str]:
    """Return ``{item_ref: status}`` for every item across all roadmaps.

    Keys are fully-qualified item_refs ``<roadmap-id>:<item-id>``; values are
    the item's status string. Read-only.
    """
    status: dict[str, str] = {}
    for roadmap_id, roadmap in load_all_roadmaps(repo_root).items():
        for item in roadmap.items:
            status[f"{roadmap_id}:{item.item_id}"] = item.status.value
    return status


def completed_external_refs(repo_root: Path) -> set[str]:
    """Set of item_refs across all roadmaps whose item status is ``completed``.

    This is the value to pass as ``external_completed`` to
    :meth:`Roadmap.ready_items` / the orchestrator's ``_get_ready_items``.
    """
    return {
        ref
        for ref, st in external_item_status(repo_root).items()
        if st == ItemStatus.COMPLETED.value
    }


# ---------------------------------------------------------------------------
# Load / Save helpers
# ---------------------------------------------------------------------------
def load_roadmap(path: Path, repo_root: Path | None = None) -> Roadmap:
    """Load and validate a roadmap.yaml file."""
    data = yaml.safe_load(path.read_text())
    if repo_root:
        errors = validate_against_schema(data, ROADMAP_SCHEMA, repo_root)
        if errors:
            raise ValueError(f"Roadmap validation failed: {'; '.join(errors)}")
    return Roadmap.from_dict(data)


def save_roadmap(roadmap: Roadmap, path: Path, *, overwrite: bool = False) -> None:
    """Save a roadmap to YAML.

    Creates parent directories as needed. Refuses to overwrite an existing
    file unless ``overwrite=True`` — operators edit ``status``/``priority``
    in place, so a silent overwrite would clobber their work.
    """
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"Roadmap already exists at {path}. Pass overwrite=True to replace it, "
            f"or choose a different workspace directory."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    roadmap.updated_at = datetime.now(timezone.utc).isoformat()
    path.write_text(yaml.dump(roadmap.to_dict(), default_flow_style=False, sort_keys=False))


def load_checkpoint(path: Path, repo_root: Path | None = None) -> Checkpoint:
    """Load and validate a checkpoint.json file."""
    data = json.loads(path.read_text())
    if repo_root:
        errors = validate_against_schema(data, CHECKPOINT_SCHEMA, repo_root)
        if errors:
            raise ValueError(f"Checkpoint validation failed: {'; '.join(errors)}")
    return Checkpoint.from_dict(data)


def save_checkpoint(checkpoint: Checkpoint, path: Path) -> None:
    """Save a checkpoint to JSON."""
    checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(checkpoint.to_dict(), indent=2) + "\n")

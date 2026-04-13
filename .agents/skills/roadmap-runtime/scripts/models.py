"""Roadmap artifact models with JSON Schema validation.

Provides dataclasses for roadmap.yaml, checkpoint.json, and learning-log
entries, plus load/save helpers that validate against the contract schemas.
"""

from __future__ import annotations

import json
import logging
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


class Effort(str, Enum):
    XS = "XS"
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"


class PolicyAction(str, Enum):
    WAIT = "wait_if_budget_exceeded"
    SWITCH = "switch_if_time_saved"


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

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "item_id": self.item_id,
            "title": self.title,
            "status": self.status.value,
            "priority": self.priority,
            "effort": self.effort.value,
            "depends_on": self.depends_on,
        }
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
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoadmapItem:
        return cls(
            item_id=data["item_id"],
            title=data["title"],
            status=ItemStatus(data["status"]),
            priority=data["priority"],
            effort=Effort(data["effort"]),
            depends_on=data.get("depends_on", []),
            description=data.get("description"),
            rationale=data.get("rationale"),
            change_id=data.get("change_id"),
            acceptance_outcomes=data.get("acceptance_outcomes", []),
            failure_reason=data.get("failure_reason"),
            blocked_by=data.get("blocked_by", []),
            learning_refs=data.get("learning_refs", []),
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
        )

    def get_item(self, item_id: str) -> RoadmapItem | None:
        for item in self.items:
            if item.item_id == item_id:
                return item
        return None

    def ready_items(self) -> list[RoadmapItem]:
        """Return items whose dependencies are all completed and status is approved."""
        completed_ids = {i.item_id for i in self.items if i.status == ItemStatus.COMPLETED}
        return [
            i for i in self.items
            if i.status == ItemStatus.APPROVED
            and all(dep in completed_ids for dep in i.depends_on)
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
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Checkpoint:
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


def save_roadmap(roadmap: Roadmap, path: Path) -> None:
    """Save a roadmap to YAML."""
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

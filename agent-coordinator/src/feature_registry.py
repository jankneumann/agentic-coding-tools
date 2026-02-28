"""Feature registry service for cross-feature coordination.

Manages feature registrations and their resource claims (lock keys).
Provides conflict analysis and parallel feasibility assessment.

A feature is registered before entering implementation. Its resource_claims
list declares which lock keys (files and logical keys) the feature intends
to use. The registry detects overlaps between active features and produces
a feasibility assessment: FULL (no overlaps), PARTIAL (some shared resources),
or SEQUENTIAL (too many conflicts to parallelize).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .audit import get_audit_service
from .config import get_config
from .db import DatabaseClient, get_db

logger = logging.getLogger(__name__)


class Feasibility(Enum):
    """Parallel feasibility assessment result."""

    FULL = "FULL"  # No resource overlaps — safe to run fully parallel
    PARTIAL = "PARTIAL"  # Some overlaps — parallel with coordination
    SEQUENTIAL = "SEQUENTIAL"  # Too many overlaps — must serialize


@dataclass
class Feature:
    """A registered feature with its resource claims."""

    feature_id: str
    title: str | None
    status: str
    registered_by: str
    registered_at: datetime | None
    updated_at: datetime | None
    completed_at: datetime | None
    resource_claims: list[str] = field(default_factory=list)
    branch_name: str | None = None
    merge_priority: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Feature":
        def parse_dt(val: Any) -> datetime | None:
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(str(val).replace("Z", "+00:00"))

        return cls(
            feature_id=data["feature_id"],
            title=data.get("title"),
            status=data["status"],
            registered_by=data["registered_by"],
            registered_at=parse_dt(data.get("registered_at")),
            updated_at=parse_dt(data.get("updated_at")),
            completed_at=parse_dt(data.get("completed_at")),
            resource_claims=data.get("resource_claims") or [],
            branch_name=data.get("branch_name"),
            merge_priority=data.get("merge_priority", 5),
            metadata=data.get("metadata") or {},
        )


@dataclass
class RegisterResult:
    """Result of a feature registration attempt."""

    success: bool
    feature_id: str | None = None
    action: str | None = None  # 'registered' or 'updated'
    reason: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegisterResult":
        return cls(
            success=data["success"],
            feature_id=data.get("feature_id"),
            action=data.get("action"),
            reason=data.get("reason"),
        )


@dataclass
class DeregisterResult:
    """Result of a feature deregistration."""

    success: bool
    feature_id: str | None = None
    status: str | None = None
    reason: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeregisterResult":
        return cls(
            success=data["success"],
            feature_id=data.get("feature_id"),
            status=data.get("status"),
            reason=data.get("reason"),
        )


@dataclass
class ConflictReport:
    """Report of resource conflicts between a candidate and active features."""

    candidate_feature_id: str
    candidate_claims: list[str]
    conflicts: list[dict[str, Any]]  # {feature_id, overlapping_keys}
    feasibility: Feasibility
    total_candidate_claims: int
    total_conflicting_claims: int


class FeatureRegistryService:
    """Service for managing the feature registry."""

    # If more than this fraction of a candidate's claims overlap with
    # active features, the feasibility is SEQUENTIAL rather than PARTIAL.
    SEQUENTIAL_THRESHOLD = 0.5

    def __init__(self, db: DatabaseClient | None = None):
        self._db = db

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def register(
        self,
        feature_id: str,
        resource_claims: list[str],
        title: str | None = None,
        agent_id: str | None = None,
        branch_name: str | None = None,
        merge_priority: int = 5,
        metadata: dict[str, Any] | None = None,
    ) -> RegisterResult:
        """Register a feature with its resource claims.

        Args:
            feature_id: Unique feature identifier
            resource_claims: List of lock keys this feature will use
            title: Human-readable feature title
            agent_id: Agent registering the feature (default: from config)
            branch_name: Git branch for this feature
            merge_priority: Merge priority (1=highest, 10=lowest)
            metadata: Additional metadata

        Returns:
            RegisterResult indicating success/failure
        """
        config = get_config()
        resolved_agent_id = agent_id or config.agent.agent_id

        result = await self.db.rpc(
            "register_feature",
            {
                "p_feature_id": feature_id,
                "p_title": title,
                "p_agent_id": resolved_agent_id,
                "p_resource_claims": resource_claims,
                "p_branch_name": branch_name,
                "p_merge_priority": merge_priority,
                "p_metadata": metadata or {},
            },
        )

        reg_result = RegisterResult.from_dict(result)

        try:
            await get_audit_service().log_operation(
                agent_id=resolved_agent_id,
                operation="register_feature",
                parameters={
                    "feature_id": feature_id,
                    "claims_count": len(resource_claims),
                },
                result={"action": reg_result.action},
                success=reg_result.success,
            )
        except Exception:
            logger.warning("Audit log failed for register_feature", exc_info=True)

        return reg_result

    async def deregister(
        self,
        feature_id: str,
        status: str = "completed",
    ) -> DeregisterResult:
        """Deregister a feature (mark as completed or cancelled).

        Args:
            feature_id: Feature to deregister
            status: Target status ('completed' or 'cancelled')

        Returns:
            DeregisterResult indicating success/failure
        """
        result = await self.db.rpc(
            "deregister_feature",
            {
                "p_feature_id": feature_id,
                "p_status": status,
            },
        )

        dereg_result = DeregisterResult.from_dict(result)

        try:
            await get_audit_service().log_operation(
                operation="deregister_feature",
                parameters={"feature_id": feature_id, "status": status},
                success=dereg_result.success,
            )
        except Exception:
            logger.warning("Audit log failed for deregister_feature", exc_info=True)

        return dereg_result

    async def get_feature(self, feature_id: str) -> Feature | None:
        """Get a specific feature by ID.

        Args:
            feature_id: Feature ID to look up

        Returns:
            Feature if found, None otherwise
        """
        features = await self.db.query(
            "feature_registry",
            f"feature_id=eq.{feature_id}",
        )
        return Feature.from_dict(features[0]) if features else None

    async def get_active_features(self) -> list[Feature]:
        """Get all active features.

        Returns:
            List of features with status='active'
        """
        features = await self.db.query(
            "feature_registry",
            "status=eq.active&order=merge_priority.asc,registered_at.asc",
        )
        return [Feature.from_dict(f) for f in features]

    async def analyze_conflicts(
        self,
        candidate_feature_id: str,
        candidate_claims: list[str],
    ) -> ConflictReport:
        """Analyze conflicts between a candidate feature and active features.

        Compares the candidate's resource claims against all active features
        (excluding itself) and produces a feasibility assessment.

        Args:
            candidate_feature_id: Feature being analyzed
            candidate_claims: Lock keys the candidate intends to use

        Returns:
            ConflictReport with conflicts and feasibility assessment
        """
        active = await self.get_active_features()
        candidate_set = set(candidate_claims)
        conflicts: list[dict[str, Any]] = []
        all_conflicting_keys: set[str] = set()

        for feature in active:
            if feature.feature_id == candidate_feature_id:
                continue
            existing_set = set(feature.resource_claims)
            overlap = candidate_set & existing_set
            if overlap:
                conflicts.append({
                    "feature_id": feature.feature_id,
                    "overlapping_keys": sorted(overlap),
                })
                all_conflicting_keys |= overlap

        # Determine feasibility
        if not conflicts:
            feasibility = Feasibility.FULL
        elif (
            len(candidate_claims) > 0
            and len(all_conflicting_keys) / len(candidate_claims)
            > self.SEQUENTIAL_THRESHOLD
        ):
            feasibility = Feasibility.SEQUENTIAL
        else:
            feasibility = Feasibility.PARTIAL

        return ConflictReport(
            candidate_feature_id=candidate_feature_id,
            candidate_claims=candidate_claims,
            conflicts=conflicts,
            feasibility=feasibility,
            total_candidate_claims=len(candidate_claims),
            total_conflicting_claims=len(all_conflicting_keys),
        )


# Global service instance
_feature_registry_service: FeatureRegistryService | None = None


def get_feature_registry_service() -> FeatureRegistryService:
    """Get the global feature registry service instance."""
    global _feature_registry_service
    if _feature_registry_service is None:
        _feature_registry_service = FeatureRegistryService()
    return _feature_registry_service

"""Merge queue service for cross-feature merge ordering.

Manages the order in which completed features are merged to main.
Features are enqueued when their implementation PR is ready, and
dequeued after successful merge. Pre-merge checks re-validate
resource claims to catch conflicts introduced after initial
registration.

The merge queue is backed by the feature_registry table's merge_priority
column, using the feature registry as the source of truth for ordering.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from .audit import get_audit_service
from .config import get_config
from .db import DatabaseClient, get_db
from .feature_registry import (
    Feasibility,
    Feature,
    FeatureRegistryService,
    get_feature_registry_service,
)

logger = logging.getLogger(__name__)


class MergeStatus(str, Enum):
    """Status of a feature in the merge queue."""

    QUEUED = "queued"
    PRE_MERGE_CHECK = "pre_merge_check"
    READY = "ready"
    MERGING = "merging"
    MERGED = "merged"
    BLOCKED = "blocked"


@dataclass
class PreMergeCheckResult:
    """Result of pre-merge validation checks."""

    feature_id: str
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class MergeQueueEntry:
    """A feature in the merge queue."""

    feature_id: str
    branch_name: str | None
    merge_priority: int
    merge_status: MergeStatus
    pr_url: str | None = None
    queued_at: datetime | None = None
    checked_at: datetime | None = None
    merged_at: datetime | None = None

    @classmethod
    def from_feature(
        cls,
        feature: Feature,
        merge_status: MergeStatus = MergeStatus.QUEUED,
        pr_url: str | None = None,
    ) -> "MergeQueueEntry":
        return cls(
            feature_id=feature.feature_id,
            branch_name=feature.branch_name,
            merge_priority=feature.merge_priority,
            merge_status=merge_status,
            pr_url=pr_url,
        )


class MergeQueueService:
    """Service for managing the merge queue.

    The merge queue is a logical layer on top of the feature registry.
    It tracks which features are ready to merge and in what order.
    Merge state is stored in the feature_registry.metadata JSONB field
    to avoid adding another table.
    """

    METADATA_KEY = "merge_queue"

    def __init__(
        self,
        db: DatabaseClient | None = None,
        registry: FeatureRegistryService | None = None,
    ):
        self._db = db
        self._registry = registry

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    @property
    def registry(self) -> FeatureRegistryService:
        if self._registry is None:
            self._registry = get_feature_registry_service()
        return self._registry

    async def enqueue(
        self,
        feature_id: str,
        pr_url: str | None = None,
    ) -> MergeQueueEntry | None:
        """Add a feature to the merge queue.

        The feature must be active in the registry. Sets merge_queue
        metadata on the feature.

        Args:
            feature_id: Feature to enqueue
            pr_url: URL of the PR to merge

        Returns:
            MergeQueueEntry if successful, None if feature not found
        """
        feature = await self.registry.get_feature(feature_id)
        if feature is None or feature.status != "active":
            return None

        merge_meta = {
            "status": MergeStatus.QUEUED.value,
            "pr_url": pr_url,
            "queued_at": datetime.now(UTC).isoformat(),
        }

        # Update feature metadata with merge queue info
        await self.db.update(
            "feature_registry",
            match={"feature_id": feature_id},
            data={
                "metadata": {
                    **feature.metadata,
                    self.METADATA_KEY: merge_meta,
                },
            },
        )

        try:
            await get_audit_service().log_operation(
                operation="merge_queue_enqueue",
                parameters={"feature_id": feature_id, "pr_url": pr_url},
                success=True,
            )
        except Exception:
            logger.warning("Audit log failed for merge_queue_enqueue", exc_info=True)

        return MergeQueueEntry.from_feature(
            feature,
            merge_status=MergeStatus.QUEUED,
            pr_url=pr_url,
        )

    async def get_queue(self) -> list[MergeQueueEntry]:
        """Get all features in the merge queue, ordered by priority.

        Returns features that have merge_queue metadata and are still active.

        Returns:
            List of MergeQueueEntry ordered by merge_priority
        """
        active = await self.registry.get_active_features()
        entries = []

        for feature in active:
            merge_meta = feature.metadata.get(self.METADATA_KEY)
            if merge_meta is None:
                continue

            status_str = merge_meta.get("status", MergeStatus.QUEUED.value)
            try:
                merge_status = MergeStatus(status_str)
            except ValueError:
                merge_status = MergeStatus.QUEUED

            entry = MergeQueueEntry(
                feature_id=feature.feature_id,
                branch_name=feature.branch_name,
                merge_priority=feature.merge_priority,
                merge_status=merge_status,
                pr_url=merge_meta.get("pr_url"),
                queued_at=_parse_dt(merge_meta.get("queued_at")),
                checked_at=_parse_dt(merge_meta.get("checked_at")),
                merged_at=_parse_dt(merge_meta.get("merged_at")),
            )
            entries.append(entry)

        return entries

    async def get_next_to_merge(self) -> MergeQueueEntry | None:
        """Get the highest-priority feature ready to merge.

        Returns the first entry with status READY, ordered by merge_priority.

        Returns:
            MergeQueueEntry if one is ready, None otherwise
        """
        queue = await self.get_queue()
        for entry in queue:
            if entry.merge_status == MergeStatus.READY:
                return entry
        return None

    async def run_pre_merge_checks(
        self,
        feature_id: str,
    ) -> PreMergeCheckResult:
        """Run pre-merge validation checks on a feature.

        Checks:
        1. Feature is still active in registry
        2. No new resource conflicts with other active features
        3. Feature has merge_queue metadata

        Args:
            feature_id: Feature to validate

        Returns:
            PreMergeCheckResult with pass/fail and details
        """
        feature = await self.registry.get_feature(feature_id)
        checks: dict[str, bool] = {}
        issues: list[str] = []

        # Check 1: Feature exists and is active
        if feature is None:
            return PreMergeCheckResult(
                feature_id=feature_id,
                passed=False,
                checks={"feature_active": False},
                issues=["Feature not found in registry"],
            )

        checks["feature_active"] = feature.status == "active"
        if not checks["feature_active"]:
            issues.append(f"Feature status is '{feature.status}', not 'active'")

        # Check 2: Re-validate resource conflicts
        report = await self.registry.analyze_conflicts(
            feature_id, feature.resource_claims
        )
        checks["no_resource_conflicts"] = report.feasibility != Feasibility.SEQUENTIAL
        if not checks["no_resource_conflicts"]:
            issues.append(
                f"Resource conflicts detected: {report.total_conflicting_claims} "
                f"conflicting claims out of {report.total_candidate_claims}"
            )

        # Check 3: Feature is in merge queue
        merge_meta = feature.metadata.get(self.METADATA_KEY)
        checks["in_merge_queue"] = merge_meta is not None
        if not checks["in_merge_queue"]:
            issues.append("Feature not found in merge queue")

        passed = all(checks.values())

        # Update merge queue status based on check result
        if merge_meta is not None:
            new_status = (
                MergeStatus.READY.value if passed else MergeStatus.BLOCKED.value
            )
            merge_meta["status"] = new_status
            merge_meta["checked_at"] = datetime.now(UTC).isoformat()
            await self.db.update(
                "feature_registry",
                match={"feature_id": feature_id},
                data={
                    "metadata": {
                        **feature.metadata,
                        self.METADATA_KEY: merge_meta,
                    },
                },
            )

        try:
            await get_audit_service().log_operation(
                operation="merge_queue_pre_check",
                parameters={"feature_id": feature_id},
                result={"passed": passed, "checks": checks},
                success=True,
            )
        except Exception:
            logger.warning("Audit log failed for pre-merge check", exc_info=True)

        return PreMergeCheckResult(
            feature_id=feature_id,
            passed=passed,
            checks=checks,
            issues=issues,
            conflicts=report.conflicts if report.conflicts else [],
        )

    async def mark_merged(self, feature_id: str) -> bool:
        """Mark a feature as merged and deregister it.

        Args:
            feature_id: Feature that was merged

        Returns:
            True if successful
        """
        feature = await self.registry.get_feature(feature_id)
        if feature is None:
            return False

        # Deregister from feature registry
        result = await self.registry.deregister(feature_id, status="completed")

        try:
            await get_audit_service().log_operation(
                operation="merge_queue_merged",
                parameters={"feature_id": feature_id},
                success=result.success,
            )
        except Exception:
            logger.warning("Audit log failed for merge_queue_merged", exc_info=True)

        return result.success

    async def remove_from_queue(self, feature_id: str) -> bool:
        """Remove a feature from the merge queue without merging.

        Clears the merge_queue metadata but keeps the feature active.

        Args:
            feature_id: Feature to remove from queue

        Returns:
            True if the feature was in the queue and removed
        """
        feature = await self.registry.get_feature(feature_id)
        if feature is None:
            return False

        if self.METADATA_KEY not in feature.metadata:
            return False

        new_metadata = {k: v for k, v in feature.metadata.items() if k != self.METADATA_KEY}
        await self.db.update(
            "feature_registry",
            match={"feature_id": feature_id},
            data={"metadata": new_metadata},
        )

        return True


def _parse_dt(val: Any) -> datetime | None:
    """Parse an ISO datetime string, returning None for empty/None."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    return datetime.fromisoformat(str(val).replace("Z", "+00:00"))


# Global service instance
_merge_queue_service: MergeQueueService | None = None


def get_merge_queue_service() -> MergeQueueService:
    """Get the global merge queue service instance."""
    global _merge_queue_service
    if _merge_queue_service is None:
        _merge_queue_service = MergeQueueService()
    return _merge_queue_service

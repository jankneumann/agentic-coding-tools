"""Tests for merge queue service (Task 8.1)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.feature_registry import (
    ConflictReport,
    DeregisterResult,
    Feasibility,
    Feature,
    FeatureRegistryService,
)
from src.merge_queue import (
    MergeQueueEntry,
    MergeQueueService,
    MergeStatus,
)


def _make_feature(
    feature_id: str = "f1",
    resource_claims: list[str] | None = None,
    merge_priority: int = 5,
    metadata: dict[str, Any] | None = None,
    status: str = "active",
    branch_name: str | None = None,
) -> Feature:
    """Build a Feature dataclass for testing."""
    return Feature(
        feature_id=feature_id,
        title=f"Feature {feature_id}",
        status=status,
        registered_by="agent-1",
        registered_at=None,
        updated_at=None,
        completed_at=None,
        resource_claims=resource_claims or [],
        branch_name=branch_name or f"openspec/{feature_id}",
        merge_priority=merge_priority,
        metadata=metadata or {},
    )


def _make_conflict_report(
    feature_id: str = "f1",
    claims: list[str] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
    feasibility: Feasibility = Feasibility.FULL,
) -> ConflictReport:
    """Build a ConflictReport for testing."""
    claims = claims or []
    conflicts = conflicts or []
    conflicting_keys: set[str] = set()
    for c in conflicts:
        conflicting_keys.update(c.get("overlapping_keys", []))
    return ConflictReport(
        candidate_feature_id=feature_id,
        candidate_claims=claims,
        conflicts=conflicts,
        feasibility=feasibility,
        total_candidate_claims=len(claims),
        total_conflicting_claims=len(conflicting_keys),
    )


@pytest.fixture
def mock_registry() -> FeatureRegistryService:
    """Create a mock registry service."""
    registry = AsyncMock(spec=FeatureRegistryService)
    return registry


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create a mock database client."""
    db = AsyncMock()
    db.update = AsyncMock(return_value=[])
    return db


@pytest.fixture
def service(mock_db, mock_registry) -> MergeQueueService:
    """Create a MergeQueueService with mocked dependencies."""
    return MergeQueueService(db=mock_db, registry=mock_registry)


class TestEnqueue:
    """Tests for adding features to the merge queue."""

    @pytest.mark.asyncio
    async def test_enqueue_active_feature(self, service, mock_registry, mock_db):
        """Enqueue an active feature successfully."""
        feature = _make_feature("f1")
        mock_registry.get_feature = AsyncMock(return_value=feature)

        entry = await service.enqueue("f1", pr_url="https://github.com/pr/1")

        assert entry is not None
        assert entry.feature_id == "f1"
        assert entry.merge_status == MergeStatus.QUEUED
        assert entry.pr_url == "https://github.com/pr/1"
        mock_db.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_enqueue_nonexistent_feature(self, service, mock_registry):
        """Enqueuing a non-existent feature returns None."""
        mock_registry.get_feature = AsyncMock(return_value=None)

        entry = await service.enqueue("nonexistent")

        assert entry is None

    @pytest.mark.asyncio
    async def test_enqueue_completed_feature(self, service, mock_registry):
        """Enqueuing a completed feature returns None."""
        feature = _make_feature("f1", status="completed")
        mock_registry.get_feature = AsyncMock(return_value=feature)

        entry = await service.enqueue("f1")

        assert entry is None

    @pytest.mark.asyncio
    async def test_enqueue_stores_metadata(self, service, mock_registry, mock_db):
        """Enqueue should store merge queue metadata on the feature."""
        feature = _make_feature("f1", metadata={"existing": "data"})
        mock_registry.get_feature = AsyncMock(return_value=feature)

        await service.enqueue("f1", pr_url="https://github.com/pr/1")

        call_args = mock_db.update.call_args
        data = call_args.kwargs.get("data") or call_args[1].get("data")
        merge_meta = data["metadata"]["merge_queue"]
        assert merge_meta["status"] == "queued"
        assert merge_meta["pr_url"] == "https://github.com/pr/1"
        assert "queued_at" in merge_meta
        # Existing metadata preserved
        assert data["metadata"]["existing"] == "data"


class TestGetQueue:
    """Tests for retrieving the merge queue."""

    @pytest.mark.asyncio
    async def test_get_queue_ordered(self, service, mock_registry):
        """Queue entries are returned in priority order from registry."""
        features = [
            _make_feature(
                "f1",
                merge_priority=3,
                metadata={
                    "merge_queue": {"status": "queued", "pr_url": None},
                },
            ),
            _make_feature(
                "f2",
                merge_priority=1,
                metadata={
                    "merge_queue": {"status": "ready", "pr_url": "https://pr/2"},
                },
            ),
        ]
        mock_registry.get_active_features = AsyncMock(return_value=features)

        queue = await service.get_queue()

        assert len(queue) == 2
        # Registry already returns in priority order
        assert queue[0].feature_id == "f1"
        assert queue[0].merge_status == MergeStatus.QUEUED
        assert queue[1].feature_id == "f2"
        assert queue[1].merge_status == MergeStatus.READY

    @pytest.mark.asyncio
    async def test_get_queue_excludes_non_queued(self, service, mock_registry):
        """Features without merge_queue metadata are excluded."""
        features = [
            _make_feature("f1", metadata={}),  # Not in queue
            _make_feature(
                "f2",
                metadata={
                    "merge_queue": {"status": "queued"},
                },
            ),
        ]
        mock_registry.get_active_features = AsyncMock(return_value=features)

        queue = await service.get_queue()

        assert len(queue) == 1
        assert queue[0].feature_id == "f2"

    @pytest.mark.asyncio
    async def test_get_queue_empty(self, service, mock_registry):
        """Empty queue returns empty list."""
        mock_registry.get_active_features = AsyncMock(return_value=[])

        queue = await service.get_queue()

        assert queue == []


class TestGetNextToMerge:
    """Tests for finding the next feature to merge."""

    @pytest.mark.asyncio
    async def test_next_ready_feature(self, service, mock_registry):
        """Returns the first READY feature."""
        features = [
            _make_feature(
                "f1",
                merge_priority=3,
                metadata={"merge_queue": {"status": "queued"}},
            ),
            _make_feature(
                "f2",
                merge_priority=5,
                metadata={"merge_queue": {"status": "ready"}},
            ),
        ]
        mock_registry.get_active_features = AsyncMock(return_value=features)

        entry = await service.get_next_to_merge()

        assert entry is not None
        assert entry.feature_id == "f2"
        assert entry.merge_status == MergeStatus.READY

    @pytest.mark.asyncio
    async def test_no_ready_features(self, service, mock_registry):
        """Returns None when no features are READY."""
        features = [
            _make_feature(
                "f1",
                metadata={"merge_queue": {"status": "queued"}},
            ),
        ]
        mock_registry.get_active_features = AsyncMock(return_value=features)

        entry = await service.get_next_to_merge()

        assert entry is None


class TestPreMergeChecks:
    """Tests for pre-merge validation."""

    @pytest.mark.asyncio
    async def test_all_checks_pass(self, service, mock_registry, mock_db):
        """All pre-merge checks pass → READY."""
        feature = _make_feature(
            "f1",
            resource_claims=["src/a.py"],
            metadata={"merge_queue": {"status": "queued"}},
        )
        mock_registry.get_feature = AsyncMock(return_value=feature)
        mock_registry.analyze_conflicts = AsyncMock(
            return_value=_make_conflict_report("f1", ["src/a.py"])
        )

        result = await service.run_pre_merge_checks("f1")

        assert result.passed is True
        assert result.checks["feature_active"] is True
        assert result.checks["no_resource_conflicts"] is True
        assert result.checks["in_merge_queue"] is True
        assert result.issues == []

    @pytest.mark.asyncio
    async def test_feature_not_found(self, service, mock_registry):
        """Feature not in registry → fail."""
        mock_registry.get_feature = AsyncMock(return_value=None)

        result = await service.run_pre_merge_checks("nonexistent")

        assert result.passed is False
        assert result.checks["feature_active"] is False
        assert "not found" in result.issues[0].lower()

    @pytest.mark.asyncio
    async def test_feature_not_active(self, service, mock_registry, mock_db):
        """Completed feature → fail the active check."""
        feature = _make_feature(
            "f1",
            status="completed",
            metadata={"merge_queue": {"status": "queued"}},
        )
        mock_registry.get_feature = AsyncMock(return_value=feature)
        mock_registry.analyze_conflicts = AsyncMock(
            return_value=_make_conflict_report("f1")
        )

        result = await service.run_pre_merge_checks("f1")

        assert result.passed is False
        assert result.checks["feature_active"] is False

    @pytest.mark.asyncio
    async def test_resource_conflicts_sequential(self, service, mock_registry, mock_db):
        """SEQUENTIAL conflicts → fail the resource check."""
        feature = _make_feature(
            "f1",
            resource_claims=["src/a.py", "src/b.py"],
            metadata={"merge_queue": {"status": "queued"}},
        )
        mock_registry.get_feature = AsyncMock(return_value=feature)
        mock_registry.analyze_conflicts = AsyncMock(
            return_value=_make_conflict_report(
                "f1",
                claims=["src/a.py", "src/b.py"],
                conflicts=[{"feature_id": "f2", "overlapping_keys": ["src/a.py", "src/b.py"]}],
                feasibility=Feasibility.SEQUENTIAL,
            )
        )

        result = await service.run_pre_merge_checks("f1")

        assert result.passed is False
        assert result.checks["no_resource_conflicts"] is False

    @pytest.mark.asyncio
    async def test_partial_conflicts_pass(self, service, mock_registry, mock_db):
        """PARTIAL conflicts → resource check passes."""
        feature = _make_feature(
            "f1",
            resource_claims=["src/a.py", "src/b.py", "src/c.py"],
            metadata={"merge_queue": {"status": "queued"}},
        )
        mock_registry.get_feature = AsyncMock(return_value=feature)
        mock_registry.analyze_conflicts = AsyncMock(
            return_value=_make_conflict_report(
                "f1",
                claims=["src/a.py", "src/b.py", "src/c.py"],
                conflicts=[{"feature_id": "f2", "overlapping_keys": ["src/a.py"]}],
                feasibility=Feasibility.PARTIAL,
            )
        )

        result = await service.run_pre_merge_checks("f1")

        assert result.checks["no_resource_conflicts"] is True

    @pytest.mark.asyncio
    async def test_not_in_queue(self, service, mock_registry, mock_db):
        """Feature not in merge queue → fail that check."""
        feature = _make_feature("f1", resource_claims=["src/a.py"], metadata={})
        mock_registry.get_feature = AsyncMock(return_value=feature)
        mock_registry.analyze_conflicts = AsyncMock(
            return_value=_make_conflict_report("f1", ["src/a.py"])
        )

        result = await service.run_pre_merge_checks("f1")

        assert result.passed is False
        assert result.checks["in_merge_queue"] is False

    @pytest.mark.asyncio
    async def test_updates_status_to_ready(self, service, mock_registry, mock_db):
        """Passing checks should update merge status to READY."""
        feature = _make_feature(
            "f1",
            resource_claims=["src/a.py"],
            metadata={"merge_queue": {"status": "queued"}},
        )
        mock_registry.get_feature = AsyncMock(return_value=feature)
        mock_registry.analyze_conflicts = AsyncMock(
            return_value=_make_conflict_report("f1", ["src/a.py"])
        )

        await service.run_pre_merge_checks("f1")

        call_args = mock_db.update.call_args
        data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert data["metadata"]["merge_queue"]["status"] == "ready"

    @pytest.mark.asyncio
    async def test_updates_status_to_blocked(self, service, mock_registry, mock_db):
        """Failing checks should update merge status to BLOCKED."""
        feature = _make_feature(
            "f1",
            resource_claims=["src/a.py"],
            status="completed",
            metadata={"merge_queue": {"status": "queued"}},
        )
        mock_registry.get_feature = AsyncMock(return_value=feature)
        mock_registry.analyze_conflicts = AsyncMock(
            return_value=_make_conflict_report("f1", ["src/a.py"])
        )

        await service.run_pre_merge_checks("f1")

        call_args = mock_db.update.call_args
        data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert data["metadata"]["merge_queue"]["status"] == "blocked"


class TestMarkMerged:
    """Tests for marking features as merged."""

    @pytest.mark.asyncio
    async def test_mark_merged_success(self, service, mock_registry):
        """Successfully mark a feature as merged."""
        feature = _make_feature("f1")
        mock_registry.get_feature = AsyncMock(return_value=feature)
        mock_registry.deregister = AsyncMock(
            return_value=DeregisterResult(
                success=True, feature_id="f1", status="completed"
            )
        )

        result = await service.mark_merged("f1")

        assert result is True
        mock_registry.deregister.assert_called_once_with("f1", status="completed")

    @pytest.mark.asyncio
    async def test_mark_merged_not_found(self, service, mock_registry):
        """Marking a non-existent feature returns False."""
        mock_registry.get_feature = AsyncMock(return_value=None)

        result = await service.mark_merged("nonexistent")

        assert result is False


class TestRemoveFromQueue:
    """Tests for removing features from the queue without merging."""

    @pytest.mark.asyncio
    async def test_remove_from_queue(self, service, mock_registry, mock_db):
        """Remove a feature from the merge queue."""
        feature = _make_feature(
            "f1",
            metadata={
                "merge_queue": {"status": "queued"},
                "other_data": "preserved",
            },
        )
        mock_registry.get_feature = AsyncMock(return_value=feature)

        result = await service.remove_from_queue("f1")

        assert result is True
        call_args = mock_db.update.call_args
        data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert "merge_queue" not in data["metadata"]
        assert data["metadata"]["other_data"] == "preserved"

    @pytest.mark.asyncio
    async def test_remove_not_in_queue(self, service, mock_registry):
        """Removing a feature not in the queue returns False."""
        feature = _make_feature("f1", metadata={})
        mock_registry.get_feature = AsyncMock(return_value=feature)

        result = await service.remove_from_queue("f1")

        assert result is False

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self, service, mock_registry):
        """Removing a non-existent feature returns False."""
        mock_registry.get_feature = AsyncMock(return_value=None)

        result = await service.remove_from_queue("nonexistent")

        assert result is False


class TestMergeStatusEnum:
    """Tests for MergeStatus enum values."""

    def test_all_statuses(self):
        assert MergeStatus.QUEUED.value == "queued"
        assert MergeStatus.PRE_MERGE_CHECK.value == "pre_merge_check"
        assert MergeStatus.READY.value == "ready"
        assert MergeStatus.MERGING.value == "merging"
        assert MergeStatus.MERGED.value == "merged"
        assert MergeStatus.BLOCKED.value == "blocked"


class TestMergeQueueEntryFromFeature:
    """Tests for MergeQueueEntry.from_feature factory."""

    def test_from_feature_defaults(self):
        feature = _make_feature("f1", merge_priority=3, branch_name="branch/f1")
        entry = MergeQueueEntry.from_feature(feature)

        assert entry.feature_id == "f1"
        assert entry.branch_name == "branch/f1"
        assert entry.merge_priority == 3
        assert entry.merge_status == MergeStatus.QUEUED
        assert entry.pr_url is None

    def test_from_feature_with_overrides(self):
        feature = _make_feature("f1")
        entry = MergeQueueEntry.from_feature(
            feature,
            merge_status=MergeStatus.READY,
            pr_url="https://github.com/pr/1",
        )

        assert entry.merge_status == MergeStatus.READY
        assert entry.pr_url == "https://github.com/pr/1"

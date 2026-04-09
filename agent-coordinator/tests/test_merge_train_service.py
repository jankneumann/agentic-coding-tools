"""Tests for MergeTrainService (wp-integration task 5.2/5.3 orchestration layer).

This service is the bridge between the pure train engine in ``merge_train.py``
(which operates on in-memory ``TrainEntry`` lists) and the persistent state in
``feature_registry.metadata["merge_queue"]``. It provides:

    - compose_train()         → load entries, call engine, persist back
    - eject_from_train()      → locate entry + successors, call engine, persist
    - get_train_status()      → list entries by train_id
    - report_spec_result()    → SPECULATING → SPEC_PASSED / BLOCKED transition

Tests use fake DB + registry + git_adapter so no infra is required. The goal
is to verify: (a) the load/save round-trip preserves train state, (b) the
wrapper correctly pairs successors with ejections, (c) refresh-architecture
integration degrades to "full_test_suite" on RefreshClientUnavailable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.feature_registry import Feature
from src.merge_train_service import MergeTrainService
from src.merge_train_types import (
    MergeTrainStatus,
)
from src.refresh_rpc_client import RefreshClientUnavailable

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


def _make_feature(
    feature_id: str,
    *,
    merge_priority: int = 5,
    resource_claims: list[str] | None = None,
    merge_queue_meta: dict[str, Any] | None = None,
    branch_name: str | None = None,
) -> Feature:
    metadata: dict[str, Any] = {}
    if merge_queue_meta is not None:
        metadata["merge_queue"] = merge_queue_meta
    return Feature(
        feature_id=feature_id,
        title=f"{feature_id} title",
        status="active",
        registered_by="test",
        registered_at=datetime.now(UTC),
        updated_at=None,
        completed_at=None,
        resource_claims=resource_claims or [],
        branch_name=branch_name or f"branch/{feature_id}",
        merge_priority=merge_priority,
        metadata=metadata,
    )


@dataclass
class _FakeGitAdapter:
    """Minimal GitAdapter fake — returns successful speculative merges."""

    speculated: list[tuple[str, str, str]] = field(default_factory=list)
    deleted_refs: list[str] = field(default_factory=list)

    def create_speculative_ref(
        self,
        base_ref: str,
        feature_branch: str,
        ref_name: str,
    ) -> Any:
        from src.git_adapter import MergeTreeResult

        self.speculated.append((base_ref, feature_branch, ref_name))
        return MergeTreeResult(
            success=True,
            tree_oid=f"tree_{ref_name}",
            commit_sha=f"sha_{ref_name}",
            conflict_files=[],
            error=None,
        )

    def delete_speculative_refs(self, ref_names: list[str]) -> int:
        self.deleted_refs.extend(ref_names)
        return len(ref_names)

    def fast_forward_main(self, target_sha: str) -> None:
        pass

    def get_changed_files(self, ref: str) -> list[str]:
        return []

    def list_refs_matching(self, pattern: str) -> list[str]:
        return []


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    db.update = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_registry() -> MagicMock:
    reg = MagicMock()
    reg.get_active_features = AsyncMock(return_value=[])
    reg.get_feature = AsyncMock(return_value=None)
    return reg


@pytest.fixture
def git_adapter() -> _FakeGitAdapter:
    return _FakeGitAdapter()


@pytest.fixture
def service(
    mock_db: MagicMock,
    mock_registry: MagicMock,
    git_adapter: _FakeGitAdapter,
) -> MergeTrainService:
    return MergeTrainService(
        db=mock_db, registry=mock_registry, git_adapter=git_adapter
    )


# ---------------------------------------------------------------------------
# _load_entries
# ---------------------------------------------------------------------------


class TestLoadEntries:
    @pytest.mark.asyncio
    async def test_loads_entries_with_merge_queue_metadata(
        self,
        service: MergeTrainService,
        mock_registry: MagicMock,
    ) -> None:
        f1 = _make_feature(
            "f1",
            merge_priority=10,
            resource_claims=["api:POST /v1/x"],
            merge_queue_meta={
                "status": "queued",
                "train_id": None,
                "decomposition": "branch",
            },
        )
        f2 = _make_feature(
            "f2",
            merge_priority=5,
            resource_claims=["db:schema:users"],
            merge_queue_meta={
                "status": "spec_passed",
                "train_id": "abc",
                "partition_id": "p1",
                "train_position": 1,
                "decomposition": "stacked",
                "stack_position": 2,
            },
        )
        # f3 has no merge_queue metadata — must be skipped
        f3 = _make_feature("f3")
        mock_registry.get_active_features = AsyncMock(return_value=[f1, f2, f3])

        entries = await service._load_entries()

        assert len(entries) == 2
        assert {e.feature_id for e in entries} == {"f1", "f2"}
        e1 = next(e for e in entries if e.feature_id == "f1")
        e2 = next(e for e in entries if e.feature_id == "f2")
        assert e1.status == MergeTrainStatus.QUEUED
        assert e1.resource_claims == ["api:POST /v1/x"]
        assert e1.merge_priority == 10
        assert e2.status == MergeTrainStatus.SPEC_PASSED
        assert e2.train_id == "abc"
        assert e2.partition_id == "p1"
        assert e2.train_position == 1
        assert e2.decomposition == "stacked"
        assert e2.stack_position == 2

    @pytest.mark.asyncio
    async def test_skips_features_without_merge_queue_meta(
        self,
        service: MergeTrainService,
        mock_registry: MagicMock,
    ) -> None:
        mock_registry.get_active_features = AsyncMock(
            return_value=[_make_feature("f1")]
        )
        entries = await service._load_entries()
        assert entries == []


# ---------------------------------------------------------------------------
# compose_train
# ---------------------------------------------------------------------------


class TestComposeTrain:
    @pytest.mark.asyncio
    async def test_authorization_enforced(
        self,
        service: MergeTrainService,
        mock_registry: MagicMock,
    ) -> None:
        """Trust level < 3 → TrainAuthorizationError."""
        from src.merge_train import TrainAuthorizationError

        mock_registry.get_active_features = AsyncMock(return_value=[])
        with pytest.raises(TrainAuthorizationError):
            await service.compose_train(caller_trust_level=2)

    @pytest.mark.asyncio
    async def test_compose_persists_each_entry(
        self,
        service: MergeTrainService,
        mock_registry: MagicMock,
        mock_db: MagicMock,
    ) -> None:
        """After composing, each entry's new state is written back to feature_registry."""
        f1 = _make_feature(
            "f1",
            resource_claims=["api:POST /v1/x"],
            merge_queue_meta={"status": "queued"},
        )
        mock_registry.get_active_features = AsyncMock(return_value=[f1])

        composition = await service.compose_train(caller_trust_level=3)

        assert composition.train_id is not None
        # _save_entry was called at least once (verified via db.update)
        assert mock_db.update.called
        call = mock_db.update.call_args
        # Match clause
        assert call.kwargs["match"] == {"feature_id": "f1"}
        # Metadata contains merge_queue with a new status (SPECULATING or SPEC_PASSED)
        meta = call.kwargs["data"]["metadata"]["merge_queue"]
        assert meta["status"] in (
            "speculating",
            "spec_passed",
        ), f"unexpected status: {meta['status']}"
        assert meta["train_id"] == composition.train_id

    @pytest.mark.asyncio
    async def test_empty_queue_returns_empty_composition(
        self,
        service: MergeTrainService,
        mock_registry: MagicMock,
    ) -> None:
        mock_registry.get_active_features = AsyncMock(return_value=[])
        composition = await service.compose_train(caller_trust_level=3)
        assert composition.partitions == []
        assert composition.cross_partition_entries == []


# ---------------------------------------------------------------------------
# eject_from_train
# ---------------------------------------------------------------------------


class TestEjectFromTrain:
    @pytest.mark.asyncio
    async def test_ejects_entry_and_persists(
        self,
        service: MergeTrainService,
        mock_registry: MagicMock,
        mock_db: MagicMock,
    ) -> None:
        """Ejection lowers priority, updates status, writes to DB."""
        f1 = _make_feature(
            "f1",
            merge_priority=20,
            resource_claims=["api:POST /v1/x"],
            merge_queue_meta={
                "status": "speculating",
                "train_id": "t1",
                "partition_id": "p1",
                "train_position": 0,
                "eject_count": 0,
                "original_priority": 20,
            },
        )
        mock_registry.get_active_features = AsyncMock(return_value=[f1])

        result = await service.eject_from_train(
            feature_id="f1",
            reason="CI failure: test_auth",
            caller_agent_id="operator-1",
            caller_trust_level=3,
        )

        assert result is not None
        assert result.ejected is True
        assert result.abandoned is False
        # Verify DB persisted the ejection
        calls_for_f1 = [
            c for c in mock_db.update.call_args_list
            if c.kwargs["match"] == {"feature_id": "f1"}
        ]
        assert len(calls_for_f1) == 1
        meta = calls_for_f1[0].kwargs["data"]["metadata"]["merge_queue"]
        assert meta["status"] == "ejected"
        assert meta["eject_count"] == 1
        assert meta["last_eject_reason"] == "CI failure: test_auth"

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_feature(
        self,
        service: MergeTrainService,
        mock_registry: MagicMock,
    ) -> None:
        mock_registry.get_active_features = AsyncMock(return_value=[])
        result = await service.eject_from_train(
            feature_id="nonexistent",
            reason="x",
            caller_agent_id="op",
            caller_trust_level=3,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_successors_requeued_when_dependent(
        self,
        service: MergeTrainService,
        mock_registry: MagicMock,
        mock_db: MagicMock,
    ) -> None:
        """Successors whose claims overlap with the ejected entry get requeued."""
        f1 = _make_feature(
            "f1",
            merge_priority=20,
            resource_claims=["api:POST /v1/x"],
            merge_queue_meta={
                "status": "speculating",
                "train_id": "t1",
                "partition_id": "p1",
                "train_position": 0,
                "eject_count": 0,
                "original_priority": 20,
            },
        )
        # f2 shares the api: prefix — dependent
        f2 = _make_feature(
            "f2",
            resource_claims=["api:GET /v1/x"],
            merge_queue_meta={
                "status": "speculating",
                "train_id": "t1",
                "partition_id": "p1",
                "train_position": 1,
            },
        )
        mock_registry.get_active_features = AsyncMock(return_value=[f1, f2])

        result = await service.eject_from_train(
            feature_id="f1",
            reason="boom",
            caller_agent_id="op",
            caller_trust_level=3,
        )
        assert result is not None
        assert "f2" in result.requeued_successors


# ---------------------------------------------------------------------------
# get_train_status
# ---------------------------------------------------------------------------


class TestGetTrainStatus:
    @pytest.mark.asyncio
    async def test_returns_entries_for_train_id(
        self,
        service: MergeTrainService,
        mock_registry: MagicMock,
    ) -> None:
        f1 = _make_feature(
            "f1",
            merge_queue_meta={
                "status": "speculating",
                "train_id": "t1",
                "train_position": 0,
            },
        )
        f2 = _make_feature(
            "f2",
            merge_queue_meta={
                "status": "speculating",
                "train_id": "t1",
                "train_position": 1,
            },
        )
        f3 = _make_feature(
            "f3",
            merge_queue_meta={"status": "speculating", "train_id": "t2"},
        )
        mock_registry.get_active_features = AsyncMock(return_value=[f1, f2, f3])

        entries = await service.get_train_status("t1")
        assert len(entries) == 2
        assert {e.feature_id for e in entries} == {"f1", "f2"}

    @pytest.mark.asyncio
    async def test_empty_for_unknown_train(
        self,
        service: MergeTrainService,
        mock_registry: MagicMock,
    ) -> None:
        mock_registry.get_active_features = AsyncMock(return_value=[])
        assert await service.get_train_status("missing") == []


# ---------------------------------------------------------------------------
# report_spec_result
# ---------------------------------------------------------------------------


class TestReportSpecResult:
    @pytest.mark.asyncio
    async def test_passed_transitions_to_spec_passed(
        self,
        service: MergeTrainService,
        mock_registry: MagicMock,
        mock_db: MagicMock,
    ) -> None:
        f1 = _make_feature(
            "f1",
            merge_queue_meta={
                "status": "speculating",
                "train_id": "t1",
            },
        )
        mock_registry.get_active_features = AsyncMock(return_value=[f1])

        result = await service.report_spec_result("f1", passed=True)

        assert result is not None
        assert result.status == MergeTrainStatus.SPEC_PASSED
        meta = mock_db.update.call_args.kwargs["data"]["metadata"]["merge_queue"]
        assert meta["status"] == "spec_passed"

    @pytest.mark.asyncio
    async def test_failed_transitions_to_blocked(
        self,
        service: MergeTrainService,
        mock_registry: MagicMock,
        mock_db: MagicMock,
    ) -> None:
        f1 = _make_feature(
            "f1",
            merge_queue_meta={
                "status": "speculating",
                "train_id": "t1",
            },
        )
        mock_registry.get_active_features = AsyncMock(return_value=[f1])

        result = await service.report_spec_result(
            "f1", passed=False, error_message="test_users failed"
        )
        assert result is not None
        assert result.status == MergeTrainStatus.BLOCKED

    @pytest.mark.asyncio
    async def test_idempotent_on_non_speculating(
        self,
        service: MergeTrainService,
        mock_registry: MagicMock,
    ) -> None:
        """Calling report_spec_result on an entry already SPEC_PASSED is a no-op."""
        f1 = _make_feature(
            "f1",
            merge_queue_meta={"status": "spec_passed", "train_id": "t1"},
        )
        mock_registry.get_active_features = AsyncMock(return_value=[f1])
        result = await service.report_spec_result("f1", passed=True)
        assert result is not None
        assert result.status == MergeTrainStatus.SPEC_PASSED

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_feature(
        self,
        service: MergeTrainService,
        mock_registry: MagicMock,
    ) -> None:
        mock_registry.get_active_features = AsyncMock(return_value=[])
        assert await service.report_spec_result("nope", passed=True) is None


# ---------------------------------------------------------------------------
# refresh-architecture integration (task 5.8)
# ---------------------------------------------------------------------------


class TestRefreshArchitectureIntegration:
    """compose_train probes is_graph_stale before speculating; falls back cleanly."""

    @pytest.mark.asyncio
    async def test_unavailable_client_does_not_block(
        self,
        mock_db: MagicMock,
        mock_registry: MagicMock,
        git_adapter: _FakeGitAdapter,
    ) -> None:
        """If refresh client returns sentinel, compose_train proceeds with full suite flag."""
        fake_refresh = MagicMock()
        fake_refresh.is_graph_stale = MagicMock(
            return_value=RefreshClientUnavailable(reason="timeout")
        )
        fake_refresh.trigger_refresh = MagicMock()

        service = MergeTrainService(
            db=mock_db,
            registry=mock_registry,
            git_adapter=git_adapter,
            refresh_client=fake_refresh,
        )

        f1 = _make_feature(
            "f1",
            resource_claims=["api:POST /v1/x"],
            merge_queue_meta={"status": "queued"},
        )
        mock_registry.get_active_features = AsyncMock(return_value=[f1])

        composition = await service.compose_train(caller_trust_level=3)
        # Proceeded without raising
        assert composition.train_id is not None
        # is_graph_stale was called
        fake_refresh.is_graph_stale.assert_called_once()
        # trigger_refresh was NOT called (client is unavailable)
        fake_refresh.trigger_refresh.assert_not_called()
        # full_test_suite flag is set on the composition
        assert composition.full_test_suite_required is True

    @pytest.mark.asyncio
    async def test_stale_triggers_refresh(
        self,
        mock_db: MagicMock,
        mock_registry: MagicMock,
        git_adapter: _FakeGitAdapter,
    ) -> None:
        """If is_graph_stale says stale and nothing in flight, trigger_refresh is called."""
        fake_refresh = MagicMock()
        fake_refresh.is_graph_stale = MagicMock(
            return_value={
                "stale": True,
                "graph_mtime": None,
                "node_count": 0,
                "refresh_in_flight": False,
                "current_refresh_id": None,
            }
        )
        fake_refresh.trigger_refresh = MagicMock(
            return_value={
                "refresh_id": "r1",
                "is_new": True,
                "estimated_duration_s": 60,
            }
        )

        service = MergeTrainService(
            db=mock_db,
            registry=mock_registry,
            git_adapter=git_adapter,
            refresh_client=fake_refresh,
        )
        mock_registry.get_active_features = AsyncMock(return_value=[])

        await service.compose_train(caller_trust_level=3)
        fake_refresh.trigger_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_fresh_graph_skips_trigger(
        self,
        mock_db: MagicMock,
        mock_registry: MagicMock,
        git_adapter: _FakeGitAdapter,
    ) -> None:
        fake_refresh = MagicMock()
        fake_refresh.is_graph_stale = MagicMock(
            return_value={
                "stale": False,
                "graph_mtime": "2026-04-09T00:00:00+00:00",
                "node_count": 1000,
                "refresh_in_flight": False,
                "current_refresh_id": None,
            }
        )
        fake_refresh.trigger_refresh = MagicMock()

        service = MergeTrainService(
            db=mock_db,
            registry=mock_registry,
            git_adapter=git_adapter,
            refresh_client=fake_refresh,
        )
        mock_registry.get_active_features = AsyncMock(return_value=[])
        await service.compose_train(caller_trust_level=3)
        fake_refresh.trigger_refresh.assert_not_called()


# ---------------------------------------------------------------------------
# MergeTrainSweeper (task 5.9)
# ---------------------------------------------------------------------------


class TestMergeTrainSweeper:
    """The sweeper is a WatchdogService-shaped background task.

    It wraps ``MergeTrainService.compose_train`` and swallows all exceptions
    per the invariant: background sweeps MUST NEVER crash the event loop.
    Tests only exercise ``run_once()`` — the ``_loop()`` wrapper is a thin
    retry shell tested indirectly via start/stop lifecycle.
    """

    @pytest.mark.asyncio
    async def test_run_once_calls_compose_train(
        self,
        service: MergeTrainService,
        mock_registry: MagicMock,
    ) -> None:
        from src.merge_train_service import MergeTrainSweeper

        mock_registry.get_active_features = AsyncMock(return_value=[])
        # Stub out the refresh probe so compose_train doesn't try to shell out.
        service._refresh_client = MagicMock()
        service._refresh_client.is_graph_stale = MagicMock(
            return_value={
                "stale": False,
                "graph_mtime": "2026-04-09T00:00:00+00:00",
                "node_count": 0,
                "refresh_in_flight": False,
                "current_refresh_id": None,
            }
        )

        sweeper = MergeTrainSweeper(service=service, interval_seconds=60)
        await sweeper.run_once()

        # One compose_train call triggers one get_active_features lookup
        # (via _load_entries) + one more (inside compose_train to persist).
        assert mock_registry.get_active_features.await_count >= 1

    @pytest.mark.asyncio
    async def test_run_once_swallows_exceptions(
        self,
        service: MergeTrainService,
    ) -> None:
        """Any exception inside compose_train must be caught by the sweeper."""
        from src.merge_train_service import MergeTrainSweeper

        boom_service = MagicMock()
        boom_service.compose_train = AsyncMock(side_effect=RuntimeError("boom"))
        sweeper = MergeTrainSweeper(service=boom_service, interval_seconds=60)

        # Must not raise
        await sweeper.run_once()
        boom_service.compose_train.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(
        self,
        service: MergeTrainService,
        mock_registry: MagicMock,
    ) -> None:
        """start() launches the loop; stop() cancels it cleanly."""
        import asyncio

        from src.merge_train_service import MergeTrainSweeper

        mock_registry.get_active_features = AsyncMock(return_value=[])
        service._refresh_client = MagicMock()
        service._refresh_client.is_graph_stale = MagicMock(
            return_value={
                "stale": False,
                "graph_mtime": "2026-04-09T00:00:00+00:00",
                "node_count": 0,
                "refresh_in_flight": False,
                "current_refresh_id": None,
            }
        )

        sweeper = MergeTrainSweeper(service=service, interval_seconds=0.01)
        assert sweeper.running is False
        await sweeper.start()
        assert sweeper.running is True
        # Let the loop run at least once.
        await asyncio.sleep(0.05)
        await sweeper.stop()
        assert sweeper.running is False

    def test_default_interval_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MERGE_TRAIN_SWEEP_INTERVAL_SECONDS overrides the default."""
        from src.merge_train_service import MergeTrainSweeper

        monkeypatch.setenv("MERGE_TRAIN_SWEEP_INTERVAL_SECONDS", "123")
        sweeper = MergeTrainSweeper(service=MagicMock())
        assert sweeper.interval_seconds == 123

    def test_default_interval_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without the env var, the sweeper uses DEFAULT_SWEEP_INTERVAL_SECONDS."""
        from src.merge_train_service import MergeTrainSweeper
        from src.merge_train_types import DEFAULT_SWEEP_INTERVAL_SECONDS

        monkeypatch.delenv("MERGE_TRAIN_SWEEP_INTERVAL_SECONDS", raising=False)
        sweeper = MergeTrainSweeper(service=MagicMock())
        assert sweeper.interval_seconds == DEFAULT_SWEEP_INTERVAL_SECONDS


# ---------------------------------------------------------------------------
# Full lifecycle integration scenarios (task 5.1)
# ---------------------------------------------------------------------------


class _StatefulRegistry:
    """Minimal in-memory feature registry fake for lifecycle tests.

    Supports the subset of FeatureRegistryService methods the train service
    uses: ``get_active_features()``. Updates come through the DB layer, which
    writes back to ``metadata["merge_queue"]`` via :meth:`apply_db_update`.
    """

    def __init__(self, features: list[Feature]) -> None:
        self._features: dict[str, Feature] = {f.feature_id: f for f in features}

    async def get_active_features(self) -> list[Feature]:
        # Return fresh Feature objects so each call sees the latest metadata.
        return list(self._features.values())

    def apply_db_update(self, feature_id: str, new_metadata: dict[str, Any]) -> None:
        feature = self._features.get(feature_id)
        if feature is None:
            return
        self._features[feature_id] = Feature(
            feature_id=feature.feature_id,
            title=feature.title,
            status=feature.status,
            registered_by=feature.registered_by,
            registered_at=feature.registered_at,
            updated_at=feature.updated_at,
            completed_at=feature.completed_at,
            resource_claims=feature.resource_claims,
            branch_name=feature.branch_name,
            merge_priority=feature.merge_priority,
            metadata=new_metadata,
        )


class _StatefulDB:
    """In-memory DB that routes updates back into the stateful registry."""

    def __init__(self, registry: _StatefulRegistry) -> None:
        self._registry = registry
        self.update_calls: list[dict[str, Any]] = []

    async def update(
        self,
        table: str,
        *,
        match: dict[str, Any],
        data: dict[str, Any],
        return_data: bool = True,
    ) -> list[dict[str, Any]]:
        self.update_calls.append({"table": table, "match": match, "data": data})
        if table == "feature_registry" and "feature_id" in match:
            feature_id = match["feature_id"]
            new_meta = data.get("metadata", {})
            self._registry.apply_db_update(feature_id, new_meta)
        return []


class TestFullLifecycle:
    """End-to-end integration tests through the real ``MergeTrainService``.

    These tests use a stateful in-memory registry + DB so a compose → persist
    → re-load round-trip actually observes the new state. They exercise the
    three lifecycle scenarios required by task 5.1:

      1. Happy path: enqueue → compose → spec pass → merge-ready
      2. BLOCKED recovery: spec fail → BLOCKED → 1h age-out → re-queued
      3. Ejection + re-speculation: eject one entry, successors re-queued
    """

    def _make_queued_feature(
        self,
        feature_id: str,
        *,
        priority: int = 5,
        resource_claims: list[str] | None = None,
    ) -> Feature:
        return _make_feature(
            feature_id,
            merge_priority=priority,
            resource_claims=resource_claims or ["api:POST /v1/" + feature_id],
            merge_queue_meta={"status": "queued", "decomposition": "branch"},
        )

    def _make_service(
        self, features: list[Feature]
    ) -> tuple[MergeTrainService, _StatefulRegistry, _StatefulDB]:
        registry = _StatefulRegistry(features)
        db = _StatefulDB(registry)
        git = _FakeGitAdapter()
        # Stub refresh probe so it doesn't shell out.
        fake_refresh = MagicMock()
        fake_refresh.is_graph_stale = MagicMock(
            return_value={
                "stale": False,
                "graph_mtime": "2026-04-09T00:00:00+00:00",
                "node_count": 1000,
                "refresh_in_flight": False,
                "current_refresh_id": None,
            }
        )
        fake_refresh.trigger_refresh = MagicMock()
        service = MergeTrainService(
            db=db,  # type: ignore[arg-type]
            registry=registry,  # type: ignore[arg-type]
            git_adapter=git,
            refresh_client=fake_refresh,
        )
        return service, registry, db

    @pytest.mark.asyncio
    async def test_happy_path_compose_then_all_pass(self) -> None:
        """Compose 3 independent features, then report all as passed."""
        features = [
            self._make_queued_feature("f1", resource_claims=["api:POST /v1/a"]),
            self._make_queued_feature("f2", resource_claims=["db:schema:users"]),
            self._make_queued_feature("f3", resource_claims=["flag:dark_mode"]),
        ]
        service, registry, _db = self._make_service(features)

        composition = await service.compose_train(caller_trust_level=3)

        # Each feature lives in its own partition (disjoint claim prefixes).
        assert composition.train_id is not None
        assert len(composition.partitions) == 3
        statuses_after_compose = set()
        for p in composition.partitions:
            for e in p.entries:
                statuses_after_compose.add(e.status)
        # Should have SPECULATING (position 0 gets immediate spec_passed when
        # the git adapter reports success) or SPEC_PASSED.
        assert statuses_after_compose <= {
            MergeTrainStatus.SPECULATING,
            MergeTrainStatus.SPEC_PASSED,
        }

        # Re-load should see the persisted train_id on each.
        entries = await service._load_entries()
        assert all(e.train_id == composition.train_id for e in entries)

        # Transition any SPECULATING → SPEC_PASSED via the CI callback.
        for e in entries:
            if e.status == MergeTrainStatus.SPECULATING:
                result = await service.report_spec_result(
                    e.feature_id, passed=True
                )
                assert result is not None
                assert result.status == MergeTrainStatus.SPEC_PASSED

        # Final state: every entry is SPEC_PASSED (i.e. ready to merge).
        final = await service._load_entries()
        assert all(e.status == MergeTrainStatus.SPEC_PASSED for e in final), (
            [(e.feature_id, e.status) for e in final]
        )

    @pytest.mark.asyncio
    async def test_blocked_recovery_after_aging(self) -> None:
        """BLOCKED entries with checked_at > 1h ago get re-queued on next compose."""
        from datetime import timedelta

        features = [
            self._make_queued_feature("f1", resource_claims=["api:POST /v1/a"]),
        ]
        service, registry, _db = self._make_service(features)

        # First compose → f1 becomes SPECULATING/SPEC_PASSED
        await service.compose_train(caller_trust_level=3)

        # Simulate CI failure → BLOCKED
        result = await service.report_spec_result(
            "f1", passed=False, error_message="test_auth.py failed"
        )
        assert result is not None
        assert result.status == MergeTrainStatus.BLOCKED

        # Manually age the checked_at timestamp so the next compose re-evaluates.
        aged_time = datetime.now(UTC) - timedelta(hours=2)
        feature = registry._features["f1"]
        new_meta = dict(feature.metadata)
        new_meta["merge_queue"] = {
            **new_meta["merge_queue"],
            "checked_at": aged_time.isoformat(),
        }
        registry.apply_db_update("f1", new_meta)

        # Second compose → BLOCKED gets re-evaluated to QUEUED, then re-speculated.
        await service.compose_train(caller_trust_level=3)
        entries = await service._load_entries()
        assert entries[0].status != MergeTrainStatus.BLOCKED
        assert entries[0].metadata.get("blocked_reason") is None

    @pytest.mark.asyncio
    async def test_ejection_decrements_priority_and_persists(self) -> None:
        """Ejecting an entry lowers its priority and marks it EJECTED."""
        features = [
            self._make_queued_feature("f1", resource_claims=["api:POST /v1/a"]),
        ]
        service, _registry, _db = self._make_service(features)

        # Compose so f1 is inside an active train.
        await service.compose_train(caller_trust_level=3)

        # Eject — caller has trust 3 (implicit admin, passes authorization).
        result = await service.eject_from_train(
            "f1",
            reason="ci_timeout",
            caller_agent_id="ops-agent",
            caller_trust_level=3,
        )
        assert result is not None
        assert result.ejected is True
        assert result.abandoned is False
        # Priority decrement of 10 → pinned to MIN via clamping
        assert result.priority_after < 5

        # Persisted state: f1 is now EJECTED with eject_count=1
        final = await service._load_entries()
        assert len(final) == 1
        assert final[0].status == MergeTrainStatus.EJECTED
        assert final[0].eject_count == 1
        assert final[0].last_eject_reason == "ci_timeout"

"""Tests for feature_registry service (Task 7.1)."""

from __future__ import annotations

import json

import pytest
from httpx import Response

from src.feature_registry import (
    DeregisterResult,
    Feature,
    FeatureRegistryService,
    RegisterResult,
)


class TestRegisterFeature:
    """Tests for registering features with resource claims."""

    @pytest.mark.asyncio
    async def test_register_new_feature(self, mock_supabase, db_client):
        """Successfully register a new feature."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/register_feature"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "feature_id": "add-auth",
                    "action": "registered",
                },
            )
        )

        service = FeatureRegistryService(db_client)
        result = await service.register(
            feature_id="add-auth",
            resource_claims=["src/auth.py", "api:/auth/login", "db:users"],
            title="Add Authentication",
        )

        assert result.success is True
        assert result.feature_id == "add-auth"
        assert result.action == "registered"

    @pytest.mark.asyncio
    async def test_register_sends_correct_params(self, mock_supabase, db_client):
        """Register RPC should send all parameters correctly."""
        captured: dict = {}

        def capture(request):
            captured.update(json.loads(request.content))
            return Response(
                200,
                json={
                    "success": True,
                    "feature_id": "add-auth",
                    "action": "registered",
                },
            )

        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/register_feature"
        ).mock(side_effect=capture)

        service = FeatureRegistryService(db_client)
        await service.register(
            feature_id="add-auth",
            resource_claims=["src/auth.py", "api:/auth/login"],
            title="Add Auth",
            branch_name="openspec/add-auth",
            merge_priority=3,
            metadata={"plan_revision": 1},
        )

        assert captured["p_feature_id"] == "add-auth"
        assert captured["p_title"] == "Add Auth"
        assert captured["p_resource_claims"] == ["src/auth.py", "api:/auth/login"]
        assert captured["p_branch_name"] == "openspec/add-auth"
        assert captured["p_merge_priority"] == 3
        assert captured["p_metadata"] == {"plan_revision": 1}

    @pytest.mark.asyncio
    async def test_register_update_existing(self, mock_supabase, db_client):
        """Re-registering an active feature should update it."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/register_feature"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "feature_id": "add-auth",
                    "action": "updated",
                },
            )
        )

        service = FeatureRegistryService(db_client)
        result = await service.register(
            feature_id="add-auth",
            resource_claims=["src/auth.py", "src/middleware.py"],
        )

        assert result.success is True
        assert result.action == "updated"

    @pytest.mark.asyncio
    async def test_register_uses_default_agent_id(self, mock_supabase, db_client):
        """Register should use config agent_id when none specified."""
        captured: dict = {}

        def capture(request):
            captured.update(json.loads(request.content))
            return Response(
                200,
                json={"success": True, "feature_id": "f1", "action": "registered"},
            )

        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/register_feature"
        ).mock(side_effect=capture)

        service = FeatureRegistryService(db_client)
        await service.register(feature_id="f1", resource_claims=[])

        assert captured["p_agent_id"] == "test-agent-1"


class TestDeregisterFeature:
    """Tests for deregistering features."""

    @pytest.mark.asyncio
    async def test_deregister_completed(self, mock_supabase, db_client):
        """Successfully deregister a feature as completed."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/deregister_feature"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "feature_id": "add-auth",
                    "status": "completed",
                },
            )
        )

        service = FeatureRegistryService(db_client)
        result = await service.deregister("add-auth")

        assert result.success is True
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_deregister_cancelled(self, mock_supabase, db_client):
        """Deregister a feature as cancelled."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/deregister_feature"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "feature_id": "add-auth",
                    "status": "cancelled",
                },
            )
        )

        service = FeatureRegistryService(db_client)
        result = await service.deregister("add-auth", status="cancelled")

        assert result.success is True
        assert result.status == "cancelled"

    @pytest.mark.asyncio
    async def test_deregister_not_found(self, mock_supabase, db_client):
        """Deregistering a non-existent feature should fail."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/deregister_feature"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": False,
                    "reason": "feature_not_found_or_not_active",
                },
            )
        )

        service = FeatureRegistryService(db_client)
        result = await service.deregister("nonexistent")

        assert result.success is False
        assert result.reason == "feature_not_found_or_not_active"

    @pytest.mark.asyncio
    async def test_deregister_sends_correct_params(self, mock_supabase, db_client):
        """Deregister should send feature_id and status."""
        captured: dict = {}

        def capture(request):
            captured.update(json.loads(request.content))
            return Response(
                200,
                json={"success": True, "feature_id": "f1", "status": "cancelled"},
            )

        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/deregister_feature"
        ).mock(side_effect=capture)

        service = FeatureRegistryService(db_client)
        await service.deregister("f1", status="cancelled")

        assert captured["p_feature_id"] == "f1"
        assert captured["p_status"] == "cancelled"


class TestGetFeature:
    """Tests for querying features."""

    @pytest.mark.asyncio
    async def test_get_existing_feature(self, mock_supabase, db_client):
        """Get a feature by ID."""
        mock_supabase.get(
            "https://test.supabase.co/rest/v1/feature_registry"
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "feature_id": "add-auth",
                        "title": "Add Authentication",
                        "status": "active",
                        "registered_by": "agent-1",
                        "registered_at": "2026-01-01T00:00:00+00:00",
                        "updated_at": "2026-01-01T00:00:00+00:00",
                        "completed_at": None,
                        "resource_claims": ["src/auth.py", "api:/auth/login"],
                        "branch_name": "openspec/add-auth",
                        "merge_priority": 3,
                        "metadata": {"plan_revision": 1},
                    }
                ],
            )
        )

        service = FeatureRegistryService(db_client)
        feature = await service.get_feature("add-auth")

        assert feature is not None
        assert feature.feature_id == "add-auth"
        assert feature.title == "Add Authentication"
        assert feature.status == "active"
        assert feature.resource_claims == ["src/auth.py", "api:/auth/login"]
        assert feature.merge_priority == 3

    @pytest.mark.asyncio
    async def test_get_nonexistent_feature(self, mock_supabase, db_client):
        """Getting a non-existent feature returns None."""
        mock_supabase.get(
            "https://test.supabase.co/rest/v1/feature_registry"
        ).mock(return_value=Response(200, json=[]))

        service = FeatureRegistryService(db_client)
        feature = await service.get_feature("nonexistent")

        assert feature is None


class TestGetActiveFeatures:
    """Tests for listing active features."""

    @pytest.mark.asyncio
    async def test_get_active_features(self, mock_supabase, db_client):
        """List all active features ordered by priority."""
        mock_supabase.get(
            "https://test.supabase.co/rest/v1/feature_registry"
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "feature_id": "f1",
                        "title": "Feature 1",
                        "status": "active",
                        "registered_by": "agent-1",
                        "registered_at": "2026-01-01T00:00:00+00:00",
                        "updated_at": "2026-01-01T00:00:00+00:00",
                        "completed_at": None,
                        "resource_claims": ["src/a.py"],
                        "branch_name": None,
                        "merge_priority": 3,
                        "metadata": {},
                    },
                    {
                        "feature_id": "f2",
                        "title": "Feature 2",
                        "status": "active",
                        "registered_by": "agent-2",
                        "registered_at": "2026-01-02T00:00:00+00:00",
                        "updated_at": "2026-01-02T00:00:00+00:00",
                        "completed_at": None,
                        "resource_claims": ["src/b.py"],
                        "branch_name": None,
                        "merge_priority": 5,
                        "metadata": {},
                    },
                ],
            )
        )

        service = FeatureRegistryService(db_client)
        features = await service.get_active_features()

        assert len(features) == 2
        assert features[0].feature_id == "f1"
        assert features[1].feature_id == "f2"

    @pytest.mark.asyncio
    async def test_get_active_features_empty(self, mock_supabase, db_client):
        """No active features returns empty list."""
        mock_supabase.get(
            "https://test.supabase.co/rest/v1/feature_registry"
        ).mock(return_value=Response(200, json=[]))

        service = FeatureRegistryService(db_client)
        features = await service.get_active_features()

        assert features == []


class TestFeatureModel:
    """Tests for the Feature dataclass."""

    def test_from_dict_full(self):
        """Feature.from_dict with all fields."""
        data = {
            "feature_id": "f1",
            "title": "Feature 1",
            "status": "active",
            "registered_by": "agent-1",
            "registered_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T12:00:00Z",
            "completed_at": None,
            "resource_claims": ["src/a.py", "api:/test"],
            "branch_name": "openspec/f1",
            "merge_priority": 2,
            "metadata": {"key": "value"},
        }

        feature = Feature.from_dict(data)

        assert feature.feature_id == "f1"
        assert feature.title == "Feature 1"
        assert feature.resource_claims == ["src/a.py", "api:/test"]
        assert feature.branch_name == "openspec/f1"
        assert feature.merge_priority == 2
        assert feature.metadata == {"key": "value"}
        assert feature.registered_at is not None
        assert feature.completed_at is None

    def test_from_dict_minimal(self):
        """Feature.from_dict with minimal fields."""
        data = {
            "feature_id": "f1",
            "status": "active",
            "registered_by": "agent-1",
        }

        feature = Feature.from_dict(data)

        assert feature.feature_id == "f1"
        assert feature.title is None
        assert feature.resource_claims == []
        assert feature.branch_name is None
        assert feature.merge_priority == 5
        assert feature.metadata == {}


class TestResultModels:
    """Tests for result dataclasses."""

    def test_register_result_success(self):
        data = {"success": True, "feature_id": "f1", "action": "registered"}
        result = RegisterResult.from_dict(data)
        assert result.success is True
        assert result.action == "registered"

    def test_register_result_failure(self):
        data = {"success": False, "reason": "feature_not_active"}
        result = RegisterResult.from_dict(data)
        assert result.success is False
        assert result.reason == "feature_not_active"

    def test_deregister_result(self):
        data = {"success": True, "feature_id": "f1", "status": "completed"}
        result = DeregisterResult.from_dict(data)
        assert result.success is True
        assert result.status == "completed"

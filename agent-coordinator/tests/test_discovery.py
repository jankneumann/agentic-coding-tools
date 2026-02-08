"""Tests for the agent discovery service."""

import pytest
from httpx import Response

from src.discovery import (
    AgentInfo,
    CleanupResult,
    DiscoverResult,
    DiscoveryService,
    HeartbeatResult,
    RegisterResult,
)


class TestDiscoveryService:
    """Tests for DiscoveryService."""

    @pytest.mark.asyncio
    async def test_register_success(self, mock_supabase, db_client):
        """Test registering an agent session."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/register_agent_session"
        ).mock(return_value=Response(200, json={
            "success": True,
            "session_id": "test-session-1",
        }))

        service = DiscoveryService(db_client)
        result = await service.register(
            capabilities=["coding", "testing"],
            current_task="Implementing features",
        )

        assert result.success is True
        assert result.session_id == "test-session-1"

    @pytest.mark.asyncio
    async def test_discover_all_agents(self, mock_supabase, db_client):
        """Test discovering all agents."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/discover_agents"
        ).mock(return_value=Response(200, json={
            "agents": [
                {
                    "agent_id": "agent-1",
                    "agent_type": "claude_code",
                    "session_id": "session-1",
                    "capabilities": ["coding", "testing"],
                    "status": "active",
                    "current_task": "Implementing locks",
                    "last_heartbeat": "2024-01-01T12:00:00+00:00",
                    "started_at": "2024-01-01T10:00:00+00:00",
                },
                {
                    "agent_id": "agent-2",
                    "agent_type": "codex",
                    "session_id": "session-2",
                    "capabilities": ["review"],
                    "status": "idle",
                    "current_task": None,
                    "last_heartbeat": "2024-01-01T11:50:00+00:00",
                    "started_at": "2024-01-01T09:00:00+00:00",
                },
            ]
        }))

        service = DiscoveryService(db_client)
        result = await service.discover()

        assert len(result.agents) == 2
        assert result.agents[0].agent_id == "agent-1"
        assert result.agents[0].capabilities == ["coding", "testing"]
        assert result.agents[1].agent_id == "agent-2"
        assert result.agents[1].status == "idle"

    @pytest.mark.asyncio
    async def test_discover_by_capability(self, mock_supabase, db_client):
        """Test discovering agents filtered by capability."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/discover_agents"
        ).mock(return_value=Response(200, json={
            "agents": [
                {
                    "agent_id": "agent-1",
                    "agent_type": "claude_code",
                    "session_id": "session-1",
                    "capabilities": ["coding", "review"],
                    "status": "active",
                    "current_task": None,
                    "last_heartbeat": "2024-01-01T12:00:00+00:00",
                    "started_at": "2024-01-01T10:00:00+00:00",
                }
            ]
        }))

        service = DiscoveryService(db_client)
        result = await service.discover(capability="review")

        assert len(result.agents) == 1
        assert "review" in result.agents[0].capabilities

    @pytest.mark.asyncio
    async def test_discover_no_matching_agents(self, mock_supabase, db_client):
        """Test discovering when no agents match."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/discover_agents"
        ).mock(return_value=Response(200, json={"agents": []}))

        service = DiscoveryService(db_client)
        result = await service.discover(capability="nonexistent")

        assert len(result.agents) == 0

    @pytest.mark.asyncio
    async def test_heartbeat_success(self, mock_supabase, db_client):
        """Test sending a heartbeat."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/agent_heartbeat"
        ).mock(return_value=Response(200, json={
            "success": True,
            "session_id": "test-session-1",
        }))

        service = DiscoveryService(db_client)
        result = await service.heartbeat()

        assert result.success is True
        assert result.session_id == "test-session-1"

    @pytest.mark.asyncio
    async def test_heartbeat_db_error(self, mock_supabase, db_client):
        """Test heartbeat when database is unavailable."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/agent_heartbeat"
        ).mock(side_effect=Exception("connection refused"))

        service = DiscoveryService(db_client)
        result = await service.heartbeat()

        assert result.success is False
        assert result.error == "database_unavailable"

    @pytest.mark.asyncio
    async def test_heartbeat_session_not_found(self, mock_supabase, db_client):
        """Test heartbeat for nonexistent session."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/agent_heartbeat"
        ).mock(return_value=Response(200, json={
            "success": False,
            "error": "session_not_found",
        }))

        service = DiscoveryService(db_client)
        result = await service.heartbeat(session_id="nonexistent")

        assert result.success is False
        assert result.error == "session_not_found"

    @pytest.mark.asyncio
    async def test_cleanup_dead_agents(self, mock_supabase, db_client):
        """Test cleaning up dead agents."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/cleanup_dead_agents"
        ).mock(return_value=Response(200, json={
            "success": True,
            "agents_cleaned": 2,
            "locks_released": 3,
        }))

        service = DiscoveryService(db_client)
        result = await service.cleanup_dead_agents(stale_threshold_minutes=15)

        assert result.success is True
        assert result.agents_cleaned == 2
        assert result.locks_released == 3

    @pytest.mark.asyncio
    async def test_cleanup_no_dead_agents(self, mock_supabase, db_client):
        """Test cleanup when all agents are active."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/cleanup_dead_agents"
        ).mock(return_value=Response(200, json={
            "success": True,
            "agents_cleaned": 0,
            "locks_released": 0,
        }))

        service = DiscoveryService(db_client)
        result = await service.cleanup_dead_agents()

        assert result.success is True
        assert result.agents_cleaned == 0
        assert result.locks_released == 0


class TestDiscoveryDataClasses:
    """Tests for discovery dataclasses."""

    def test_agent_info_from_dict(self):
        """Test creating AgentInfo from a dictionary."""
        data = {
            "agent_id": "agent-1",
            "agent_type": "claude_code",
            "session_id": "session-1",
            "capabilities": ["coding", "testing"],
            "status": "active",
            "current_task": "Working on locks",
            "last_heartbeat": "2024-01-01T12:00:00Z",
            "started_at": "2024-01-01T10:00:00Z",
        }

        info = AgentInfo.from_dict(data)

        assert info.agent_id == "agent-1"
        assert info.agent_type == "claude_code"
        assert info.capabilities == ["coding", "testing"]
        assert info.status == "active"
        assert info.current_task == "Working on locks"
        assert info.last_heartbeat is not None
        assert info.started_at is not None

    def test_agent_info_from_dict_minimal(self):
        """Test creating AgentInfo with minimal fields."""
        data = {
            "agent_id": "agent-1",
            "agent_type": "claude_code",
            "session_id": "session-1",
        }

        info = AgentInfo.from_dict(data)

        assert info.agent_id == "agent-1"
        assert info.capabilities == []
        assert info.status == "active"
        assert info.current_task is None

    def test_register_result_from_dict(self):
        """Test RegisterResult from response."""
        result = RegisterResult.from_dict({
            "success": True,
            "session_id": "session-123",
        })

        assert result.success is True
        assert result.session_id == "session-123"

    def test_discover_result_from_dict(self):
        """Test DiscoverResult from response."""
        result = DiscoverResult.from_dict({
            "agents": [
                {
                    "agent_id": "a1",
                    "agent_type": "claude_code",
                    "session_id": "s1",
                    "capabilities": ["coding"],
                    "status": "active",
                    "current_task": None,
                    "last_heartbeat": "2024-01-01T12:00:00+00:00",
                    "started_at": None,
                }
            ]
        })

        assert len(result.agents) == 1
        assert result.agents[0].agent_id == "a1"

    def test_heartbeat_result_from_dict(self):
        """Test HeartbeatResult from response."""
        result = HeartbeatResult.from_dict({
            "success": True,
            "session_id": "session-1",
        })

        assert result.success is True
        assert result.session_id == "session-1"

    def test_cleanup_result_from_dict(self):
        """Test CleanupResult from response."""
        result = CleanupResult.from_dict({
            "success": True,
            "agents_cleaned": 5,
            "locks_released": 10,
        })

        assert result.success is True
        assert result.agents_cleaned == 5
        assert result.locks_released == 10

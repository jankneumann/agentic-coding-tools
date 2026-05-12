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


# =============================================================================
# Phase archetype round-trip — wire-autopilot-phase-subagents (D-1)
# =============================================================================


class TestPhaseArchetypeRoundTrip:
    """phase_archetype round-trips through heartbeat → discover via the RPC.

    These tests cover the Python side of the contract; the SQL side is
    asserted in tests/test_phase_archetype_migration.py and the live
    end-to-end wiring is in the integration test suite.
    """

    def test_agent_info_default_phase_archetype_is_none(self) -> None:
        """The new field defaults to None so older serialised dicts still parse."""
        info = AgentInfo(agent_id="a", agent_type="t", session_id="s")
        assert info.phase_archetype is None

    def test_agent_info_from_dict_parses_phase_archetype(self) -> None:
        info = AgentInfo.from_dict({
            "agent_id": "a-1",
            "agent_type": "claude_code",
            "session_id": "s-1",
            "phase_archetype": "implementer",
        })
        assert info.phase_archetype == "implementer"

    def test_agent_info_from_dict_without_phase_archetype_defaults_to_none(self) -> None:
        info = AgentInfo.from_dict({
            "agent_id": "a-1",
            "agent_type": "claude_code",
            "session_id": "s-1",
        })
        assert info.phase_archetype is None

    @pytest.mark.asyncio
    async def test_heartbeat_forwards_phase_archetype_to_rpc(
        self,
        mock_supabase,
        db_client,
    ):
        """``DiscoveryService.heartbeat(phase_archetype=...)`` MUST forward to
        ``agent_heartbeat`` as ``p_phase_archetype``."""
        route = mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/agent_heartbeat"
        ).mock(return_value=Response(200, json={
            "success": True,
            "session_id": "test-session-1",
        }))

        service = DiscoveryService(db_client)
        result = await service.heartbeat(
            session_id="test-session-1",
            phase_archetype="implementer",
        )

        assert result.success is True
        assert route.called
        # Inspect the request body — Supabase RPC posts JSON.
        import json as _json
        request = route.calls.last.request
        body = _json.loads(request.content.decode())
        assert body.get("p_phase_archetype") == "implementer"

    @pytest.mark.asyncio
    async def test_heartbeat_without_phase_archetype_omits_or_passes_none(
        self,
        mock_supabase,
        db_client,
    ):
        """Older callers that don't pass phase_archetype MUST keep working.

        The wire payload either omits ``p_phase_archetype`` or sends ``null`` —
        the RPC's ``DEFAULT NULL`` and ``COALESCE`` semantics handle either.
        """
        route = mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/agent_heartbeat"
        ).mock(return_value=Response(200, json={
            "success": True,
            "session_id": "test-session-1",
        }))

        service = DiscoveryService(db_client)
        result = await service.heartbeat(session_id="test-session-1")

        assert result.success is True
        assert route.called
        import json as _json
        body = _json.loads(route.calls.last.request.content.decode())
        # Either absent or explicit null are valid — they both resolve to
        # the SQL default.
        if "p_phase_archetype" in body:
            assert body["p_phase_archetype"] is None

    @pytest.mark.asyncio
    async def test_discover_parses_phase_archetype_from_rpc_response(
        self,
        mock_supabase,
        db_client,
    ):
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/discover_agents"
        ).mock(return_value=Response(200, json={
            "agents": [
                {
                    "agent_id": "a-1",
                    "agent_type": "claude_code",
                    "session_id": "s-1",
                    "capabilities": ["coding"],
                    "status": "active",
                    "current_task": None,
                    "last_heartbeat": "2024-01-01T12:00:00+00:00",
                    "started_at": "2024-01-01T10:00:00+00:00",
                    "phase_archetype": "reviewer",
                },
                {
                    "agent_id": "a-2",
                    "agent_type": "codex",
                    "session_id": "s-2",
                    "capabilities": [],
                    "status": "idle",
                    "current_task": None,
                    "last_heartbeat": "2024-01-01T11:50:00+00:00",
                    "started_at": "2024-01-01T09:00:00+00:00",
                    # phase_archetype absent — older row that pre-dates the migration
                },
            ],
        }))

        service = DiscoveryService(db_client)
        result = await service.discover()

        assert len(result.agents) == 2
        assert result.agents[0].phase_archetype == "reviewer"
        assert result.agents[1].phase_archetype is None

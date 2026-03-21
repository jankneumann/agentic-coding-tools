"""Tests for delegated identity support across discovery, audit, and profiles."""

from uuid import uuid4

import pytest
from httpx import Response

from src.audit import AuditEntry, AuditService
from src.discovery import AgentInfo, DiscoveryService
from src.profiles import ProfileResult, ProfilesService


class TestDiscoveryDelegation:
    """Tests for delegated identity in DiscoveryService."""

    @pytest.mark.asyncio
    async def test_register_with_delegation(self, mock_supabase, db_client):
        """Verify delegated_from is passed through to the RPC call."""
        route = mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/register_agent_session"
        ).mock(return_value=Response(200, json={
            "success": True,
            "session_id": "test-session-1",
        }))

        service = DiscoveryService(db_client)
        result = await service.register(
            capabilities=["coding"],
            delegated_from="parent-agent-1",
        )

        assert result.success is True
        assert result.session_id == "test-session-1"

        # Verify the RPC payload included delegated_from
        request = route.calls[0].request
        import json
        body = json.loads(request.content)
        assert body["p_delegated_from"] == "parent-agent-1"

    @pytest.mark.asyncio
    async def test_register_without_delegation(self, mock_supabase, db_client):
        """Verify backward compatibility: delegated_from defaults to None."""
        route = mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/register_agent_session"
        ).mock(return_value=Response(200, json={
            "success": True,
            "session_id": "test-session-1",
        }))

        service = DiscoveryService(db_client)
        result = await service.register(capabilities=["coding"])

        assert result.success is True

        # Verify the RPC payload has delegated_from as None
        import json
        body = json.loads(route.calls[0].request.content)
        assert body["p_delegated_from"] is None

    @pytest.mark.asyncio
    async def test_discover_includes_delegation(self, mock_supabase, db_client):
        """Verify delegated_from is included in discovered agent info."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/discover_agents"
        ).mock(return_value=Response(200, json={
            "agents": [
                {
                    "agent_id": "child-agent-1",
                    "agent_type": "claude_code",
                    "session_id": "session-1",
                    "capabilities": ["coding"],
                    "status": "active",
                    "current_task": None,
                    "last_heartbeat": "2024-01-01T12:00:00+00:00",
                    "started_at": "2024-01-01T10:00:00+00:00",
                    "delegated_from": "parent-agent-1",
                },
                {
                    "agent_id": "standalone-agent",
                    "agent_type": "codex",
                    "session_id": "session-2",
                    "capabilities": ["review"],
                    "status": "active",
                    "current_task": None,
                    "last_heartbeat": "2024-01-01T12:00:00+00:00",
                    "started_at": "2024-01-01T10:00:00+00:00",
                },
            ]
        }))

        service = DiscoveryService(db_client)
        result = await service.discover()

        assert len(result.agents) == 2
        assert result.agents[0].delegated_from == "parent-agent-1"
        assert result.agents[1].delegated_from is None


class TestAgentInfoDelegation:
    """Tests for delegated_from in AgentInfo dataclass."""

    def test_agent_info_with_delegated_from(self):
        """Verify AgentInfo.from_dict parses delegated_from."""
        info = AgentInfo.from_dict({
            "agent_id": "child-1",
            "agent_type": "claude_code",
            "session_id": "s-1",
            "delegated_from": "parent-1",
        })
        assert info.delegated_from == "parent-1"

    def test_agent_info_without_delegated_from(self):
        """Verify AgentInfo.from_dict defaults delegated_from to None."""
        info = AgentInfo.from_dict({
            "agent_id": "agent-1",
            "agent_type": "claude_code",
            "session_id": "s-1",
        })
        assert info.delegated_from is None


class TestAuditDelegation:
    """Tests for delegated identity in AuditService."""

    @pytest.mark.asyncio
    async def test_audit_log_with_delegation(
        self, mock_supabase, db_client, monkeypatch
    ):
        """Verify delegated_from is included in the audit insert."""
        monkeypatch.setenv("AUDIT_ASYNC", "false")
        from src.config import reset_config
        reset_config()

        entry_id = str(uuid4())
        route = mock_supabase.post(
            url__startswith="https://test.supabase.co/rest/v1/audit_log"
        ).mock(return_value=Response(
            201, json=[{"id": entry_id, "agent_id": "test-agent-1"}]
        ))

        service = AuditService(db_client)
        result = await service.log_operation(
            operation="acquire_lock",
            parameters={"file_path": "src/main.py"},
            success=True,
            delegated_from="parent-agent-1",
        )

        assert result.success is True

        # Verify the insert payload included delegated_from
        import json
        body = json.loads(route.calls[0].request.content)
        assert body["delegated_from"] == "parent-agent-1"

    @pytest.mark.asyncio
    async def test_audit_log_without_delegation(
        self, mock_supabase, db_client, monkeypatch
    ):
        """Verify backward compatibility: delegated_from defaults to None."""
        monkeypatch.setenv("AUDIT_ASYNC", "false")
        from src.config import reset_config
        reset_config()

        mock_supabase.post(
            url__startswith="https://test.supabase.co/rest/v1/audit_log"
        ).mock(return_value=Response(
            201, json=[{"id": str(uuid4()), "agent_id": "test-agent-1"}]
        ))

        service = AuditService(db_client)
        result = await service.log_operation(
            operation="release_lock",
            success=True,
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_audit_query_filter_delegation(self, mock_supabase, db_client):
        """Verify query filters by delegated_from when provided."""
        route = mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/audit_log"
        ).mock(return_value=Response(200, json=[
            {
                "id": str(uuid4()),
                "agent_id": "child-agent",
                "agent_type": "claude_code",
                "operation": "acquire_lock",
                "parameters": {},
                "result": {},
                "duration_ms": 10,
                "success": True,
                "error_message": None,
                "created_at": "2024-01-01T12:00:00+00:00",
                "delegated_from": "parent-agent-1",
            }
        ]))

        service = AuditService(db_client)
        results = await service.query(delegated_from="parent-agent-1")

        assert len(results) == 1
        assert results[0].delegated_from == "parent-agent-1"

        # Verify the query string included the delegated_from filter
        request_url = str(route.calls[0].request.url)
        assert "delegated_from=eq.parent-agent-1" in request_url

    def test_audit_entry_from_dict_with_delegation(self):
        """Verify AuditEntry.from_dict parses delegated_from."""
        entry = AuditEntry.from_dict({
            "id": str(uuid4()),
            "agent_id": "child-agent",
            "agent_type": "claude_code",
            "operation": "acquire_lock",
            "delegated_from": "parent-agent-1",
        })
        assert entry.delegated_from == "parent-agent-1"

    def test_audit_entry_from_dict_without_delegation(self):
        """Verify AuditEntry.from_dict defaults delegated_from to None."""
        entry = AuditEntry.from_dict({
            "id": str(uuid4()),
            "agent_id": "agent-1",
            "agent_type": "claude_code",
            "operation": "release_lock",
        })
        assert entry.delegated_from is None


class TestProfilesDelegation:
    """Tests for delegated identity in ProfilesService."""

    @pytest.mark.asyncio
    async def test_get_profile_with_delegation(self, mock_supabase, db_client):
        """Verify get_profile returns delegated_from context."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(return_value=Response(200, json={
            "success": True,
            "profile": {
                "id": "profile-1",
                "name": "default-claude",
                "agent_type": "claude_code",
                "trust_level": 3,
                "allowed_operations": [],
                "blocked_operations": [],
                "max_file_modifications": 50,
                "max_execution_time_seconds": 300,
                "max_api_calls_per_hour": 1000,
                "network_policy": {},
                "enabled": True,
            },
            "source": "assignment",
        }))

        service = ProfilesService(db_client)
        result = await service.get_profile(delegated_from="parent-agent-1")

        assert result.success is True
        assert result.delegated_from == "parent-agent-1"
        assert result.profile is not None

    @pytest.mark.asyncio
    async def test_get_profile_without_delegation(self, mock_supabase, db_client):
        """Verify get_profile backward compatible without delegated_from."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(return_value=Response(200, json={
            "success": True,
            "profile": {
                "id": "profile-1",
                "name": "default-claude",
                "agent_type": "claude_code",
                "trust_level": 2,
            },
            "source": "default",
        }))

        service = ProfilesService(db_client)
        result = await service.get_profile()

        assert result.success is True
        assert result.delegated_from is None

    def test_profile_result_from_dict_with_delegation(self):
        """Verify ProfileResult.from_dict parses delegated_from."""
        result = ProfileResult.from_dict({
            "success": True,
            "profile": {
                "id": "p1",
                "name": "test",
                "agent_type": "claude_code",
            },
            "source": "assignment",
            "delegated_from": "parent-1",
        })
        assert result.delegated_from == "parent-1"

    def test_profile_result_from_dict_without_delegation(self):
        """Verify ProfileResult.from_dict defaults delegated_from to None."""
        result = ProfileResult.from_dict({
            "success": True,
            "profile": None,
            "source": None,
        })
        assert result.delegated_from is None

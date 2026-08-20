"""Tests for the agent profiles service."""

from uuid import uuid4

import pytest
from httpx import Response

from src.profiles import AgentProfile, OperationCheck, ProfileResult, ProfilesService


class TestProfilesService:
    """Tests for ProfilesService."""

    @pytest.mark.asyncio
    async def test_get_profile_success(self, mock_supabase, db_client):
        """Test getting an agent profile."""
        profile_id = str(uuid4())
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "profile": {
                        "id": profile_id,
                        "name": "claude-code-cli",
                        "agent_type": "claude_code",
                        "trust_level": 3,
                        "allowed_operations": ["acquire_lock", "release_lock"],
                        "blocked_operations": [],
                        "max_file_modifications": 100,
                        "max_execution_time_seconds": 300,
                        "max_api_calls_per_hour": 1000,
                        "network_policy": {},
                        "enabled": True,
                    },
                    "source": "assignment",
                },
            )
        )

        service = ProfilesService(db_client)
        result = await service.get_profile(
            agent_id="test-agent-1",
            agent_type="claude_code",
        )

        assert result.success is True
        assert result.profile is not None
        assert result.profile.name == "claude-code-cli"
        assert result.profile.trust_level == 3
        assert result.source == "assignment"

    @pytest.mark.asyncio
    async def test_get_profile_default_fallback(self, mock_supabase, db_client):
        """Test falling back to default profile."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "profile": {
                        "id": str(uuid4()),
                        "name": "codex-cloud-worker",
                        "agent_type": "codex",
                        "trust_level": 2,
                        "allowed_operations": ["acquire_lock"],
                        "blocked_operations": [],
                        "max_file_modifications": 50,
                    },
                    "source": "default",
                },
            )
        )

        service = ProfilesService(db_client)
        result = await service.get_profile(agent_type="codex")

        assert result.success is True
        assert result.source == "default"

    @pytest.mark.asyncio
    async def test_get_profile_not_found(self, mock_supabase, db_client):
        """Test when no profile is found."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": False,
                    "reason": "no_profile_found",
                },
            )
        )

        service = ProfilesService(db_client)
        result = await service.get_profile()

        assert result.success is False
        assert result.reason == "no_profile_found"

    @pytest.mark.asyncio
    async def test_check_operation_allowed(self, mock_supabase, db_client):
        """Test that allowed operations pass."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "profile": {
                        "id": str(uuid4()),
                        "name": "test-profile",
                        "agent_type": "claude_code",
                        "trust_level": 3,
                        "allowed_operations": ["acquire_lock", "release_lock"],
                        "blocked_operations": [],
                        "max_file_modifications": 100,
                    },
                    "source": "default",
                },
            )
        )

        service = ProfilesService(db_client)
        check = await service.check_operation("acquire_lock")

        assert check.allowed is True

    @pytest.mark.asyncio
    async def test_check_operation_blocked(self, mock_supabase, db_client):
        """Test that blocked operations are rejected."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "profile": {
                        "id": str(uuid4()),
                        "name": "reviewer",
                        "agent_type": "claude_code",
                        "trust_level": 1,
                        "allowed_operations": ["check_locks", "read_handoff"],
                        "blocked_operations": ["acquire_lock"],
                        "max_file_modifications": 0,
                    },
                    "source": "default",
                },
            )
        )

        service = ProfilesService(db_client)
        check = await service.check_operation("acquire_lock")

        assert check.allowed is False
        assert "blocked" in (check.reason or "")

    @pytest.mark.asyncio
    async def test_check_operation_not_in_allowlist(self, mock_supabase, db_client):
        """Test that operations not in allowlist are rejected."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "profile": {
                        "id": str(uuid4()),
                        "name": "restricted",
                        "agent_type": "claude_code",
                        "trust_level": 1,
                        "allowed_operations": ["check_locks"],
                        "blocked_operations": [],
                        "max_file_modifications": 0,
                    },
                    "source": "default",
                },
            )
        )

        service = ProfilesService(db_client)
        check = await service.check_operation("acquire_lock")

        assert check.allowed is False
        assert "allowlist" in (check.reason or "")

    @pytest.mark.asyncio
    async def test_check_resource_limit_exceeded(self, mock_supabase, db_client):
        """Test that resource limits are enforced."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "profile": {
                        "id": str(uuid4()),
                        "name": "standard",
                        "agent_type": "claude_code",
                        "trust_level": 2,
                        "allowed_operations": ["acquire_lock"],
                        "blocked_operations": [],
                        "max_file_modifications": 5,
                    },
                    "source": "default",
                },
            )
        )

        service = ProfilesService(db_client)
        check = await service.check_operation(
            "acquire_lock",
            context={"files_modified": 10},
        )

        assert check.allowed is False
        assert "resource_limit" in (check.reason or "")


class TestProfileDataClasses:
    """Tests for profile dataclasses."""

    def test_agent_profile_from_dict(self):
        """Test creating AgentProfile from dict."""
        profile = AgentProfile.from_dict({
            "id": "test-id",
            "name": "test-profile",
            "agent_type": "claude_code",
            "trust_level": 3,
            "allowed_operations": ["acquire_lock"],
            "max_file_modifications": 100,
        })

        assert profile.name == "test-profile"
        assert profile.trust_level == 3
        assert "acquire_lock" in profile.allowed_operations

    def test_profile_result_from_dict(self):
        """Test creating ProfileResult from dict."""
        result = ProfileResult.from_dict({
            "success": True,
            "profile": {
                "id": "test",
                "name": "test",
                "agent_type": "test",
                "trust_level": 2,
            },
            "source": "default",
        })

        assert result.success is True
        assert result.profile is not None

    def test_operation_check_from_dict(self):
        """Test creating OperationCheck from dict."""
        check = OperationCheck.from_dict({"allowed": True})
        assert check.allowed is True


class TestProfileCacheInvalidation:
    """The startup registry sync drops cached lookups after it mutates rows."""

    @pytest.mark.asyncio
    async def test_invalidate_cache_forces_refetch(self, mock_supabase, db_client):
        """A cached profile is re-read from the DB after invalidation."""
        route = mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "profile": {
                        "id": str(uuid4()),
                        "name": "grok_local",
                        "agent_type": "grok",
                        "trust_level": 2,
                    },
                    "source": "default",
                },
            )
        )

        service = ProfilesService(db_client)
        first = await service.get_profile(agent_id="grok-local", agent_type="grok")
        assert first.source == "default"

        # A cache hit must be indistinguishable from the lookup it replaces.
        #
        # This previously asserted `cached.source == "cache"`, which pinned a
        # live escalation rather than a feature: `resolve_trust_level` credits a
        # non-registry principal with a profile's trust only when provenance is
        # "assignment", so overwriting provenance with a "cache" marker made
        # every hit inside the TTL fall back to `default_trust_level`. Where the
        # assigned level was *lower* than the default that is an escalation — a
        # principal pinned to a trust-0 (suspended) profile resolved 0 on the
        # cold call and 2 on every cached call, un-suspending itself.
        #
        # The call_count assertion below is what still proves the cache is
        # working; provenance being preserved is not the same as not caching.
        cached = await service.get_profile(agent_id="grok-local", agent_type="grok")
        assert cached.source == "default", (
            "cache hits must report the original provenance, not a cache marker"
        )
        assert route.call_count == 1, "second lookup must be served from cache"

        service.invalidate_cache()
        refetched = await service.get_profile(agent_id="grok-local", agent_type="grok")
        assert refetched.source == "default"
        assert route.call_count == 2

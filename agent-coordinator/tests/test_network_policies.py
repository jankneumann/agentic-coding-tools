"""Tests for the network access policy service."""

from uuid import uuid4

import pytest
from httpx import Response

from src.network_policies import AccessDecision, NetworkPolicyService


class TestNetworkPolicyService:
    """Tests for NetworkPolicyService."""

    @pytest.mark.asyncio
    async def test_check_domain_allowed(self, mock_supabase, db_client):
        """Test that allowed domains pass."""
        policy_id = str(uuid4())
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/is_domain_allowed"
        ).mock(
            return_value=Response(
                200,
                json={
                    "allowed": True,
                    "domain": "github.com",
                    "reason": "global_allow",
                    "policy_id": policy_id,
                },
            )
        )

        service = NetworkPolicyService(db_client)
        result = await service.check_domain("github.com")

        assert result.allowed is True
        assert result.domain == "github.com"
        assert result.policy_id == policy_id

    @pytest.mark.asyncio
    async def test_check_domain_denied(self, mock_supabase, db_client):
        """Test that denied domains are rejected."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/is_domain_allowed"
        ).mock(
            return_value=Response(
                200,
                json={
                    "allowed": False,
                    "domain": "evil.com",
                    "reason": "no_matching_policy",
                },
            )
        )

        service = NetworkPolicyService(db_client)
        result = await service.check_domain("evil.com")

        assert result.allowed is False
        assert result.domain == "evil.com"
        assert result.reason == "no_matching_policy"

    @pytest.mark.asyncio
    async def test_check_domain_with_agent_id(self, mock_supabase, db_client):
        """Test checking domain with explicit agent_id."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/is_domain_allowed"
        ).mock(
            return_value=Response(
                200,
                json={
                    "allowed": True,
                    "domain": "pypi.org",
                    "reason": "profile_allow",
                },
            )
        )

        service = NetworkPolicyService(db_client)
        result = await service.check_domain("pypi.org", agent_id="custom-agent")

        assert result.allowed is True
        assert result.domain == "pypi.org"

    @pytest.mark.asyncio
    async def test_check_domain_error_falls_back_to_default_deny(
        self, mock_supabase, db_client
    ):
        """Test that errors fall back to default deny policy."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/is_domain_allowed"
        ).mock(
            return_value=Response(500, json={"error": "internal error"})
        )

        service = NetworkPolicyService(db_client)
        result = await service.check_domain("example.com")

        assert result.allowed is False
        assert result.domain == "example.com"
        assert "default_policy" in (result.reason or "")

    @pytest.mark.asyncio
    async def test_check_domain_error_falls_back_to_default_allow(
        self, mock_supabase, db_client, monkeypatch
    ):
        """Test fallback to allow when default policy is 'allow'."""
        monkeypatch.setenv("NETWORK_DEFAULT_POLICY", "allow")
        from src.config import reset_config

        reset_config()

        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/is_domain_allowed"
        ).mock(
            return_value=Response(500, json={"error": "internal error"})
        )

        service = NetworkPolicyService(db_client)
        result = await service.check_domain("example.com")

        assert result.allowed is True
        assert "default_policy:allow" in (result.reason or "")


class TestAccessDecisionDataClass:
    """Tests for AccessDecision dataclass."""

    def test_from_dict_full(self):
        """Test creating AccessDecision from full dict."""
        decision = AccessDecision.from_dict(
            {
                "allowed": True,
                "domain": "github.com",
                "reason": "global_allow",
                "policy_id": "abc-123",
            }
        )

        assert decision.allowed is True
        assert decision.domain == "github.com"
        assert decision.reason == "global_allow"
        assert decision.policy_id == "abc-123"

    def test_from_dict_minimal(self):
        """Test creating AccessDecision from minimal dict."""
        decision = AccessDecision.from_dict({"allowed": False, "domain": "test.com"})

        assert decision.allowed is False
        assert decision.domain == "test.com"
        assert decision.reason is None
        assert decision.policy_id is None

    def test_from_dict_defaults(self):
        """Test AccessDecision defaults for missing fields."""
        decision = AccessDecision.from_dict({})

        assert decision.allowed is False
        assert decision.domain == ""

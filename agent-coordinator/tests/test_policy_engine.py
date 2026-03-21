"""Tests for the policy engine module."""


import pytest
from httpx import Response

from src.policy_engine import (
    ADMIN_ACTIONS,
    ALLOWED_DOMAINS,
    READ_ACTIONS,
    WRITE_ACTIONS,
    NativePolicyEngine,
    PolicyDecision,
    get_policy_engine,
    reset_policy_engine,
)


class TestPolicyDecision:
    """Tests for PolicyDecision dataclass."""

    def test_allow(self):
        """Test creating allow decision."""
        d = PolicyDecision.allow("test_reason")
        assert d.allowed is True
        assert d.reason == "test_reason"

    def test_deny(self):
        """Test creating deny decision."""
        d = PolicyDecision.deny("test_reason")
        assert d.allowed is False
        assert d.reason == "test_reason"

    def test_defaults(self):
        """Test PolicyDecision defaults."""
        d = PolicyDecision(allowed=True)
        assert d.reason == ""
        assert d.policy_id is None
        assert d.diagnostics == []


class TestNativePolicyEngine:
    """Tests for NativePolicyEngine."""

    @pytest.mark.asyncio
    async def test_read_action_allowed(self, mock_supabase, db_client):
        """Test that read actions are allowed for all agents."""
        engine = NativePolicyEngine(db_client)

        for action in ["check_locks", "get_work", "recall", "query_audit"]:
            result = await engine.check_operation(
                agent_id="test-agent",
                agent_type="claude_code",
                operation=action,
                context={"trust_level": 1},
            )
            assert result.allowed is True, f"{action} should be allowed"

    @pytest.mark.asyncio
    async def test_write_action_denied_low_trust(
        self, mock_supabase, db_client
    ):
        """Test that write actions are denied for trust < 2."""
        engine = NativePolicyEngine(db_client)

        result = await engine.check_operation(
            agent_id="test-agent",
            agent_type="claude_code",
            operation="acquire_lock",
            context={"trust_level": 1},
        )
        assert result.allowed is False
        assert "trust_level=1 < 2" in result.reason

    @pytest.mark.asyncio
    async def test_write_action_allowed_high_trust(
        self, mock_supabase, db_client
    ):
        """Test that write actions are allowed for trust >= 2."""
        engine = NativePolicyEngine(db_client)

        result = await engine.check_operation(
            agent_id="test-agent",
            agent_type="claude_code",
            operation="acquire_lock",
            context={"trust_level": 2},
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_admin_action_denied_trust_2(
        self, mock_supabase, db_client
    ):
        """Test that admin actions are denied for trust < 3."""
        engine = NativePolicyEngine(db_client)

        result = await engine.check_operation(
            agent_id="test-agent",
            agent_type="claude_code",
            operation="force_push",
            context={"trust_level": 2},
        )
        assert result.allowed is False
        assert "trust_level=2 < 3" in result.reason

    @pytest.mark.asyncio
    async def test_admin_action_allowed_trust_3(
        self, mock_supabase, db_client
    ):
        """Test that admin actions are allowed for trust >= 3."""
        engine = NativePolicyEngine(db_client)

        result = await engine.check_operation(
            agent_id="test-agent",
            agent_type="claude_code",
            operation="force_push",
            context={"trust_level": 3},
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_suspended_agent_denied_all(
        self, mock_supabase, db_client
    ):
        """Test that suspended agents (trust 0) are denied all operations."""
        engine = NativePolicyEngine(db_client)

        for action in ["check_locks", "acquire_lock", "force_push"]:
            result = await engine.check_operation(
                agent_id="test-agent",
                agent_type="claude_code",
                operation=action,
                context={"trust_level": 0},
            )
            assert result.allowed is False, f"{action} should be denied"
            assert "suspended" in result.reason

    @pytest.mark.asyncio
    async def test_network_access_delegation(
        self, mock_supabase, db_client
    ):
        """Test that network access delegates to NetworkPolicyService."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/is_domain_allowed"
        ).mock(
            return_value=Response(
                200,
                json={
                    "allowed": True,
                    "domain": "github.com",
                    "reason": "global_allow",
                },
            )
        )

        engine = NativePolicyEngine(db_client)
        result = await engine.check_network_access(
            agent_id="test-agent",
            domain="github.com",
        )
        assert result.allowed is True


class TestPolicyEngineFactory:
    """Tests for get_policy_engine() factory."""

    def test_default_native_engine(self, monkeypatch):
        """Test default engine is NativePolicyEngine."""
        monkeypatch.setenv("POLICY_ENGINE", "native")
        from src.config import reset_config
        reset_config()
        reset_policy_engine()

        engine = get_policy_engine()
        assert isinstance(engine, NativePolicyEngine)

    def test_cedar_engine_requires_import(self, monkeypatch):
        """Test Cedar engine raises if cedarpy not installed."""
        monkeypatch.setenv("POLICY_ENGINE", "cedar")
        from src.config import reset_config
        reset_config()
        reset_policy_engine()

        # cedarpy may or may not be installed — test both cases
        try:
            engine = get_policy_engine()
            # If cedarpy IS installed, verify it's a CedarPolicyEngine
            from src.policy_engine import CedarPolicyEngine
            assert isinstance(engine, CedarPolicyEngine)
        except ImportError:
            # Expected if cedarpy is not installed
            pass
        finally:
            # Reset back to native
            monkeypatch.setenv("POLICY_ENGINE", "native")
            reset_config()
            reset_policy_engine()


class TestActionCategories:
    """Tests for action category constants."""

    def test_read_actions(self):
        """Test read actions are defined."""
        assert "check_locks" in READ_ACTIONS
        assert "get_work" in READ_ACTIONS
        assert "recall" in READ_ACTIONS
        assert "discover_agents" in READ_ACTIONS

    def test_write_actions(self):
        """Test write actions are defined."""
        assert "acquire_lock" in WRITE_ACTIONS
        assert "complete_work" in WRITE_ACTIONS
        assert "remember" in WRITE_ACTIONS

    def test_admin_actions(self):
        """Test admin actions are defined."""
        assert "force_push" in ADMIN_ACTIONS
        assert "delete_branch" in ADMIN_ACTIONS
        assert "cleanup_agents" in ADMIN_ACTIONS

    def test_allowed_domains(self):
        """Test allowed domains are defined."""
        assert "github.com" in ALLOWED_DOMAINS
        assert "pypi.org" in ALLOWED_DOMAINS
        assert "registry.npmjs.org" in ALLOWED_DOMAINS

    def test_no_overlapping_categories(self):
        """Test action categories don't overlap."""
        assert not READ_ACTIONS & WRITE_ACTIONS
        assert not READ_ACTIONS & ADMIN_ACTIONS
        assert not WRITE_ACTIONS & ADMIN_ACTIONS

    def test_new_read_operations(self):
        """Test new read operations are in READ_ACTIONS."""
        assert "check_approval" in READ_ACTIONS
        assert "list_policy_versions" in READ_ACTIONS

    def test_new_write_operations(self):
        """Test new write operations are in WRITE_ACTIONS."""
        assert "request_approval" in WRITE_ACTIONS
        assert "request_permission" in WRITE_ACTIONS

    def test_rollback_policy_admin(self):
        """Test rollback_policy is an admin action requiring trust >= 3."""
        assert "rollback_policy" in ADMIN_ACTIONS


class TestNativeRiskScoreAndSessionGrants:
    """Tests for risk scoring and session grants in NativePolicyEngine."""

    @pytest.mark.asyncio
    async def test_native_risk_score_high_denies(
        self, mock_supabase, db_client
    ):
        """Verify risk_score > 0.7 denies write ops."""
        engine = NativePolicyEngine(db_client)

        result = await engine.check_operation(
            agent_id="test-agent",
            agent_type="claude_code",
            operation="acquire_lock",
            context={"trust_level": 2, "risk_score": 0.85},
        )
        assert result.allowed is False
        assert "risk_score_exceeded" in result.reason

    @pytest.mark.asyncio
    async def test_native_risk_score_low_allows(
        self, mock_supabase, db_client
    ):
        """Verify risk_score < 0.3 doesn't affect normal authorization."""
        engine = NativePolicyEngine(db_client)

        result = await engine.check_operation(
            agent_id="test-agent",
            agent_type="claude_code",
            operation="acquire_lock",
            context={"trust_level": 2, "risk_score": 0.2},
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_native_risk_score_high_allows_read(
        self, mock_supabase, db_client
    ):
        """Verify high risk_score does not block read operations."""
        engine = NativePolicyEngine(db_client)

        result = await engine.check_operation(
            agent_id="test-agent",
            agent_type="claude_code",
            operation="check_locks",
            context={"trust_level": 1, "risk_score": 0.9},
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_native_session_grants_elevate(
        self, mock_supabase, db_client
    ):
        """Verify session_grants allows a normally-denied operation."""
        engine = NativePolicyEngine(db_client)

        # trust_level=1 would normally deny write operations
        result = await engine.check_operation(
            agent_id="test-agent",
            agent_type="claude_code",
            operation="acquire_lock",
            context={
                "trust_level": 1,
                "session_grants": ["acquire_lock", "release_lock"],
            },
        )
        assert result.allowed is True
        assert "session_grant_permitted" in result.reason

    @pytest.mark.asyncio
    async def test_native_session_grants_suspended(
        self, mock_supabase, db_client
    ):
        """Verify trust 0 still denied even with session grants."""
        engine = NativePolicyEngine(db_client)

        result = await engine.check_operation(
            agent_id="test-agent",
            agent_type="claude_code",
            operation="acquire_lock",
            context={
                "trust_level": 0,
                "session_grants": ["acquire_lock"],
            },
        )
        assert result.allowed is False
        assert "suspended" in result.reason

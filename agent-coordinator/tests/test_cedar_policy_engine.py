"""Tests for the CedarPolicyEngine.

Tests Cedar-based authorization using cedarpy with default policies.
Includes equivalence tests verifying Cedar produces identical decisions
to the NativePolicyEngine for all trust levels and action categories.
"""

import pytest

from src.policy_engine import (
    ADMIN_ACTIONS,
    ALLOWED_DOMAINS,
    READ_ACTIONS,
    WRITE_ACTIONS,
    CedarPolicyEngine,
    NativePolicyEngine,
)


@pytest.fixture
def cedar_engine():
    """Create a CedarPolicyEngine using default file-based policies."""
    return CedarPolicyEngine()


class TestCedarReadActions:
    """Test that Cedar permits read operations for all trust levels."""

    @pytest.mark.asyncio
    async def test_read_actions_allowed_trust_1(self, cedar_engine):
        """Read actions should be allowed for trust_level 1."""
        for action in READ_ACTIONS:
            result = await cedar_engine.check_operation(
                agent_id="agent-1",
                agent_type="claude_code",
                operation=action,
                context={"trust_level": 1},
            )
            assert result.allowed is True, f"{action} should be allowed at trust 1"

    @pytest.mark.asyncio
    async def test_read_actions_allowed_trust_2(self, cedar_engine):
        """Read actions should be allowed for trust_level 2."""
        for action in READ_ACTIONS:
            result = await cedar_engine.check_operation(
                agent_id="agent-1",
                agent_type="claude_code",
                operation=action,
                context={"trust_level": 2},
            )
            assert result.allowed is True, f"{action} should be allowed at trust 2"


class TestCedarWriteActions:
    """Test Cedar write operation enforcement."""

    @pytest.mark.asyncio
    async def test_write_denied_trust_1(self, cedar_engine):
        """Write actions should be denied for trust_level 1."""
        for action in WRITE_ACTIONS:
            result = await cedar_engine.check_operation(
                agent_id="agent-1",
                agent_type="claude_code",
                operation=action,
                context={"trust_level": 1},
            )
            assert result.allowed is False, f"{action} should be denied at trust 1"

    @pytest.mark.asyncio
    async def test_write_allowed_trust_2(self, cedar_engine):
        """Write actions should be allowed for trust_level 2."""
        for action in WRITE_ACTIONS:
            result = await cedar_engine.check_operation(
                agent_id="agent-1",
                agent_type="claude_code",
                operation=action,
                context={"trust_level": 2},
            )
            assert result.allowed is True, f"{action} should be allowed at trust 2"

    @pytest.mark.asyncio
    async def test_write_allowed_trust_3(self, cedar_engine):
        """Write actions should be allowed for trust_level 3."""
        for action in WRITE_ACTIONS:
            result = await cedar_engine.check_operation(
                agent_id="agent-1",
                agent_type="claude_code",
                operation=action,
                context={"trust_level": 3},
            )
            assert result.allowed is True, f"{action} should be allowed at trust 3"


class TestCedarAdminActions:
    """Test Cedar admin operation enforcement."""

    @pytest.mark.asyncio
    async def test_admin_denied_trust_1(self, cedar_engine):
        """Admin actions should be denied for trust_level 1."""
        for action in ADMIN_ACTIONS:
            result = await cedar_engine.check_operation(
                agent_id="agent-1",
                agent_type="claude_code",
                operation=action,
                context={"trust_level": 1},
            )
            assert result.allowed is False, f"{action} should be denied at trust 1"

    @pytest.mark.asyncio
    async def test_admin_denied_trust_2(self, cedar_engine):
        """Admin actions should be denied for trust_level 2."""
        for action in ADMIN_ACTIONS:
            result = await cedar_engine.check_operation(
                agent_id="agent-1",
                agent_type="claude_code",
                operation=action,
                context={"trust_level": 2},
            )
            assert result.allowed is False, f"{action} should be denied at trust 2"

    @pytest.mark.asyncio
    async def test_admin_allowed_trust_3(self, cedar_engine):
        """Admin actions should be allowed for trust_level 3."""
        for action in ADMIN_ACTIONS:
            result = await cedar_engine.check_operation(
                agent_id="agent-1",
                agent_type="claude_code",
                operation=action,
                context={"trust_level": 3},
            )
            assert result.allowed is True, f"{action} should be allowed at trust 3"


class TestCedarSuspendedAgent:
    """Test Cedar forbid policy for suspended agents (trust 0)."""

    @pytest.mark.asyncio
    async def test_suspended_denied_read(self, cedar_engine):
        """Suspended agents should be denied read operations."""
        for action in READ_ACTIONS:
            result = await cedar_engine.check_operation(
                agent_id="agent-suspended",
                agent_type="claude_code",
                operation=action,
                context={"trust_level": 0},
            )
            assert result.allowed is False, f"{action} should be denied at trust 0"

    @pytest.mark.asyncio
    async def test_suspended_denied_write(self, cedar_engine):
        """Suspended agents should be denied write operations."""
        for action in WRITE_ACTIONS:
            result = await cedar_engine.check_operation(
                agent_id="agent-suspended",
                agent_type="claude_code",
                operation=action,
                context={"trust_level": 0},
            )
            assert result.allowed is False, f"{action} should be denied at trust 0"

    @pytest.mark.asyncio
    async def test_suspended_denied_admin(self, cedar_engine):
        """Suspended agents should be denied admin operations."""
        for action in ADMIN_ACTIONS:
            result = await cedar_engine.check_operation(
                agent_id="agent-suspended",
                agent_type="claude_code",
                operation=action,
                context={"trust_level": 0},
            )
            assert result.allowed is False, f"{action} should be denied at trust 0"


class TestCedarNetworkAccess:
    """Test Cedar network access policies."""

    @pytest.mark.asyncio
    async def test_allowed_domains(self, cedar_engine):
        """Known domains should be permitted."""
        for domain in ALLOWED_DOMAINS:
            result = await cedar_engine.check_network_access(
                agent_id="agent-1",
                domain=domain,
                agent_type="claude_code",
                trust_level=1,
            )
            assert result.allowed is True, f"{domain} should be allowed"

    @pytest.mark.asyncio
    async def test_unknown_domain_denied(self, cedar_engine):
        """Unknown domains should be denied (Cedar is default-deny)."""
        result = await cedar_engine.check_network_access(
            agent_id="agent-1",
            domain="evil.example.com",
            agent_type="claude_code",
            trust_level=1,
        )
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_suspended_agent_network_denied(self, cedar_engine):
        """Suspended agents should be denied network access even to allowed domains."""
        result = await cedar_engine.check_network_access(
            agent_id="agent-suspended",
            domain="github.com",
            agent_type="claude_code",
            trust_level=0,
        )
        assert result.allowed is False


class TestCedarPolicyCache:
    """Test Cedar policy caching behavior."""

    @pytest.mark.asyncio
    async def test_policies_cached_after_first_load(self, cedar_engine):
        """Policies should be cached after first evaluation."""
        await cedar_engine.check_operation(
            agent_id="agent-1",
            agent_type="claude_code",
            operation="check_locks",
            context={"trust_level": 1},
        )
        assert cedar_engine._policies_cache is not None
        assert cedar_engine._policies_cache_time > 0

    def test_invalidate_cache(self, cedar_engine):
        """Cache invalidation should clear cached policies."""
        cedar_engine._policies_cache = "cached"
        cedar_engine._policies_cache_time = 100.0

        cedar_engine.invalidate_cache()

        assert cedar_engine._policies_cache is None
        assert cedar_engine._policies_cache_time == 0.0


class TestCedarPolicyValidation:
    """Test Cedar policy validation."""

    def test_validate_valid_policy(self, cedar_engine):
        """Valid Cedar policy should pass validation."""
        result = cedar_engine.validate_policy(
            'permit(principal, action == Action::"check_locks", resource);'
        )
        assert result.valid is True
        assert result.errors == []

    def test_validate_invalid_policy(self, cedar_engine):
        """Invalid Cedar policy syntax should fail validation."""
        result = cedar_engine.validate_policy("this is not valid cedar syntax {{{")
        assert result.valid is False
        assert len(result.errors) > 0


class TestCedarDecisionDiagnostics:
    """Test that Cedar decisions include proper diagnostics."""

    @pytest.mark.asyncio
    async def test_allow_decision_has_reason(self, cedar_engine):
        """Allow decisions should have cedar:allow reason."""
        result = await cedar_engine.check_operation(
            agent_id="agent-1",
            agent_type="claude_code",
            operation="check_locks",
            context={"trust_level": 1},
        )
        assert result.allowed is True
        assert "cedar:allow" in result.reason

    @pytest.mark.asyncio
    async def test_deny_decision_has_reason(self, cedar_engine):
        """Deny decisions should have cedar:deny reason."""
        result = await cedar_engine.check_operation(
            agent_id="agent-1",
            agent_type="claude_code",
            operation="force_push",
            context={"trust_level": 1},
        )
        assert result.allowed is False
        assert "cedar:deny" in result.reason


class TestCedarNativeEquivalence:
    """Verify Cedar and Native engines produce identical decisions.

    This is the key spec requirement: default Cedar policies must produce
    identical authorization decisions to the native engine for all
    preconfigured profiles.
    """

    @pytest.mark.asyncio
    async def test_equivalence_read_actions(
        self, mock_supabase, db_client, cedar_engine
    ):
        """Cedar and Native should agree on read action decisions."""
        native_engine = NativePolicyEngine(db_client)

        for trust_level in [1, 2, 3, 4]:
            for action in READ_ACTIONS:
                cedar_result = await cedar_engine.check_operation(
                    agent_id="agent-eq",
                    agent_type="claude_code",
                    operation=action,
                    context={"trust_level": trust_level},
                )
                native_result = await native_engine.check_operation(
                    agent_id="agent-eq",
                    agent_type="claude_code",
                    operation=action,
                    context={"trust_level": trust_level},
                )
                assert cedar_result.allowed == native_result.allowed, (
                    f"Mismatch for {action} at trust {trust_level}: "
                    f"cedar={cedar_result.allowed}, native={native_result.allowed}"
                )

    @pytest.mark.asyncio
    async def test_equivalence_write_actions(
        self, mock_supabase, db_client, cedar_engine
    ):
        """Cedar and Native should agree on write action decisions."""
        native_engine = NativePolicyEngine(db_client)

        for trust_level in [1, 2, 3, 4]:
            for action in WRITE_ACTIONS:
                cedar_result = await cedar_engine.check_operation(
                    agent_id="agent-eq",
                    agent_type="claude_code",
                    operation=action,
                    context={"trust_level": trust_level},
                )
                native_result = await native_engine.check_operation(
                    agent_id="agent-eq",
                    agent_type="claude_code",
                    operation=action,
                    context={"trust_level": trust_level},
                )
                assert cedar_result.allowed == native_result.allowed, (
                    f"Mismatch for {action} at trust {trust_level}: "
                    f"cedar={cedar_result.allowed}, native={native_result.allowed}"
                )

    @pytest.mark.asyncio
    async def test_equivalence_admin_actions(
        self, mock_supabase, db_client, cedar_engine
    ):
        """Cedar and Native should agree on admin action decisions."""
        native_engine = NativePolicyEngine(db_client)

        for trust_level in [1, 2, 3, 4]:
            for action in ADMIN_ACTIONS:
                cedar_result = await cedar_engine.check_operation(
                    agent_id="agent-eq",
                    agent_type="claude_code",
                    operation=action,
                    context={"trust_level": trust_level},
                )
                native_result = await native_engine.check_operation(
                    agent_id="agent-eq",
                    agent_type="claude_code",
                    operation=action,
                    context={"trust_level": trust_level},
                )
                assert cedar_result.allowed == native_result.allowed, (
                    f"Mismatch for {action} at trust {trust_level}: "
                    f"cedar={cedar_result.allowed}, native={native_result.allowed}"
                )

    @pytest.mark.asyncio
    async def test_equivalence_suspended_agents(
        self, mock_supabase, db_client, cedar_engine
    ):
        """Cedar and Native should both deny all actions for suspended agents."""
        native_engine = NativePolicyEngine(db_client)
        all_actions = READ_ACTIONS | WRITE_ACTIONS | ADMIN_ACTIONS

        for action in all_actions:
            cedar_result = await cedar_engine.check_operation(
                agent_id="agent-suspended",
                agent_type="claude_code",
                operation=action,
                context={"trust_level": 0},
            )
            native_result = await native_engine.check_operation(
                agent_id="agent-suspended",
                agent_type="claude_code",
                operation=action,
                context={"trust_level": 0},
            )
            assert cedar_result.allowed is False, (
                f"Cedar should deny {action} at trust 0"
            )
            assert native_result.allowed is False, (
                f"Native should deny {action} at trust 0"
            )

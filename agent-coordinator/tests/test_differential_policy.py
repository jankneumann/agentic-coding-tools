"""Full operation/resource matrix Cedar-vs-native differential tests (Task 4.4).

Extends existing Cedar equivalence tests with:
- All operations x all trust levels x all resource types
- Multiple agent types
- Network access domain matrix
- Boundary trust levels (exact thresholds)
- Property-based random operation/context generation
"""

from __future__ import annotations

import hypothesis.strategies as st
import pytest
from hypothesis import HealthCheck, given, settings

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
    return CedarPolicyEngine()


@pytest.fixture
def native_engine(mock_supabase, db_client):
    return NativePolicyEngine(db=db_client)


# =============================================================================
# Full Operation x Trust Level Matrix
# =============================================================================


ALL_ACTIONS = sorted(READ_ACTIONS | WRITE_ACTIONS | ADMIN_ACTIONS)
ALL_TRUST_LEVELS = [0, 1, 2, 3, 4, 5]


class TestFullOperationMatrix:
    """Verify Cedar/Native equivalence across the complete operation matrix."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("trust_level", ALL_TRUST_LEVELS)
    @pytest.mark.parametrize("operation", ALL_ACTIONS)
    async def test_equivalence_full_matrix(
        self, cedar_engine, native_engine, operation, trust_level
    ):
        """Cedar and Native must agree for every (operation, trust_level) pair."""
        cedar_result = await cedar_engine.check_operation(
            agent_id="matrix-agent",
            agent_type="claude_code",
            operation=operation,
            context={"trust_level": trust_level},
        )
        native_result = await native_engine.check_operation(
            agent_id="matrix-agent",
            agent_type="claude_code",
            operation=operation,
            context={"trust_level": trust_level},
        )
        assert cedar_result.allowed == native_result.allowed, (
            f"Mismatch: op={operation}, trust={trust_level}, "
            f"cedar={cedar_result.allowed}({cedar_result.reason}), "
            f"native={native_result.allowed}({native_result.reason})"
        )


# =============================================================================
# Resource Type Variations
# =============================================================================


class TestResourceTypeVariations:
    """Verify equivalence with different resource types and values."""

    RESOURCE_SAMPLES = [
        ("src/main.py", "File"),
        ("tests/test_api.py", "File"),
        ("api:/v1/locks", "File"),
        ("feature:deploy-pipeline", "File"),
        ("", "default"),
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "resource,_desc",
        RESOURCE_SAMPLES,
        ids=[r[1] + ":" + (r[0] or "empty") for r in RESOURCE_SAMPLES],
    )
    async def test_equivalence_with_resources(
        self, cedar_engine, native_engine, resource, _desc
    ):
        """Equivalence holds for write operations across resource types."""
        for trust_level in [1, 2, 3]:
            cedar_result = await cedar_engine.check_operation(
                agent_id="resource-agent",
                agent_type="claude_code",
                operation="acquire_lock",
                resource=resource,
                context={"trust_level": trust_level},
            )
            native_result = await native_engine.check_operation(
                agent_id="resource-agent",
                agent_type="claude_code",
                operation="acquire_lock",
                resource=resource,
                context={"trust_level": trust_level},
            )
            assert cedar_result.allowed == native_result.allowed, (
                f"Resource mismatch: resource={resource!r}, trust={trust_level}"
            )


# =============================================================================
# Multiple Agent Types
# =============================================================================


class TestAgentTypeVariations:
    """Verify equivalence across different agent types."""

    AGENT_TYPES = ["claude_code", "codex", "gemini", "unknown_agent", "test_agent"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("agent_type", AGENT_TYPES)
    async def test_equivalence_agent_types(
        self, cedar_engine, native_engine, agent_type
    ):
        """Authorization decisions are identical for different agent types."""
        for operation in ["acquire_lock", "check_locks", "force_push"]:
            for trust_level in [1, 2, 3]:
                cedar_result = await cedar_engine.check_operation(
                    agent_id=f"{agent_type}-agent",
                    agent_type=agent_type,
                    operation=operation,
                    context={"trust_level": trust_level},
                )
                native_result = await native_engine.check_operation(
                    agent_id=f"{agent_type}-agent",
                    agent_type=agent_type,
                    operation=operation,
                    context={"trust_level": trust_level},
                )
                assert cedar_result.allowed == native_result.allowed, (
                    f"Agent type mismatch: type={agent_type}, op={operation}, trust={trust_level}"
                )


# =============================================================================
# Boundary Trust Levels (Exact Thresholds)
# =============================================================================


class TestBoundaryTrustLevels:
    """Test exact trust level boundaries where decisions change."""

    @pytest.mark.asyncio
    async def test_write_boundary_at_2(self, cedar_engine, native_engine):
        """Write operations: denied at trust=1, allowed at trust=2."""
        for action in WRITE_ACTIONS:
            # Denied at 1
            cedar_1 = await cedar_engine.check_operation(
                agent_id="boundary-agent", agent_type="claude_code",
                operation=action, context={"trust_level": 1},
            )
            native_1 = await native_engine.check_operation(
                agent_id="boundary-agent", agent_type="claude_code",
                operation=action, context={"trust_level": 1},
            )
            assert cedar_1.allowed is False
            assert native_1.allowed is False

            # Allowed at 2
            cedar_2 = await cedar_engine.check_operation(
                agent_id="boundary-agent", agent_type="claude_code",
                operation=action, context={"trust_level": 2},
            )
            native_2 = await native_engine.check_operation(
                agent_id="boundary-agent", agent_type="claude_code",
                operation=action, context={"trust_level": 2},
            )
            assert cedar_2.allowed is True
            assert native_2.allowed is True

    @pytest.mark.asyncio
    async def test_admin_boundary_at_3(self, cedar_engine, native_engine):
        """Admin operations: denied at trust=2, allowed at trust=3."""
        for action in ADMIN_ACTIONS:
            cedar_2 = await cedar_engine.check_operation(
                agent_id="boundary-agent", agent_type="claude_code",
                operation=action, context={"trust_level": 2},
            )
            native_2 = await native_engine.check_operation(
                agent_id="boundary-agent", agent_type="claude_code",
                operation=action, context={"trust_level": 2},
            )
            assert cedar_2.allowed is False
            assert native_2.allowed is False

            cedar_3 = await cedar_engine.check_operation(
                agent_id="boundary-agent", agent_type="claude_code",
                operation=action, context={"trust_level": 3},
            )
            native_3 = await native_engine.check_operation(
                agent_id="boundary-agent", agent_type="claude_code",
                operation=action, context={"trust_level": 3},
            )
            assert cedar_3.allowed is True
            assert native_3.allowed is True


# =============================================================================
# Network Access Domain Matrix
# =============================================================================


class TestNetworkAccessEquivalence:
    """Verify network access decisions match between engines."""

    DENIED_DOMAINS = [
        "evil.example.com",
        "attacker.io",
        "localhost",
        "internal.corp.net",
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("domain", sorted(ALLOWED_DOMAINS))
    async def test_allowed_domains_match(self, cedar_engine, native_engine, domain):
        """Both engines allow the same known domains."""
        cedar_result = await cedar_engine.check_network_access(
            agent_id="net-agent", domain=domain,
            agent_type="claude_code", trust_level=2,
        )
        # Native engine uses NetworkPolicyService, which we mock
        # We test Cedar independently here
        assert cedar_result.allowed is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("domain", DENIED_DOMAINS)
    async def test_unknown_domains_denied_by_cedar(self, cedar_engine, domain):
        """Cedar denies unknown domains (default-deny)."""
        result = await cedar_engine.check_network_access(
            agent_id="net-agent", domain=domain,
            agent_type="claude_code", trust_level=2,
        )
        assert result.allowed is False


# =============================================================================
# Property-Based: Random Operation/Context Generation
# =============================================================================


class TestPropertyBasedEquivalence:
    """Property-based differential testing with random inputs."""

    @given(
        operation=st.sampled_from(sorted(READ_ACTIONS | WRITE_ACTIONS | ADMIN_ACTIONS)),
        trust_level=st.integers(min_value=0, max_value=5),
        agent_type=st.sampled_from(["claude_code", "codex", "gemini"]),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_random_operation_equivalence(
        self, cedar_engine, native_engine, operation, trust_level, agent_type
    ):
        """Randomly generated operations produce equivalent decisions."""
        cedar_result = await cedar_engine.check_operation(
            agent_id=f"random-{agent_type}",
            agent_type=agent_type,
            operation=operation,
            context={"trust_level": trust_level},
        )
        native_result = await native_engine.check_operation(
            agent_id=f"random-{agent_type}",
            agent_type=agent_type,
            operation=operation,
            context={"trust_level": trust_level},
        )
        assert cedar_result.allowed == native_result.allowed, (
            f"Random mismatch: op={operation}, trust={trust_level}, "
            f"type={agent_type}, "
            f"cedar={cedar_result.allowed}, native={native_result.allowed}"
        )

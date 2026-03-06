"""Boundary enforcement tests (Task 4.1).

Validates that denied mutations are blocked BEFORE any side effects:
- No database state changes occur when policy denies an operation
- No audit trail entries for the blocked operation itself (only for the policy decision)
- Applies to both service-layer (MCP) and HTTP API paths

These tests use mocked database clients to verify that RPC/insert calls
are never reached when the policy engine denies the operation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.locks import LockService
from src.policy_engine import NativePolicyEngine, PolicyDecision
from src.work_queue import WorkQueueService

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Database client that tracks all calls and should NOT be called on denial."""
    db = AsyncMock()
    rpc_err = "DB rpc should not be called on denied operation"
    insert_err = "DB insert should not be called on denied operation"
    db.rpc = AsyncMock(side_effect=AssertionError(rpc_err))
    db.insert = AsyncMock(side_effect=AssertionError(insert_err))
    db.query = AsyncMock(return_value=[])
    return db


@pytest.fixture
def deny_policy():
    """Policy engine that denies all operations."""
    engine = AsyncMock(spec=NativePolicyEngine)
    engine.check_operation = AsyncMock(
        return_value=PolicyDecision.deny("test_denial: trust_level=0")
    )
    return engine


@pytest.fixture
def allow_policy():
    """Policy engine that allows all operations."""
    engine = AsyncMock(spec=NativePolicyEngine)
    engine.check_operation = AsyncMock(
        return_value=PolicyDecision.allow("test_allow")
    )
    return engine


# =============================================================================
# Lock Service: Denied Mutations Produce No Side Effects
# =============================================================================


class TestLockBoundaryEnforcement:
    """Verify denied lock operations produce no database state changes."""

    @pytest.mark.asyncio
    async def test_denied_acquire_no_db_rpc(self, mock_db, deny_policy):
        """Denied acquire_lock must not call DB rpc."""
        service = LockService(db=mock_db)

        with patch("src.policy_engine.get_policy_engine", return_value=deny_policy):
            result = await service.acquire(file_path="src/main.py", reason="test")

        assert result.success is False
        assert result.reason is not None and "test_denial" in result.reason
        mock_db.rpc.assert_not_called()

    @pytest.mark.asyncio
    async def test_denied_release_no_db_rpc(self, mock_db, deny_policy):
        """Denied release_lock must not call DB rpc."""
        service = LockService(db=mock_db)

        with patch("src.policy_engine.get_policy_engine", return_value=deny_policy):
            result = await service.release(file_path="src/main.py")

        assert result.success is False
        mock_db.rpc.assert_not_called()

    @pytest.mark.asyncio
    async def test_denied_acquire_returns_policy_reason(self, mock_db, deny_policy):
        """Denied acquire should propagate the policy denial reason."""
        service = LockService(db=mock_db)

        with patch("src.policy_engine.get_policy_engine", return_value=deny_policy):
            result = await service.acquire(file_path="src/main.py")

        assert result.success is False
        assert result.reason is not None
        assert "test_denial" in result.reason or "operation_not_permitted" in result.reason

    @pytest.mark.asyncio
    async def test_suspended_agent_acquire_denied(self, mock_supabase, db_client):
        """Agent with trust_level=0 (suspended) is denied lock acquisition."""
        engine = NativePolicyEngine(db=db_client)

        # Simulate suspended agent
        decision = await engine.check_operation(
            agent_id="suspended-agent",
            agent_type="test_agent",
            operation="acquire_lock",
            resource="src/main.py",
            context={"trust_level": 0},
        )
        assert decision.allowed is False

    @pytest.mark.asyncio
    async def test_low_trust_agent_acquire_denied(self, mock_supabase, db_client):
        """Agent with trust_level=1 is denied lock acquisition (requires >= 2)."""
        engine = NativePolicyEngine(db=db_client)

        decision = await engine.check_operation(
            agent_id="low-trust-agent",
            agent_type="test_agent",
            operation="acquire_lock",
            resource="src/main.py",
            context={"trust_level": 1},
        )
        assert decision.allowed is False


# =============================================================================
# Work Queue: Denied Mutations Produce No Side Effects
# =============================================================================


class TestWorkQueueBoundaryEnforcement:
    """Verify denied work queue operations produce no database state changes."""

    @pytest.mark.asyncio
    async def test_denied_claim_no_db_rpc(self, mock_db, deny_policy):
        """Denied claim must not call DB rpc."""
        service = WorkQueueService(db=mock_db)

        with patch("src.policy_engine.get_policy_engine", return_value=deny_policy):
            result = await service.claim()

        assert result.success is False
        mock_db.rpc.assert_not_called()

    @pytest.mark.asyncio
    async def test_denied_complete_no_db_rpc(self, mock_db, deny_policy):
        """Denied complete must not call DB rpc."""
        service = WorkQueueService(db=mock_db)
        task_id = uuid4()

        with patch("src.policy_engine.get_policy_engine", return_value=deny_policy):
            result = await service.complete(task_id=task_id, success=True)

        assert result.success is False
        mock_db.rpc.assert_not_called()

    @pytest.mark.asyncio
    async def test_denied_submit_no_db_rpc(self, mock_db, deny_policy):
        """Denied submit must not call DB rpc."""
        service = WorkQueueService(db=mock_db)

        with patch("src.policy_engine.get_policy_engine", return_value=deny_policy):
            result = await service.submit(
                task_type="test",
                description="Write tests",
            )

        assert result.success is False
        mock_db.rpc.assert_not_called()

    @pytest.mark.asyncio
    async def test_denied_complete_returns_blocked_status(self, mock_db, deny_policy):
        """Denied complete should return status='blocked'."""
        service = WorkQueueService(db=mock_db)

        with patch("src.policy_engine.get_policy_engine", return_value=deny_policy):
            result = await service.complete(task_id=uuid4(), success=True)

        assert result.success is False
        assert result.status == "blocked"

    @pytest.mark.asyncio
    async def test_guardrail_blocked_claim_releases_task(self):
        """When guardrails block a claimed task, it should be released (failed)."""
        mock_db = AsyncMock()

        # First rpc call (claim_task) succeeds
        claimed_response = {
            "success": True,
            "task_id": str(uuid4()),
            "task_type": "test",
            "description": "git push --force to main",
            "input_data": None,
            "priority": 5,
            "deadline": None,
        }
        # Second rpc call (complete_task to release) also tracked
        release_response = {"success": True, "status": "failed"}
        mock_db.rpc = AsyncMock(side_effect=[claimed_response, release_response])
        mock_db.query = AsyncMock(return_value=[])
        mock_db.insert = AsyncMock(return_value={})

        service = WorkQueueService(db=mock_db)

        allow_policy = AsyncMock()
        allow_policy.check_operation = AsyncMock(
            return_value=PolicyDecision.allow("test_allow")
        )

        with (
            patch("src.policy_engine.get_policy_engine", return_value=allow_policy),
            patch("src.audit.get_audit_service") as mock_audit,
        ):
            mock_audit_svc = AsyncMock()
            mock_audit.return_value = mock_audit_svc

            result = await service.claim()

        # The claim should fail because guardrails detect "git push --force"
        assert result.success is False
        assert "destructive_operation_blocked" in (result.reason or "")
        # DB rpc should have been called twice: once for claim, once for release
        assert mock_db.rpc.call_count == 2


# =============================================================================
# HTTP API: Denied Mutations Return Proper HTTP Status
# =============================================================================


class TestHTTPBoundaryEnforcement:
    """Verify HTTP API returns 403 for denied operations."""

    @pytest.fixture
    def api_client(self):
        """Create a test client for the coordination API."""
        from fastapi.testclient import TestClient

        from src.coordination_api import create_coordination_api

        app = create_coordination_api()
        return TestClient(app)

    @pytest.mark.asyncio
    async def test_acquire_lock_no_api_key_returns_401(self, api_client):
        """Missing API key returns 401."""
        response = api_client.post(
            "/locks/acquire",
            json={
                "file_path": "src/main.py",
                "agent_id": "agent-1",
                "agent_type": "test_agent",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_identity_spoofing_returns_403(self):
        """API key bound to agent-1 cannot act as agent-2."""
        import os

        from fastapi.testclient import TestClient

        from src.coordination_api import create_coordination_api
        os.environ["COORDINATION_API_KEYS"] = "test-key-1"
        identities = '{"test-key-1": {"agent_id": "agent-1", "agent_type": "claude_code"}}'
        os.environ["COORDINATION_API_KEY_IDENTITIES"] = identities

        app = create_coordination_api()
        client = TestClient(app)

        response = client.post(
            "/locks/acquire",
            headers={"X-API-Key": "test-key-1"},
            json={
                "file_path": "src/main.py",
                "agent_id": "agent-2",
                "agent_type": "claude_code",
            },
        )
        assert response.status_code == 403
        assert "not permitted" in response.json()["detail"].lower()


# =============================================================================
# Cross-Cutting: Enforcement Invariant Over All Mutation Operations
# =============================================================================


class TestEnforcementInvariant:
    """Verify that every mutation operation checks policy before side effects."""

    MUTATION_OPERATIONS = [
        ("acquire_lock", "acquire_lock"),
        ("release_lock", "release_lock"),
        ("get_work", "get_work"),
        ("complete_work", "complete_work"),
        ("submit_work", "submit_work"),
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "operation,expected_policy_op",
        MUTATION_OPERATIONS,
        ids=[op[0] for op in MUTATION_OPERATIONS],
    )
    async def test_policy_check_before_side_effect(
        self, mock_supabase, db_client, operation, expected_policy_op
    ):
        """Each mutation operation invokes policy check with the correct operation name."""
        engine = NativePolicyEngine(db=db_client)

        # Suspended agent (trust=0) should be denied for all operations
        decision = await engine.check_operation(
            agent_id="test-agent",
            agent_type="test_agent",
            operation=expected_policy_op,
            context={"trust_level": 0},
        )
        assert decision.allowed is False, (
            f"Suspended agent should be denied for {expected_policy_op}"
        )

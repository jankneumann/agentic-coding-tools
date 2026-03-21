"""Tests for transport-layer authorization tools (approval, policy versions, session grants)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest  # noqa: I001

# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeApprovalRequest:
    id: str
    agent_id: str
    operation: str
    resource: str | None
    status: str
    decided_by: str | None
    reason: str | None
    expires_at: datetime
    created_at: datetime


@dataclass
class FakeGrant:
    id: str
    operation: str
    session_id: str
    agent_id: str
    granted_at: datetime
    expires_at: datetime | None = None
    approved_by: str | None = None


def _make_config(
    *,
    approval_enabled: bool = True,
    session_grants_enabled: bool = True,
    agent_id: str = "test-agent",
) -> Any:
    """Build a minimal config-like object."""
    config = MagicMock()
    config.agent.agent_id = agent_id
    config.approval.enabled = approval_enabled
    config.approval.default_timeout_seconds = 3600
    config.session_grants.enabled = session_grants_enabled
    return config


# ---------------------------------------------------------------------------
# MCP tool tests — call directly (FastMCP @mcp.tool keeps functions callable)
# ---------------------------------------------------------------------------


class TestRequestApprovalMCP:
    """Tests for the request_approval MCP tool."""

    @pytest.mark.asyncio
    async def test_request_approval_success(self) -> None:
        now = datetime.now(UTC)
        fake_request = FakeApprovalRequest(
            id="req-1",
            agent_id="test-agent",
            operation="delete_branch",
            resource="main",
            status="pending",
            decided_by=None,
            reason=None,
            expires_at=now + timedelta(hours=1),
            created_at=now,
        )
        mock_service = AsyncMock()
        mock_service.submit_request.return_value = fake_request

        with (
            patch(
                "src.coordination_mcp.get_config",
                return_value=_make_config(approval_enabled=True),
            ),
            patch(
                "src.coordination_mcp.get_approval_service",
                return_value=mock_service,
            ),
        ):
            from src.coordination_mcp import request_approval

            result = await request_approval.fn(
                operation="delete_branch", resource="main"
            )

        assert result["success"] is True
        assert result["request_id"] == "req-1"
        assert result["status"] == "pending"
        assert "expires_at" in result
        mock_service.submit_request.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_request_approval_disabled(self) -> None:
        with patch(
            "src.coordination_mcp.get_config",
            return_value=_make_config(approval_enabled=False),
        ):
            from src.coordination_mcp import request_approval

            result = await request_approval.fn(operation="delete_branch")

        assert result["success"] is False
        assert "not enabled" in result["error"]


class TestCheckApprovalMCP:
    """Tests for the check_approval MCP tool."""

    @pytest.mark.asyncio
    async def test_check_approval_found(self) -> None:
        now = datetime.now(UTC)
        fake_request = FakeApprovalRequest(
            id="req-2",
            agent_id="test-agent",
            operation="force_push",
            resource=None,
            status="approved",
            decided_by="human-admin",
            reason="Looks safe",
            expires_at=now + timedelta(hours=1),
            created_at=now,
        )
        mock_service = AsyncMock()
        mock_service.check_request.return_value = fake_request

        with patch(
            "src.coordination_mcp.get_approval_service",
            return_value=mock_service,
        ):
            from src.coordination_mcp import check_approval

            result = await check_approval.fn(request_id="req-2")

        assert result["success"] is True
        assert result["request_id"] == "req-2"
        assert result["status"] == "approved"
        assert result["decided_by"] == "human-admin"
        assert result["reason"] == "Looks safe"

    @pytest.mark.asyncio
    async def test_check_approval_not_found(self) -> None:
        mock_service = AsyncMock()
        mock_service.check_request.return_value = None

        with patch(
            "src.coordination_mcp.get_approval_service",
            return_value=mock_service,
        ):
            from src.coordination_mcp import check_approval

            result = await check_approval.fn(request_id="nonexistent")

        assert result["success"] is False
        assert "not found" in result["error"].lower()


class TestListPolicyVersionsMCP:
    """Tests for the list_policy_versions MCP tool."""

    @pytest.mark.asyncio
    async def test_list_policy_versions(self) -> None:
        fake_versions = [
            {"version": 2, "created_at": "2026-03-20T10:00:00Z"},
            {"version": 1, "created_at": "2026-03-19T10:00:00Z"},
        ]
        mock_engine = AsyncMock()
        mock_engine.list_policy_versions.return_value = fake_versions

        with patch(
            "src.policy_engine.get_policy_engine",
            return_value=mock_engine,
        ):
            from src.coordination_mcp import list_policy_versions

            result = await list_policy_versions.fn(policy_name="default", limit=10)

        assert result["versions"] == fake_versions
        mock_engine.list_policy_versions.assert_awaited_once_with("default", 10)


class TestRequestPermissionMCP:
    """Tests for the request_permission MCP tool."""

    @pytest.mark.asyncio
    async def test_request_permission_success(self) -> None:
        now = datetime.now(UTC)
        fake_grant = FakeGrant(
            id="grant-1",
            operation="write_config",
            session_id="test-agent",
            agent_id="test-agent",
            granted_at=now,
        )
        mock_service = AsyncMock()
        mock_service.request_grant.return_value = fake_grant

        with (
            patch(
                "src.coordination_mcp.get_config",
                return_value=_make_config(session_grants_enabled=True),
            ),
            patch(
                "src.coordination_mcp.get_session_grant_service",
                return_value=mock_service,
            ),
        ):
            from src.coordination_mcp import request_permission

            result = await request_permission.fn(
                operation="write_config", justification="Need to update DB settings"
            )

        assert result["success"] is True
        assert result["granted"] is True
        assert result["grant_id"] == "grant-1"
        assert result["operation"] == "write_config"

    @pytest.mark.asyncio
    async def test_request_permission_disabled(self) -> None:
        with patch(
            "src.coordination_mcp.get_config",
            return_value=_make_config(session_grants_enabled=False),
        ):
            from src.coordination_mcp import request_permission

            result = await request_permission.fn(operation="write_config")

        assert result["success"] is False
        assert "not enabled" in result["error"]

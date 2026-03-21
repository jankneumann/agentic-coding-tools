"""Tests for the approval queue service."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from src.approval import (
    ApprovalRequest,
    ApprovalService,
    get_approval_service,
    reset_approval_service,
)


class FakeDB:
    """Minimal fake database client for unit tests."""

    def __init__(self) -> None:
        self.insert_calls: list[tuple[str, dict[str, Any]]] = []
        self.update_calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        self.query_calls: list[tuple[str, str | None]] = []
        self._query_results: list[dict[str, Any]] = []

    def set_query_results(self, rows: list[dict[str, Any]]) -> None:
        self._query_results = rows

    async def query(
        self,
        table: str,
        query_params: str | None = None,
        select: str = "*",
    ) -> list[dict[str, Any]]:
        self.query_calls.append((table, query_params))
        return list(self._query_results)

    async def insert(
        self,
        table: str,
        data: dict[str, Any],
        return_data: bool = True,
    ) -> dict[str, Any]:
        self.insert_calls.append((table, data))
        return data

    async def update(
        self,
        table: str,
        match: dict[str, Any],
        data: dict[str, Any],
        return_data: bool = True,
    ) -> list[dict[str, Any]]:
        self.update_calls.append((table, match, data))
        return [data]

    async def delete(self, table: str, match: dict[str, Any]) -> None:
        pass

    async def rpc(self, function_name: str, params: dict[str, Any]) -> Any:
        return None

    async def close(self) -> None:
        pass


def _make_row(
    *,
    request_id: str = "req-1",
    agent_id: str = "agent-1",
    agent_type: str | None = "claude_code",
    operation: str = "deploy",
    resource: str | None = "/prod",
    context: str = "{}",
    status: str = "pending",
    decided_by: str | None = None,
    decided_at: str | None = None,
    reason: str | None = None,
    expires_at: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "id": request_id,
        "agent_id": agent_id,
        "agent_type": agent_type,
        "operation": operation,
        "resource": resource,
        "context": context,
        "status": status,
        "decided_by": decided_by,
        "decided_at": decided_at,
        "reason": reason,
        "expires_at": expires_at or (now + timedelta(hours=1)).isoformat(),
        "created_at": created_at or now.isoformat(),
    }


class TestApprovalService:
    """Tests for ApprovalService."""

    @pytest.mark.asyncio
    async def test_submit_request(self) -> None:
        """submit_request inserts into approval_queue and returns ApprovalRequest."""
        db = FakeDB()
        service = ApprovalService(db=db)

        result = await service.submit_request(
            agent_id="agent-1",
            operation="deploy",
            agent_type="claude_code",
            resource="/prod",
            context={"env": "production"},
            timeout_seconds=1800,
        )

        assert isinstance(result, ApprovalRequest)
        assert result.agent_id == "agent-1"
        assert result.operation == "deploy"
        assert result.agent_type == "claude_code"
        assert result.resource == "/prod"
        assert result.context == {"env": "production"}
        assert result.status == "pending"
        assert result.decided_by is None
        assert result.decided_at is None

        # Verify DB insert
        assert len(db.insert_calls) == 1
        table, data = db.insert_calls[0]
        assert table == "approval_queue"
        assert data["agent_id"] == "agent-1"
        assert data["operation"] == "deploy"
        assert data["status"] == "pending"
        assert json.loads(data["context"]) == {"env": "production"}

    @pytest.mark.asyncio
    async def test_submit_request_defaults(self) -> None:
        """submit_request uses sensible defaults for optional params."""
        db = FakeDB()
        service = ApprovalService(db=db)

        result = await service.submit_request(
            agent_id="agent-1",
            operation="deploy",
        )

        assert result.agent_type is None
        assert result.resource is None
        assert result.context == {}

        _, data = db.insert_calls[0]
        assert json.loads(data["context"]) == {}

    @pytest.mark.asyncio
    async def test_check_request_found(self) -> None:
        """check_request returns ApprovalRequest when found."""
        db = FakeDB()
        db.set_query_results([_make_row(request_id="req-42", operation="scale")])
        service = ApprovalService(db=db)

        result = await service.check_request("req-42")

        assert result is not None
        assert result.id == "req-42"
        assert result.operation == "scale"
        assert result.status == "pending"

        # Verify correct query
        assert len(db.query_calls) == 1
        table, filters = db.query_calls[0]
        assert table == "approval_queue"
        assert "id=eq.req-42" in (filters or "")

    @pytest.mark.asyncio
    async def test_check_request_not_found(self) -> None:
        """check_request returns None when request doesn't exist."""
        db = FakeDB()
        db.set_query_results([])
        service = ApprovalService(db=db)

        result = await service.check_request("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_decide_approve(self) -> None:
        """decide_request with 'approved' updates status correctly."""
        db = FakeDB()
        db.set_query_results([_make_row(request_id="req-1")])
        service = ApprovalService(db=db)

        result = await service.decide_request(
            "req-1",
            "approved",
            decided_by="human-admin",
            reason="Looks good",
        )

        assert result is not None
        assert result.status == "approved"
        assert result.decided_by == "human-admin"
        assert result.reason == "Looks good"
        assert result.decided_at is not None

        # Verify update call
        assert len(db.update_calls) == 1
        table, match, data = db.update_calls[0]
        assert table == "approval_queue"
        assert match == {"id": "req-1"}
        assert data["status"] == "approved"
        assert data["decided_by"] == "human-admin"

    @pytest.mark.asyncio
    async def test_decide_deny(self) -> None:
        """decide_request with 'denied' updates status correctly."""
        db = FakeDB()
        db.set_query_results([_make_row(request_id="req-2")])
        service = ApprovalService(db=db)

        result = await service.decide_request(
            "req-2",
            "denied",
            decided_by="reviewer",
            reason="Too risky",
        )

        assert result is not None
        assert result.status == "denied"
        assert result.decided_by == "reviewer"
        assert result.reason == "Too risky"

        _, _, data = db.update_calls[0]
        assert data["status"] == "denied"

    @pytest.mark.asyncio
    async def test_decide_invalid(self) -> None:
        """decide_request raises ValueError for invalid decisions."""
        db = FakeDB()
        service = ApprovalService(db=db)

        with pytest.raises(ValueError, match="Invalid decision"):
            await service.decide_request("req-1", "maybe")

    @pytest.mark.asyncio
    async def test_decide_not_pending(self) -> None:
        """decide_request returns None when no pending request matches."""
        db = FakeDB()
        db.set_query_results([])  # No matching pending request
        service = ApprovalService(db=db)

        result = await service.decide_request("req-1", "approved")
        assert result is None
        assert len(db.update_calls) == 0

    @pytest.mark.asyncio
    async def test_expire_stale(self) -> None:
        """expire_stale_requests marks expired requests and returns count."""
        past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        db = FakeDB()
        db.set_query_results([
            _make_row(request_id="req-old-1", expires_at=past),
            _make_row(request_id="req-old-2", expires_at=past),
        ])
        service = ApprovalService(db=db)

        count = await service.expire_stale_requests()

        assert count == 2
        assert len(db.update_calls) == 2
        for _, match, data in db.update_calls:
            assert data["status"] == "expired"

    @pytest.mark.asyncio
    async def test_expire_stale_none(self) -> None:
        """expire_stale_requests returns 0 when nothing is stale."""
        db = FakeDB()
        db.set_query_results([])
        service = ApprovalService(db=db)

        count = await service.expire_stale_requests()
        assert count == 0

    @pytest.mark.asyncio
    async def test_list_pending(self) -> None:
        """list_pending returns pending requests."""
        db = FakeDB()
        db.set_query_results([
            _make_row(request_id="req-a", operation="deploy"),
            _make_row(request_id="req-b", operation="scale"),
        ])
        service = ApprovalService(db=db)

        results = await service.list_pending()

        assert len(results) == 2
        assert results[0].id == "req-a"
        assert results[1].id == "req-b"

        # Verify filter includes pending status
        _, filters = db.query_calls[0]
        assert "status=eq.pending" in (filters or "")

    @pytest.mark.asyncio
    async def test_list_pending_filtered_by_agent(self) -> None:
        """list_pending filters by agent_id when provided."""
        db = FakeDB()
        db.set_query_results([_make_row(agent_id="agent-x")])
        service = ApprovalService(db=db)

        results = await service.list_pending(agent_id="agent-x")

        assert len(results) == 1
        _, filters = db.query_calls[0]
        assert "agent_id=eq.agent-x" in (filters or "")

    @pytest.mark.asyncio
    async def test_list_pending_respects_limit(self) -> None:
        """list_pending truncates results to limit."""
        db = FakeDB()
        db.set_query_results([_make_row(request_id=f"req-{i}") for i in range(10)])
        service = ApprovalService(db=db)

        results = await service.list_pending(limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_row_to_request_parses_context_string(self) -> None:
        """_row_to_request parses JSON string context."""
        db = FakeDB()
        service = ApprovalService(db=db)

        row = _make_row(context='{"key": "value"}')
        request = service._row_to_request(row)

        assert request.context == {"key": "value"}

    @pytest.mark.asyncio
    async def test_row_to_request_handles_dict_context(self) -> None:
        """_row_to_request handles already-parsed dict context."""
        db = FakeDB()
        service = ApprovalService(db=db)

        row = _make_row()
        row["context"] = {"already": "parsed"}
        request = service._row_to_request(row)

        assert request.context == {"already": "parsed"}


class TestApprovalSingleton:
    """Tests for module-level singleton."""

    def test_get_approval_service_returns_same_instance(self, monkeypatch) -> None:
        """get_approval_service returns the same instance on repeated calls."""
        # Ensure clean state
        reset_approval_service()

        # Prevent actual DB creation by patching get_db
        monkeypatch.setattr("src.approval.get_db", lambda: FakeDB())

        svc1 = get_approval_service()
        svc2 = get_approval_service()
        assert svc1 is svc2

        # Clean up
        reset_approval_service()

    def test_reset_approval_service(self, monkeypatch) -> None:
        """reset_approval_service clears the singleton."""
        reset_approval_service()
        monkeypatch.setattr("src.approval.get_db", lambda: FakeDB())

        svc1 = get_approval_service()
        reset_approval_service()
        svc2 = get_approval_service()
        assert svc1 is not svc2

        reset_approval_service()

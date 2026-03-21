"""Tests for session-scoped permission grants."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from src.session_grants import (
    PermissionGrant,
    SessionGrantService,
    _parse_dt,
    get_session_grant_service,
    reset_session_grant_service,
)


class FakeDB:
    """Minimal fake DatabaseClient for unit tests."""

    def __init__(
        self,
        query_result: list[dict[str, Any]] | None = None,
        insert_result: dict[str, Any] | None = None,
    ) -> None:
        self.query_result = query_result or []
        self.insert_result = insert_result or {}
        self.insert_calls: list[tuple[str, dict[str, Any]]] = []
        self.query_calls: list[tuple[str, str | None]] = []
        self.delete_calls: list[tuple[str, dict[str, Any]]] = []

    async def rpc(self, function_name: str, params: dict[str, Any]) -> Any:
        return {}

    async def query(
        self,
        table: str,
        query_params: str | None = None,
        select: str = "*",
    ) -> list[dict[str, Any]]:
        self.query_calls.append((table, query_params))
        return self.query_result

    async def insert(
        self,
        table: str,
        data: dict[str, Any],
        return_data: bool = True,
    ) -> dict[str, Any]:
        self.insert_calls.append((table, data))
        return self.insert_result

    async def update(
        self,
        table: str,
        match: dict[str, Any],
        data: dict[str, Any],
        return_data: bool = True,
    ) -> list[dict[str, Any]]:
        return []

    async def delete(self, table: str, match: dict[str, Any]) -> None:
        self.delete_calls.append((table, match))

    async def close(self) -> None:
        pass


def _make_row(
    *,
    grant_id: str = "grant-1",
    session_id: str = "sess-1",
    agent_id: str = "agent-1",
    operation: str = "file:write",
    justification: str | None = "needed for feature X",
    granted_at: str = "2026-03-20T10:00:00+00:00",
    expires_at: str | None = None,
    approved_by: str | None = None,
) -> dict[str, Any]:
    return {
        "id": grant_id,
        "session_id": session_id,
        "agent_id": agent_id,
        "operation": operation,
        "justification": justification,
        "granted_at": granted_at,
        "expires_at": expires_at,
        "approved_by": approved_by,
    }


class TestSessionGrantService:
    """Tests for SessionGrantService."""

    @pytest.mark.asyncio
    async def test_request_grant(self) -> None:
        """Verify insert is called with correct data."""
        fake_db = FakeDB()
        service = SessionGrantService(db=fake_db)

        grant = await service.request_grant(
            session_id="sess-1",
            agent_id="agent-1",
            operation="file:write",
            justification="need to edit config",
        )

        assert isinstance(grant, PermissionGrant)
        assert grant.session_id == "sess-1"
        assert grant.agent_id == "agent-1"
        assert grant.operation == "file:write"
        assert grant.justification == "need to edit config"
        assert grant.expires_at is None
        assert grant.approved_by is None

        # Verify DB insert
        assert len(fake_db.insert_calls) == 1
        table, data = fake_db.insert_calls[0]
        assert table == "session_permission_grants"
        assert data["session_id"] == "sess-1"
        assert data["agent_id"] == "agent-1"
        assert data["operation"] == "file:write"
        assert data["justification"] == "need to edit config"
        assert "id" in data
        assert "granted_at" in data

    @pytest.mark.asyncio
    async def test_get_active_grants(self) -> None:
        """Verify query and row parsing."""
        rows = [
            _make_row(grant_id="g1", operation="file:read"),
            _make_row(grant_id="g2", operation="file:write"),
        ]
        fake_db = FakeDB(query_result=rows)
        service = SessionGrantService(db=fake_db)

        grants = await service.get_active_grants("sess-1")

        assert len(grants) == 2
        assert grants[0].id == "g1"
        assert grants[0].operation == "file:read"
        assert grants[1].id == "g2"
        assert grants[1].operation == "file:write"
        assert isinstance(grants[0].granted_at, datetime)

        # Verify correct query params
        assert len(fake_db.query_calls) == 1
        table, params = fake_db.query_calls[0]
        assert table == "session_permission_grants"
        assert "session_id=eq.sess-1" in (params or "")

    @pytest.mark.asyncio
    async def test_has_grant_true(self) -> None:
        """Verify True when grant exists."""
        fake_db = FakeDB(query_result=[_make_row()])
        service = SessionGrantService(db=fake_db)

        result = await service.has_grant("sess-1", "file:write")

        assert result is True
        table, params = fake_db.query_calls[0]
        assert "session_id=eq.sess-1" in (params or "")
        assert "operation=eq.file:write" in (params or "")

    @pytest.mark.asyncio
    async def test_has_grant_false(self) -> None:
        """Verify False when no grant."""
        fake_db = FakeDB(query_result=[])
        service = SessionGrantService(db=fake_db)

        result = await service.has_grant("sess-1", "file:write")

        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_grants(self) -> None:
        """Verify delete called and count returned."""
        rows = [_make_row(grant_id="g1"), _make_row(grant_id="g2")]
        fake_db = FakeDB(query_result=rows)
        service = SessionGrantService(db=fake_db)

        count = await service.revoke_grants("sess-1")

        assert count == 2
        assert len(fake_db.delete_calls) == 1
        table, match = fake_db.delete_calls[0]
        assert table == "session_permission_grants"
        assert match == {"session_id": "sess-1"}

    @pytest.mark.asyncio
    async def test_revoke_grants_empty(self) -> None:
        """Verify 0 returned when no grants to revoke."""
        fake_db = FakeDB(query_result=[])
        service = SessionGrantService(db=fake_db)

        count = await service.revoke_grants("sess-1")

        assert count == 0
        assert len(fake_db.delete_calls) == 0


class TestSingleton:
    """Tests for the singleton accessor."""

    def test_get_session_grant_service(self) -> None:
        """Verify singleton pattern."""
        reset_session_grant_service()
        try:
            svc1 = get_session_grant_service()
            svc2 = get_session_grant_service()
            assert svc1 is svc2
        finally:
            reset_session_grant_service()

    def test_reset_session_grant_service(self) -> None:
        """Verify reset creates new instance."""
        reset_session_grant_service()
        try:
            svc1 = get_session_grant_service()
            reset_session_grant_service()
            svc2 = get_session_grant_service()
            assert svc1 is not svc2
        finally:
            reset_session_grant_service()


class TestParseDt:
    """Tests for _parse_dt helper."""

    def test_none(self) -> None:
        assert _parse_dt(None) is None

    def test_datetime_passthrough(self) -> None:
        dt = datetime(2026, 3, 20, 10, 0, 0, tzinfo=UTC)
        assert _parse_dt(dt) is dt

    def test_iso_string(self) -> None:
        result = _parse_dt("2026-03-20T10:00:00+00:00")
        assert isinstance(result, datetime)
        assert result.year == 2026
        assert result.month == 3
        assert result.day == 20

    def test_z_suffix(self) -> None:
        result = _parse_dt("2026-03-20T10:00:00Z")
        assert isinstance(result, datetime)
        assert result.tzinfo is not None

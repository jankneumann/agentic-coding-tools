"""Tests for the audit trail service."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import Response

from src.audit import AuditEntry, AuditResult, AuditService


class TestAuditService:
    """Tests for AuditService."""

    @pytest.mark.asyncio
    async def test_log_operation_sync(self, mock_supabase, db_client, monkeypatch):
        """Test synchronous audit logging."""
        monkeypatch.setenv("AUDIT_ASYNC", "false")

        from src.config import reset_config

        reset_config()

        entry_id = str(uuid4())
        mock_supabase.post(
            url__startswith="https://test.supabase.co/rest/v1/audit_log"
        ).mock(
            return_value=Response(
                201, json=[{"id": entry_id, "agent_id": "test-agent-1"}]
            )
        )

        service = AuditService(db_client)
        result = await service.log_operation(
            operation="acquire_lock",
            parameters={"file_path": "src/main.py"},
            success=True,
            duration_ms=42,
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_log_operation_async(self, mock_supabase, db_client):
        """Test async (fire-and-forget) audit logging."""
        mock_supabase.post(
            url__startswith="https://test.supabase.co/rest/v1/audit_log"
        ).mock(return_value=Response(201, json=[{"id": str(uuid4())}]))

        service = AuditService(db_client)
        result = await service.log_operation(
            operation="release_lock",
            success=True,
        )

        # Async logging returns success immediately
        assert result.success is True

    @pytest.mark.asyncio
    async def test_query_all(self, mock_supabase, db_client):
        """Test querying audit entries."""
        now = datetime.now(UTC)
        entries = [
            {
                "id": str(uuid4()),
                "agent_id": "agent-1",
                "agent_type": "claude_code",
                "operation": "acquire_lock",
                "parameters": {},
                "result": {},
                "duration_ms": 50,
                "success": True,
                "error_message": None,
                "created_at": now.isoformat(),
            },
            {
                "id": str(uuid4()),
                "agent_id": "agent-1",
                "agent_type": "claude_code",
                "operation": "release_lock",
                "parameters": {},
                "result": {},
                "duration_ms": 12,
                "success": True,
                "error_message": None,
                "created_at": (now - timedelta(minutes=1)).isoformat(),
            },
        ]

        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/audit_log"
        ).mock(return_value=Response(200, json=entries))

        service = AuditService(db_client)
        results = await service.query(agent_id="agent-1", limit=10)

        assert len(results) == 2
        assert results[0].operation == "acquire_lock"
        assert results[1].operation == "release_lock"

    @pytest.mark.asyncio
    async def test_query_by_operation(self, mock_supabase, db_client):
        """Test querying audit entries filtered by operation."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/audit_log"
        ).mock(return_value=Response(200, json=[]))

        service = AuditService(db_client)
        results = await service.query(operation="acquire_lock")

        assert len(results) == 0


class TestAuditDataClasses:
    """Tests for audit dataclasses."""

    def test_audit_entry_from_dict(self):
        """Test creating AuditEntry from dict."""
        data = {
            "id": str(uuid4()),
            "agent_id": "test-agent",
            "agent_type": "claude_code",
            "operation": "acquire_lock",
            "parameters": {"file": "main.py"},
            "result": {"success": True},
            "duration_ms": 42,
            "success": True,
            "error_message": None,
            "created_at": "2024-01-01T12:00:00+00:00",
        }

        entry = AuditEntry.from_dict(data)
        assert entry.agent_id == "test-agent"
        assert entry.operation == "acquire_lock"
        assert entry.duration_ms == 42
        assert entry.success is True

    def test_audit_result_from_dict(self):
        """Test creating AuditResult from dict."""
        result = AuditResult.from_dict({"success": True, "id": "test-id"})
        assert result.success is True
        assert result.entry_id == "test-id"

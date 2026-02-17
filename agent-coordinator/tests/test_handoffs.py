"""Tests for the handoff document service."""

from uuid import uuid4

import pytest
from httpx import Response

from src.policy_engine import PolicyDecision
from src.handoffs import HandoffDocument, HandoffService, ReadHandoffResult, WriteHandoffResult


class TestHandoffService:
    """Tests for HandoffService."""

    @pytest.mark.asyncio
    async def test_write_handoff_success(self, mock_supabase, db_client):
        """Test writing a handoff document."""
        handoff_id = str(uuid4())
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/write_handoff"
        ).mock(return_value=Response(200, json={
            "success": True,
            "handoff_id": handoff_id,
        }))

        service = HandoffService(db_client)
        result = await service.write(
            summary="Implemented file locking",
            completed_work=["Lock acquisition", "Lock release"],
            next_steps=["Write tests"],
        )

        assert result.success is True
        assert result.handoff_id is not None
        assert str(result.handoff_id) == handoff_id

    @pytest.mark.asyncio
    async def test_write_handoff_db_error(self, mock_supabase, db_client):
        """Test writing a handoff when database is unavailable."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/write_handoff"
        ).mock(side_effect=Exception("connection refused"))

        service = HandoffService(db_client)
        result = await service.write(summary="Test summary")

        assert result.success is False
        assert result.error == "database_unavailable"

    @pytest.mark.asyncio
    async def test_write_handoff_missing_summary(self, mock_supabase, db_client):
        """Test writing a handoff without summary fails."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/write_handoff"
        ).mock(return_value=Response(200, json={
            "success": False,
            "error": "summary_required",
        }))

        service = HandoffService(db_client)
        result = await service.write(summary="")

        assert result.success is False
        assert result.error == "summary_required"

    @pytest.mark.asyncio
    async def test_read_handoff_success(self, mock_supabase, db_client):
        """Test reading handoff documents."""
        handoff_id = str(uuid4())
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/read_handoff"
        ).mock(return_value=Response(200, json={
            "handoffs": [
                {
                    "id": handoff_id,
                    "agent_name": "test-agent-1",
                    "session_id": "session-1",
                    "summary": "Implemented file locking",
                    "completed_work": ["Lock acquisition"],
                    "in_progress": ["Integration tests"],
                    "decisions": ["Used PostgreSQL locks"],
                    "next_steps": ["Write tests"],
                    "relevant_files": ["src/locks.py"],
                    "created_at": "2024-01-01T12:00:00+00:00",
                }
            ]
        }))

        service = HandoffService(db_client)
        result = await service.read(agent_name="test-agent-1")

        assert len(result.handoffs) == 1
        handoff = result.handoffs[0]
        assert handoff.agent_name == "test-agent-1"
        assert handoff.summary == "Implemented file locking"
        assert handoff.completed_work == ["Lock acquisition"]
        assert handoff.in_progress == ["Integration tests"]
        assert handoff.next_steps == ["Write tests"]

    @pytest.mark.asyncio
    async def test_read_handoff_empty(self, mock_supabase, db_client):
        """Test reading when no handoffs exist."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/read_handoff"
        ).mock(return_value=Response(200, json={
            "handoffs": []
        }))

        service = HandoffService(db_client)
        result = await service.read(agent_name="nonexistent-agent")

        assert len(result.handoffs) == 0

    @pytest.mark.asyncio
    async def test_read_handoff_with_limit(self, mock_supabase, db_client):
        """Test reading multiple handoff documents."""
        handoffs = [
            {
                "id": str(uuid4()),
                "agent_name": "test-agent-1",
                "session_id": None,
                "summary": f"Session {i}",
                "completed_work": [],
                "in_progress": [],
                "decisions": [],
                "next_steps": [],
                "relevant_files": [],
                "created_at": f"2024-01-0{i}T12:00:00+00:00",
            }
            for i in range(1, 4)
        ]

        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/read_handoff"
        ).mock(return_value=Response(200, json={"handoffs": handoffs}))

        service = HandoffService(db_client)
        result = await service.read(agent_name="test-agent-1", limit=3)

        assert len(result.handoffs) == 3

    @pytest.mark.asyncio
    async def test_get_recent_handoffs(self, mock_supabase, db_client):
        """Test getting recent handoffs across all agents."""
        handoffs = [
            {
                "id": str(uuid4()),
                "agent_name": f"agent-{i}",
                "session_id": None,
                "summary": f"Work by agent {i}",
                "completed_work": [],
                "in_progress": [],
                "decisions": [],
                "next_steps": [],
                "relevant_files": [],
                "created_at": "2024-01-01T12:00:00+00:00",
            }
            for i in range(1, 3)
        ]

        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/handoff_documents"
        ).mock(return_value=Response(200, json=handoffs))

        service = HandoffService(db_client)
        result = await service.get_recent(limit=5)

        assert len(result) == 2
        assert result[0].agent_name == "agent-1"
        assert result[1].agent_name == "agent-2"

    @pytest.mark.asyncio
    async def test_write_handoff_denied_by_policy(self, monkeypatch):
        """write_handoff is blocked when policy engine denies mutation."""

        class DenyPolicyEngine:
            async def check_operation(self, **_kwargs):
                return PolicyDecision.deny("operation_not_permitted")

        class FailDB:
            async def rpc(self, *_args, **_kwargs):
                raise AssertionError("DB RPC should not run when denied")

        monkeypatch.setattr(
            "src.policy_engine.get_policy_engine",
            lambda: DenyPolicyEngine(),
        )

        service = HandoffService(FailDB())
        result = await service.write(summary="blocked by policy")

        assert result.success is False
        assert result.error == "operation_not_permitted"


class TestHandoffDataClasses:
    """Tests for handoff dataclasses."""

    def test_handoff_document_from_dict(self):
        """Test creating a HandoffDocument from a dictionary."""
        data = {
            "id": str(uuid4()),
            "agent_name": "test-agent",
            "session_id": "session-1",
            "summary": "Test handoff",
            "completed_work": ["item1", "item2"],
            "in_progress": ["item3"],
            "decisions": ["decision1"],
            "next_steps": ["step1"],
            "relevant_files": ["file1.py"],
            "created_at": "2024-01-01T12:00:00Z",
        }

        doc = HandoffDocument.from_dict(data)

        assert doc.agent_name == "test-agent"
        assert doc.summary == "Test handoff"
        assert doc.completed_work == ["item1", "item2"]
        assert doc.created_at is not None

    def test_handoff_document_from_dict_minimal(self):
        """Test creating a HandoffDocument with minimal fields."""
        data = {
            "id": str(uuid4()),
            "agent_name": "test-agent",
            "summary": "Minimal handoff",
        }

        doc = HandoffDocument.from_dict(data)

        assert doc.agent_name == "test-agent"
        assert doc.summary == "Minimal handoff"
        assert doc.completed_work == []
        assert doc.in_progress == []
        assert doc.session_id is None

    def test_write_handoff_result_success(self):
        """Test WriteHandoffResult from success response."""
        handoff_id = str(uuid4())
        result = WriteHandoffResult.from_dict({
            "success": True,
            "handoff_id": handoff_id,
        })

        assert result.success is True
        assert str(result.handoff_id) == handoff_id

    def test_write_handoff_result_failure(self):
        """Test WriteHandoffResult from failure response."""
        result = WriteHandoffResult.from_dict({
            "success": False,
            "error": "summary_required",
        })

        assert result.success is False
        assert result.error == "summary_required"
        assert result.handoff_id is None

    def test_read_handoff_result_from_dict(self):
        """Test ReadHandoffResult from response."""
        result = ReadHandoffResult.from_dict({
            "handoffs": [
                {
                    "id": str(uuid4()),
                    "agent_name": "agent-1",
                    "session_id": None,
                    "summary": "Test",
                    "completed_work": [],
                    "in_progress": [],
                    "decisions": [],
                    "next_steps": [],
                    "relevant_files": [],
                    "created_at": "2024-01-01T12:00:00+00:00",
                }
            ]
        })

        assert len(result.handoffs) == 1
        assert result.handoffs[0].summary == "Test"

    def test_read_handoff_result_empty(self):
        """Test ReadHandoffResult with no handoffs."""
        result = ReadHandoffResult.from_dict({"handoffs": []})

        assert len(result.handoffs) == 0

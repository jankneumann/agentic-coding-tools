"""Tests for the memory service."""

from uuid import uuid4

import pytest
from httpx import Response

from src.memory import EpisodicMemory, MemoryResult, MemoryService, RecallResult
from src.policy_engine import PolicyDecision


class TestMemoryService:
    """Tests for MemoryService."""

    @pytest.mark.asyncio
    async def test_remember_success(self, mock_supabase, db_client):
        """Test storing an episodic memory."""
        memory_id = str(uuid4())
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/store_episodic_memory"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "memory_id": memory_id,
                    "action": "created",
                },
            )
        )

        service = MemoryService(db_client)
        result = await service.remember(
            event_type="discovery",
            summary="Found a useful pattern for error handling",
            tags=["python", "error-handling"],
        )

        assert result.success is True
        assert result.memory_id == memory_id
        assert result.action == "created"

    @pytest.mark.asyncio
    async def test_remember_deduplicated(self, mock_supabase, db_client):
        """Test deduplication of similar memories."""
        memory_id = str(uuid4())
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/store_episodic_memory"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "memory_id": memory_id,
                    "action": "deduplicated",
                },
            )
        )

        service = MemoryService(db_client)
        result = await service.remember(
            event_type="discovery",
            summary="Found a useful pattern for error handling",
        )

        assert result.success is True
        assert result.action == "deduplicated"

    @pytest.mark.asyncio
    async def test_recall_with_results(self, mock_supabase, db_client):
        """Test recalling memories with results."""
        memories = [
            {
                "id": str(uuid4()),
                "agent_id": "test-agent-1",
                "event_type": "success",
                "summary": "Successfully refactored auth module",
                "details": {},
                "outcome": "positive",
                "lessons": ["Use dependency injection"],
                "tags": ["refactoring", "auth"],
                "relevance_score": 0.9,
                "created_at": "2024-01-01T12:00:00+00:00",
            },
        ]

        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_relevant_memories"
        ).mock(return_value=Response(200, json=memories))

        service = MemoryService(db_client)
        result = await service.recall(tags=["refactoring"])

        assert len(result.memories) == 1
        assert result.memories[0].summary == "Successfully refactored auth module"
        assert result.memories[0].relevance_score == 0.9

    @pytest.mark.asyncio
    async def test_recall_empty(self, mock_supabase, db_client):
        """Test recalling when no memories match."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_relevant_memories"
        ).mock(return_value=Response(200, json=[]))

        service = MemoryService(db_client)
        result = await service.recall(tags=["nonexistent"])

        assert len(result.memories) == 0

    @pytest.mark.asyncio
    async def test_remember_denied_by_policy(self, monkeypatch):
        """remember is blocked when policy engine denies mutation."""

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

        service = MemoryService(FailDB())
        result = await service.remember(
            event_type="discovery",
            summary="blocked by policy",
        )

        assert result.success is False
        assert result.error == "operation_not_permitted"


class TestMemoryDataClasses:
    """Tests for memory dataclasses."""

    def test_episodic_memory_from_dict(self):
        """Test creating EpisodicMemory from dict."""
        data = {
            "id": str(uuid4()),
            "agent_id": "agent-1",
            "event_type": "error",
            "summary": "Connection timeout",
            "details": {"service": "database"},
            "outcome": "negative",
            "lessons": ["Add retry logic"],
            "tags": ["error", "database"],
            "relevance_score": 0.75,
            "created_at": "2024-01-01T12:00:00+00:00",
        }

        memory = EpisodicMemory.from_dict(data)
        assert memory.event_type == "error"
        assert memory.summary == "Connection timeout"
        assert memory.outcome == "negative"
        assert "Add retry logic" in memory.lessons

    def test_memory_result_from_dict(self):
        """Test creating MemoryResult from dict."""
        result = MemoryResult.from_dict(
            {"success": True, "memory_id": "test-id", "action": "created"}
        )
        assert result.success is True
        assert result.action == "created"

    def test_recall_result_from_empty(self):
        """Test creating RecallResult from empty data."""
        result = RecallResult.from_dict([])
        assert len(result.memories) == 0

    def test_recall_result_from_none(self):
        """Test creating RecallResult from None."""
        result = RecallResult.from_dict(None)
        assert len(result.memories) == 0

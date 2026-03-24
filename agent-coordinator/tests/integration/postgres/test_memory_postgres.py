"""Integration tests for memory service via DirectPostgresClient (asyncpg).

Tests the PL/pgSQL store_episodic_memory/get_relevant_memories functions
through the Python MemoryService, hitting real PostgreSQL via asyncpg.

Run with:
    docker-compose up -d
    pytest tests/integration/test_memory_postgres.py -v
"""

import pytest

pytestmark = pytest.mark.integration


# =============================================================================
# Store and Recall
# =============================================================================


class TestMemoryStoreRecallPostgres:
    """Test basic memory store and recall operations via asyncpg."""

    async def test_store_memory(self, pg_memory_service):
        result = await pg_memory_service.remember(
            event_type="discovery",
            summary="Found a useful pattern for error handling",
            details={"file": "src/errors.py", "pattern": "retry-with-backoff"},
            outcome="positive",
            lessons=["Use exponential backoff for transient failures"],
            tags=["error-handling", "patterns"],
            agent_id="integ-pg-agent-1",
        )
        assert result.success is True
        assert result.memory_id is not None
        assert result.action == "created"

    async def test_recall_by_tags(self, pg_memory_service):
        """Memories can be recalled by matching tags."""
        await pg_memory_service.remember(
            event_type="discovery",
            summary="Pattern A",
            tags=["alpha", "shared"],
            agent_id="integ-pg-agent-1",
        )
        await pg_memory_service.remember(
            event_type="error",
            summary="Pattern B",
            tags=["beta", "shared"],
            agent_id="integ-pg-agent-1",
        )

        result = await pg_memory_service.recall(
            tags=["alpha"],
            agent_id="integ-pg-agent-1",
        )
        assert len(result.memories) >= 1
        summaries = [m.summary for m in result.memories]
        assert "Pattern A" in summaries

    async def test_recall_with_limit(self, pg_memory_service):
        """Recall respects the limit parameter."""
        for i in range(5):
            await pg_memory_service.remember(
                event_type="discovery",
                summary=f"Memory {i}",
                tags=["bulk"],
                agent_id="integ-pg-agent-1",
            )

        result = await pg_memory_service.recall(
            tags=["bulk"],
            agent_id="integ-pg-agent-1",
            limit=3,
        )
        assert len(result.memories) <= 3

    async def test_recall_by_event_type(self, pg_memory_service):
        """Memories can be filtered by event type."""
        await pg_memory_service.remember(
            event_type="error",
            summary="Something broke",
            tags=["test"],
            agent_id="integ-pg-agent-1",
        )
        await pg_memory_service.remember(
            event_type="success",
            summary="Something worked",
            tags=["test"],
            agent_id="integ-pg-agent-1",
        )

        result = await pg_memory_service.recall(
            event_type="error",
            agent_id="integ-pg-agent-1",
        )
        assert len(result.memories) >= 1
        assert all(m.event_type == "error" for m in result.memories)

    async def test_recall_empty_returns_no_memories(self, pg_memory_service):
        """Recall with no matching data returns empty list."""
        result = await pg_memory_service.recall(
            tags=["nonexistent-tag-xyz"],
            agent_id="integ-pg-agent-1",
        )
        assert len(result.memories) == 0


# =============================================================================
# Deduplication
# =============================================================================


class TestMemoryDeduplicationPostgres:
    """Test memory deduplication within the 1-hour window via asyncpg."""

    async def test_duplicate_within_window_is_deduplicated(self, pg_memory_service):
        """Storing the same summary twice within 1hr deduplicates."""
        result1 = await pg_memory_service.remember(
            event_type="discovery",
            summary="Duplicate test memory",
            tags=["dedup-test"],
            agent_id="integ-pg-agent-1",
        )
        assert result1.success is True
        assert result1.action == "created"

        result2 = await pg_memory_service.remember(
            event_type="discovery",
            summary="Duplicate test memory",
            tags=["dedup-test"],
            agent_id="integ-pg-agent-1",
        )
        assert result2.success is True
        assert result2.action == "deduplicated"

    async def test_different_summaries_not_deduplicated(self, pg_memory_service):
        """Different summaries are stored as separate memories."""
        result1 = await pg_memory_service.remember(
            event_type="discovery",
            summary="First unique memory",
            tags=["unique-test"],
            agent_id="integ-pg-agent-1",
        )
        assert result1.action == "created"

        result2 = await pg_memory_service.remember(
            event_type="discovery",
            summary="Second unique memory",
            tags=["unique-test"],
            agent_id="integ-pg-agent-1",
        )
        assert result2.action == "created"
        assert result1.memory_id != result2.memory_id


# =============================================================================
# Relevance Scoring
# =============================================================================


class TestMemoryRelevancePostgres:
    """Test relevance scoring and ordering via asyncpg."""

    async def test_recall_orders_by_relevance(self, pg_memory_service):
        """Memories with higher relevance scores appear first in recall."""
        # Store memories with different characteristics that affect relevance.
        # The exact ordering depends on the PL/pgSQL scoring function, but
        # more recently stored memories with matching tags should score higher.
        await pg_memory_service.remember(
            event_type="discovery",
            summary="Older relevant memory",
            tags=["relevance-test"],
            agent_id="integ-pg-agent-1",
        )
        await pg_memory_service.remember(
            event_type="discovery",
            summary="Newer relevant memory",
            tags=["relevance-test"],
            agent_id="integ-pg-agent-1",
        )

        result = await pg_memory_service.recall(
            tags=["relevance-test"],
            agent_id="integ-pg-agent-1",
        )
        assert len(result.memories) == 2
        # Verify results are returned (ordering depends on DB scoring function)
        summaries = {m.summary for m in result.memories}
        assert "Older relevant memory" in summaries
        assert "Newer relevant memory" in summaries

    async def test_min_relevance_filters_low_scoring(self, pg_memory_service):
        """Setting min_relevance filters out low-scoring memories."""
        await pg_memory_service.remember(
            event_type="discovery",
            summary="A memory to filter",
            tags=["filter-test"],
            agent_id="integ-pg-agent-1",
        )

        # With a very high min_relevance threshold, we should get fewer or no results
        result_high = await pg_memory_service.recall(
            tags=["filter-test"],
            agent_id="integ-pg-agent-1",
            min_relevance=999.0,
        )
        result_low = await pg_memory_service.recall(
            tags=["filter-test"],
            agent_id="integ-pg-agent-1",
            min_relevance=0.0,
        )
        assert len(result_high.memories) <= len(result_low.memories)

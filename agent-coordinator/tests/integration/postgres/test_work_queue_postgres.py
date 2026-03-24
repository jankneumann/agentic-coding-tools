"""Integration tests for work queue via DirectPostgresClient (asyncpg).

Tests the PL/pgSQL claim_task/complete_task/submit_task functions through
the Python WorkQueueService, hitting real PostgreSQL via asyncpg.

Run with:
    docker-compose up -d
    pytest tests/integration/test_work_queue_postgres.py -v
"""

import asyncio
from uuid import UUID

import pytest

pytestmark = pytest.mark.integration


# =============================================================================
# Task Lifecycle
# =============================================================================


class TestWorkQueueLifecyclePostgres:
    """Test basic task submit/claim/complete operations via asyncpg."""

    async def test_submit_task(self, pg_work_queue):
        result = await pg_work_queue.submit(
            task_type="test",
            description="Integration test task",
            input_data={"key": "value"},
        )
        assert result.success is True
        assert result.task_id is not None
        assert isinstance(result.task_id, UUID)

    async def test_submit_and_claim(self, pg_work_queue):
        submit = await pg_work_queue.submit(
            task_type="refactor",
            description="Refactor auth module",
            input_data={"files": ["src/auth.py"]},
            priority=3,
        )

        claim = await pg_work_queue.claim(
            agent_id="integ-pg-agent-1",
            agent_type="test_agent",
        )
        assert claim.success is True
        assert claim.task_id == submit.task_id
        assert claim.task_type == "refactor"
        assert claim.description == "Refactor auth module"
        assert claim.priority == 3

    async def test_full_lifecycle(self, pg_work_queue):
        """Task goes through submit -> claim -> complete."""
        await pg_work_queue.submit(task_type="test", description="Write tests")

        claim = await pg_work_queue.claim(
            agent_id="integ-pg-agent-1", agent_type="test_agent"
        )
        assert claim.success is True

        complete = await pg_work_queue.complete(
            task_id=claim.task_id,
            success=True,
            result={"tests_passed": 5},
            agent_id="integ-pg-agent-1",
        )
        assert complete.success is True
        assert complete.status == "completed"

    async def test_complete_with_failure(self, pg_work_queue):
        await pg_work_queue.submit(task_type="test", description="Failing task")
        claim = await pg_work_queue.claim(
            agent_id="integ-pg-agent-1", agent_type="test_agent"
        )

        complete = await pg_work_queue.complete(
            task_id=claim.task_id,
            success=False,
            error_message="Tests failed: 3 errors",
            agent_id="integ-pg-agent-1",
        )
        assert complete.success is True
        assert complete.status == "failed"


# =============================================================================
# Priority Ordering
# =============================================================================


class TestWorkQueuePriorityPostgres:
    """Test task priority ordering via asyncpg."""

    async def test_claim_priority_order(self, pg_work_queue):
        """Higher priority tasks (lower number) are claimed first."""
        await pg_work_queue.submit(
            task_type="low", description="Low priority", priority=8
        )
        await pg_work_queue.submit(
            task_type="high", description="High priority", priority=2
        )
        await pg_work_queue.submit(
            task_type="mid", description="Mid priority", priority=5
        )

        claim1 = await pg_work_queue.claim(
            agent_id="integ-pg-agent-1", agent_type="test_agent"
        )
        assert claim1.task_type == "high"
        assert claim1.priority == 2

        claim2 = await pg_work_queue.claim(
            agent_id="integ-pg-agent-1", agent_type="test_agent"
        )
        assert claim2.task_type == "mid"
        assert claim2.priority == 5

    async def test_claim_empty_queue(self, pg_work_queue):
        result = await pg_work_queue.claim(
            agent_id="integ-pg-agent-1", agent_type="test_agent"
        )
        assert result.success is False
        assert result.reason == "no_tasks_available"

    async def test_claim_with_type_filter(self, pg_work_queue):
        await pg_work_queue.submit(task_type="refactor", description="Refactor task")
        await pg_work_queue.submit(task_type="test", description="Test task")

        claim = await pg_work_queue.claim(
            agent_id="integ-pg-agent-1",
            agent_type="test_agent",
            task_types=["test"],
        )
        assert claim.success is True
        assert claim.task_type == "test"


# =============================================================================
# Dependencies
# =============================================================================


class TestWorkQueueDependenciesPostgres:
    """Test task dependency resolution via asyncpg."""

    async def test_blocked_task_not_claimable(self, pg_work_queue):
        """Tasks with unfinished dependencies cannot be claimed."""
        dep = await pg_work_queue.submit(
            task_type="build", description="Build first"
        )
        await pg_work_queue.submit(
            task_type="deploy",
            description="Deploy after build",
            depends_on=[dep.task_id],
        )

        # Should get the build task (no deps), not deploy
        claim = await pg_work_queue.claim(
            agent_id="integ-pg-agent-1", agent_type="test_agent"
        )
        assert claim.task_type == "build"

        # No more claimable tasks (deploy is blocked)
        claim2 = await pg_work_queue.claim(
            agent_id="integ-pg-agent-1", agent_type="test_agent"
        )
        assert claim2.success is False

    async def test_completing_dependency_unblocks_task(self, pg_work_queue):
        """Completing a dependency makes the dependent task claimable."""
        dep = await pg_work_queue.submit(
            task_type="build", description="Build first"
        )
        await pg_work_queue.submit(
            task_type="deploy",
            description="Deploy after build",
            depends_on=[dep.task_id],
        )

        # Claim and complete the dependency
        claim = await pg_work_queue.claim(
            agent_id="integ-pg-agent-1", agent_type="test_agent"
        )
        assert claim.task_type == "build"
        await pg_work_queue.complete(
            task_id=claim.task_id, success=True, agent_id="integ-pg-agent-1"
        )

        # Now the deploy task should be claimable
        claim2 = await pg_work_queue.claim(
            agent_id="integ-pg-agent-1", agent_type="test_agent"
        )
        assert claim2.success is True
        assert claim2.task_type == "deploy"

    async def test_failed_dependency_still_blocks(self, pg_work_queue):
        """A failed dependency does not unblock dependents."""
        dep = await pg_work_queue.submit(
            task_type="build", description="Build first"
        )
        await pg_work_queue.submit(
            task_type="deploy",
            description="Deploy after build",
            depends_on=[dep.task_id],
        )

        claim = await pg_work_queue.claim(
            agent_id="integ-pg-agent-1", agent_type="test_agent"
        )
        await pg_work_queue.complete(
            task_id=claim.task_id,
            success=False,
            error_message="build failed",
            agent_id="integ-pg-agent-1",
        )

        # Deploy is still blocked (dep is 'failed', not 'completed')
        claim2 = await pg_work_queue.claim(
            agent_id="integ-pg-agent-1", agent_type="test_agent"
        )
        assert claim2.success is False


# =============================================================================
# Concurrency
# =============================================================================


class TestWorkQueueConcurrencyPostgres:
    """Test concurrent access patterns via asyncpg."""

    async def test_concurrent_claims_single_task(self, pg_work_queue, make_pg_agent):
        """Two agents racing to claim one task: exactly one wins."""
        await pg_work_queue.submit(task_type="test", description="Single task")

        _, _, agent2_queue = make_pg_agent("integ-pg-agent-2")

        results = await asyncio.gather(
            pg_work_queue.claim(agent_id="integ-pg-agent-1", agent_type="test_agent"),
            agent2_queue.claim(agent_id="integ-pg-agent-2", agent_type="test_agent"),
        )

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 1
        assert len(failures) == 1

    async def test_concurrent_claims_distribute_tasks(self, pg_work_queue, make_pg_agent):
        """Two agents claiming from a two-task queue each get a different task."""
        await pg_work_queue.submit(
            task_type="test", description="Task 1", priority=1
        )
        await pg_work_queue.submit(
            task_type="test", description="Task 2", priority=2
        )

        _, _, agent2_queue = make_pg_agent("integ-pg-agent-2")

        results = await asyncio.gather(
            pg_work_queue.claim(agent_id="integ-pg-agent-1", agent_type="test_agent"),
            agent2_queue.claim(agent_id="integ-pg-agent-2", agent_type="test_agent"),
        )

        assert all(r.success for r in results)
        task_ids = {r.task_id for r in results}
        assert len(task_ids) == 2  # Each got a different task

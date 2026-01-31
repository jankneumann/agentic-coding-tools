"""Integration tests for work queue against local Supabase.

Tests the PL/pgSQL claim_task/complete_task/submit_task functions through
the Python WorkQueueService, hitting real PostgREST + PostgreSQL.

Run with:
    docker-compose up -d
    pytest tests/integration/test_work_queue_integration.py -v
"""

import asyncio
from uuid import UUID

import pytest

pytestmark = pytest.mark.integration


# =============================================================================
# Task Lifecycle
# =============================================================================


class TestTaskLifecycle:
    """Test basic task submit/claim/complete operations."""

    async def test_submit_task(self, work_queue):
        result = await work_queue.submit(
            task_type="test",
            description="Integration test task",
            input_data={"key": "value"},
        )
        assert result.success is True
        assert result.task_id is not None
        assert isinstance(result.task_id, UUID)

    async def test_submit_and_claim(self, work_queue):
        submit = await work_queue.submit(
            task_type="refactor",
            description="Refactor auth module",
            input_data={"files": ["src/auth.py"]},
            priority=3,
        )

        claim = await work_queue.claim(
            agent_id="integ-agent-1",
            agent_type="test_agent",
        )
        assert claim.success is True
        assert claim.task_id == submit.task_id
        assert claim.task_type == "refactor"
        assert claim.description == "Refactor auth module"
        assert claim.priority == 3

    async def test_full_lifecycle(self, work_queue):
        """Task goes through submit -> claim -> complete."""
        await work_queue.submit(task_type="test", description="Write tests")

        claim = await work_queue.claim(
            agent_id="integ-agent-1", agent_type="test_agent"
        )
        assert claim.success is True

        complete = await work_queue.complete(
            task_id=claim.task_id,
            success=True,
            result={"tests_passed": 5},
            agent_id="integ-agent-1",
        )
        assert complete.success is True
        assert complete.status == "completed"

    async def test_complete_with_failure(self, work_queue):
        await work_queue.submit(task_type="test", description="Failing task")
        claim = await work_queue.claim(
            agent_id="integ-agent-1", agent_type="test_agent"
        )

        complete = await work_queue.complete(
            task_id=claim.task_id,
            success=False,
            error_message="Tests failed: 3 errors",
            agent_id="integ-agent-1",
        )
        assert complete.success is True
        assert complete.status == "failed"


# =============================================================================
# Claim Behavior
# =============================================================================


class TestClaimBehavior:
    """Test task claiming edge cases and ordering."""

    async def test_claim_empty_queue(self, work_queue):
        result = await work_queue.claim(
            agent_id="integ-agent-1", agent_type="test_agent"
        )
        assert result.success is False
        assert result.reason == "no_tasks_available"

    async def test_claim_priority_order(self, work_queue):
        """Higher priority tasks (lower number) are claimed first."""
        await work_queue.submit(
            task_type="low", description="Low priority", priority=8
        )
        await work_queue.submit(
            task_type="high", description="High priority", priority=2
        )
        await work_queue.submit(
            task_type="mid", description="Mid priority", priority=5
        )

        claim1 = await work_queue.claim(
            agent_id="integ-agent-1", agent_type="test_agent"
        )
        assert claim1.task_type == "high"
        assert claim1.priority == 2

        claim2 = await work_queue.claim(
            agent_id="integ-agent-1", agent_type="test_agent"
        )
        assert claim2.task_type == "mid"
        assert claim2.priority == 5

    async def test_claim_with_type_filter(self, work_queue):
        await work_queue.submit(task_type="refactor", description="Refactor task")
        await work_queue.submit(task_type="test", description="Test task")

        claim = await work_queue.claim(
            agent_id="integ-agent-1",
            agent_type="test_agent",
            task_types=["test"],
        )
        assert claim.success is True
        assert claim.task_type == "test"

    async def test_claim_type_filter_no_match(self, work_queue):
        await work_queue.submit(task_type="refactor", description="Refactor task")

        claim = await work_queue.claim(
            agent_id="integ-agent-1",
            agent_type="test_agent",
            task_types=["deploy"],
        )
        assert claim.success is False
        assert claim.reason == "no_tasks_available"

    async def test_complete_wrong_agent_fails(self, work_queue, make_agent):
        """Agent cannot complete a task claimed by another."""
        await work_queue.submit(task_type="test", description="Test task")

        claim = await work_queue.claim(
            agent_id="integ-agent-1", agent_type="test_agent"
        )
        assert claim.success is True

        _, _, agent2_queue = make_agent("integ-agent-2")
        result = await agent2_queue.complete(
            task_id=claim.task_id,
            success=True,
            agent_id="integ-agent-2",
        )
        assert result.success is False

    async def test_already_claimed_not_reclaimable(self, work_queue, make_agent):
        """A claimed task cannot be claimed again by another agent."""
        await work_queue.submit(task_type="test", description="Single task")

        claim = await work_queue.claim(
            agent_id="integ-agent-1", agent_type="test_agent"
        )
        assert claim.success is True

        _, _, agent2_queue = make_agent("integ-agent-2")
        claim2 = await agent2_queue.claim(
            agent_id="integ-agent-2", agent_type="test_agent"
        )
        assert claim2.success is False


# =============================================================================
# Task Dependencies
# =============================================================================


class TestTaskDependencies:
    """Test task dependency resolution in the PL/pgSQL claim_task function."""

    async def test_blocked_task_not_claimable(self, work_queue):
        """Tasks with unfinished dependencies cannot be claimed."""
        dep = await work_queue.submit(
            task_type="build", description="Build first"
        )
        await work_queue.submit(
            task_type="deploy",
            description="Deploy after build",
            depends_on=[dep.task_id],
        )

        # Should get the build task (no deps), not deploy
        claim = await work_queue.claim(
            agent_id="integ-agent-1", agent_type="test_agent"
        )
        assert claim.task_type == "build"

        # No more claimable tasks (deploy is blocked)
        claim2 = await work_queue.claim(
            agent_id="integ-agent-1", agent_type="test_agent"
        )
        assert claim2.success is False

    async def test_completing_dependency_unblocks_task(self, work_queue):
        """Completing a dependency makes the dependent task claimable."""
        dep = await work_queue.submit(
            task_type="build", description="Build first"
        )
        await work_queue.submit(
            task_type="deploy",
            description="Deploy after build",
            depends_on=[dep.task_id],
        )

        # Claim and complete the dependency
        claim = await work_queue.claim(
            agent_id="integ-agent-1", agent_type="test_agent"
        )
        assert claim.task_type == "build"
        await work_queue.complete(
            task_id=claim.task_id, success=True, agent_id="integ-agent-1"
        )

        # Now the deploy task should be claimable
        claim2 = await work_queue.claim(
            agent_id="integ-agent-1", agent_type="test_agent"
        )
        assert claim2.success is True
        assert claim2.task_type == "deploy"

    async def test_failed_dependency_still_blocks(self, work_queue):
        """A failed dependency does not unblock dependents."""
        dep = await work_queue.submit(
            task_type="build", description="Build first"
        )
        await work_queue.submit(
            task_type="deploy",
            description="Deploy after build",
            depends_on=[dep.task_id],
        )

        claim = await work_queue.claim(
            agent_id="integ-agent-1", agent_type="test_agent"
        )
        await work_queue.complete(
            task_id=claim.task_id,
            success=False,
            error_message="build failed",
            agent_id="integ-agent-1",
        )

        # Deploy is still blocked (dep is 'failed', not 'completed')
        claim2 = await work_queue.claim(
            agent_id="integ-agent-1", agent_type="test_agent"
        )
        assert claim2.success is False


# =============================================================================
# Task Queries
# =============================================================================


class TestTaskQueries:
    """Test task query operations against real data."""

    async def test_get_pending_tasks(self, work_queue):
        await work_queue.submit(
            task_type="test", description="Task 1", priority=3
        )
        await work_queue.submit(
            task_type="test", description="Task 2", priority=1
        )

        tasks = await work_queue.get_pending()
        assert len(tasks) == 2
        # Ordered by priority ascending
        assert tasks[0].priority == 1
        assert tasks[1].priority == 3

    async def test_get_task_by_id(self, work_queue):
        submit = await work_queue.submit(
            task_type="test", description="Specific task"
        )

        task = await work_queue.get_task(submit.task_id)
        assert task is not None
        assert task.id == submit.task_id
        assert task.description == "Specific task"
        assert task.status == "pending"

    async def test_get_task_reflects_claim(self, work_queue):
        """After claiming, get_task shows the updated status."""
        submit = await work_queue.submit(
            task_type="test", description="Track me"
        )

        await work_queue.claim(
            agent_id="integ-agent-1", agent_type="test_agent"
        )

        task = await work_queue.get_task(submit.task_id)
        assert task.status == "claimed"
        assert task.claimed_by == "integ-agent-1"


# =============================================================================
# Concurrency
# =============================================================================


class TestConcurrency:
    """Test concurrent access patterns using asyncio.gather."""

    async def test_concurrent_claims_single_task(self, work_queue, make_agent):
        """Two agents racing to claim one task: exactly one wins."""
        await work_queue.submit(task_type="test", description="Single task")

        _, _, agent2_queue = make_agent("integ-agent-2")

        results = await asyncio.gather(
            work_queue.claim(agent_id="integ-agent-1", agent_type="test_agent"),
            agent2_queue.claim(agent_id="integ-agent-2", agent_type="test_agent"),
        )

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 1
        assert len(failures) == 1

    async def test_concurrent_claims_distribute_tasks(self, work_queue, make_agent):
        """Two agents claiming from a two-task queue each get a different task."""
        await work_queue.submit(
            task_type="test", description="Task 1", priority=1
        )
        await work_queue.submit(
            task_type="test", description="Task 2", priority=2
        )

        _, _, agent2_queue = make_agent("integ-agent-2")

        results = await asyncio.gather(
            work_queue.claim(agent_id="integ-agent-1", agent_type="test_agent"),
            agent2_queue.claim(agent_id="integ-agent-2", agent_type="test_agent"),
        )

        assert all(r.success for r in results)
        task_ids = {r.task_id for r in results}
        assert len(task_ids) == 2  # Each got a different task

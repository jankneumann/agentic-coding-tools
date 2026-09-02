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


class TestWorkQueueProjectionMigrationContract:
    def test_migration_035_static_contract(self):
        from pathlib import Path

        sql = (
            Path(__file__).resolve().parents[3]
            / "database/migrations/035_work_queue_projection.sql"
        ).read_text()
        assert "DROP FUNCTION IF EXISTS coordinator_notify(TEXT,TEXT,TEXT,TEXT,TEXT);" in sql
        assert "CREATE TABLE IF NOT EXISTS work_queue_projection_heads" in sql
        assert "CREATE UNIQUE INDEX IF NOT EXISTS work_queue_projection_key_uidx" in sql
        assert "phase TEXT NOT NULL" in sql
        assert "pg_advisory_xact_lock(hashtextextended" in sql
        assert "projection_generation_mismatch" in sql
        assert "reconciliation_required" in sql
        assert "cancelled_by_projection_reconcile" in sql
        assert "ON CONFLICT ((input_data ->>" in sql
        assert "OR (CASE WHEN" in sql
        assert "ELSE FALSE END)" in sql
        statements = [line.strip() for line in sql.splitlines()]
        assert "BEGIN;" in statements
        assert "COMMIT;" in statements
        assert statements.index("BEGIN;") < statements.index(
            "LOCK TABLE work_queue IN SHARE ROW EXCLUSIVE MODE;"
        ) < statements.index("COMMIT;")

    @pytest.mark.asyncio
    async def test_projection_submit_replay_returns_one_canonical_task(self, pg_work_queue):
        key = {"change_id": "projection-change", "phase": "IMPLEMENT", "transition_sequence": 1}
        first, second = await asyncio.gather(
            pg_work_queue.submit(task_type="implement", description="one", projection_key=key),
            pg_work_queue.submit(task_type="implement", description="one", projection_key=key),
        )
        assert first.task_id == second.task_id
        assert sorted([first.created, second.created]) == [False, True]

    @pytest.mark.asyncio
    async def test_projection_head_rejects_equal_sequence_different_phase(self, pg_work_queue):
        first = {"change_id": "projection-change", "phase": "IMPLEMENT", "transition_sequence": 2}
        mismatch = {"change_id": "projection-change", "phase": "VALIDATE", "transition_sequence": 2}
        assert (
            await pg_work_queue.submit(
                task_type="implement", description="one", projection_key=first
            )
        ).success is True
        result = await pg_work_queue.submit(
            task_type="validate", description="wrong generation", projection_key=mismatch
        )
        assert result.success is False
        assert result.reason == "projection_generation_mismatch"

    @pytest.mark.asyncio
    async def test_reconcile_advances_full_head_and_cancels_stale(self, pg_work_queue):
        old = {"change_id": "projection-change", "phase": "IMPLEMENT", "transition_sequence": 3}
        new = {"change_id": "projection-change", "phase": "VALIDATE", "transition_sequence": 4}
        stale = await pg_work_queue.submit(
            task_type="implement", description="old", projection_key=old
        )
        current = await pg_work_queue.reconcile_projection(
            projection_key=new, task_type="validate", description="current"
        )
        assert current.success is True
        assert current.created is True
        assert stale.task_id in current.cancelled_task_ids
        replay = await pg_work_queue.reconcile_projection(
            projection_key=new, task_type="validate", description="current"
        )
        assert replay.task_id == current.task_id
        assert replay.created is False


class TestCompleteTaskTerminalCancellation:
    """Migration 036: cancellation by reconciliation must be terminal.

    Without the ``status IN ('claimed', 'running')`` guard in complete_task,
    a worker that was already cancelled by reconcile_work_projection could
    still flip its now-terminal ``cancelled`` row back to
    ``completed``/``failed`` by calling complete_task after the fact.
    """

    async def test_late_complete_after_reconcile_cancel_is_refused(self, pg_work_queue):
        stale = {"change_id": "terminal-change", "phase": "IMPLEMENT", "transition_sequence": 1}
        fresh = {"change_id": "terminal-change", "phase": "VALIDATE", "transition_sequence": 2}

        submitted = await pg_work_queue.submit(
            task_type="implement", description="stale work", projection_key=stale
        )
        claim = await pg_work_queue.claim(
            agent_id="integ-pg-agent-1", agent_type="test_agent"
        )
        assert claim.task_id == submitted.task_id

        reconciled = await pg_work_queue.reconcile_projection(
            projection_key=fresh, task_type="validate", description="fresh work"
        )
        assert submitted.task_id in reconciled.cancelled_task_ids

        cancelled_task = await pg_work_queue.get_task(submitted.task_id)
        assert cancelled_task.status == "cancelled"

        late_complete = await pg_work_queue.complete(
            task_id=submitted.task_id,
            success=True,
            result={"output": "too late"},
            agent_id="integ-pg-agent-1",
        )
        assert late_complete.success is False
        assert late_complete.reason == "task_not_active"
        assert late_complete.status == "cancelled"

        # The cancellation must not have been overwritten by the late call.
        still_cancelled = await pg_work_queue.get_task(submitted.task_id)
        assert still_cancelled.status == "cancelled"
        assert still_cancelled.result is not None
        assert still_cancelled.result.get("reason") == "cancelled_by_projection_reconcile"

    async def test_complete_still_succeeds_for_active_claimed_task(self, pg_work_queue):
        """The new status filter does not regress the ordinary completion path."""
        await pg_work_queue.submit(task_type="test", description="normal task")
        claim = await pg_work_queue.claim(
            agent_id="integ-pg-agent-1", agent_type="test_agent"
        )
        assert claim.success is True

        complete = await pg_work_queue.complete(
            task_id=claim.task_id,
            success=True,
            result={"ok": True},
            agent_id="integ-pg-agent-1",
        )
        assert complete.success is True
        assert complete.status == "completed"

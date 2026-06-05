"""Tests for evaluator agent profile (Task 2.1).

Verifies:
- Evaluator profile has read-only permissions (allowed: read, review, evaluate)
- Evaluator profile blocks write/commit/push/delete operations
- Work queue prefers evaluator agent_type for evaluation tasks
- Work queue never assigns evaluation task to the same agent_id that generated the work
"""

from uuid import uuid4

import pytest
from httpx import Response

from src.profiles import AgentProfile, OperationCheck, ProfilesService


class TestEvaluatorProfilePermissions:
    """Tests for evaluator profile operation restrictions."""

    def _make_evaluator_profile(self) -> AgentProfile:
        """Create an evaluator profile matching the migration seed."""
        return AgentProfile(
            id=str(uuid4()),
            name="evaluator",
            agent_type="evaluator",
            trust_level=2,
            allowed_operations=["read", "review", "evaluate"],
            blocked_operations=["write", "commit", "push", "delete"],
            max_file_modifications=0,
            max_execution_time_seconds=600,
            max_api_calls_per_hour=500,
            enabled=True,
        )

    @pytest.mark.asyncio
    async def test_evaluator_allows_read(self, mock_supabase, db_client):
        """Evaluator profile allows read operations."""
        profile = self._make_evaluator_profile()
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(
            return_value=Response(200, json={
                "success": True,
                "profile": {
                    "id": profile.id,
                    "name": profile.name,
                    "agent_type": profile.agent_type,
                    "trust_level": profile.trust_level,
                    "allowed_operations": profile.allowed_operations,
                    "blocked_operations": profile.blocked_operations,
                    "max_file_modifications": profile.max_file_modifications,
                    "max_execution_time_seconds": profile.max_execution_time_seconds,
                    "max_api_calls_per_hour": profile.max_api_calls_per_hour,
                    "enabled": profile.enabled,
                },
                "source": "assignment",
            })
        )

        service = ProfilesService(db_client)
        result = await service.check_operation(
            operation="read",
            agent_id="eval-agent-1",
            agent_type="evaluator",
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_evaluator_allows_review(self, mock_supabase, db_client):
        """Evaluator profile allows review operations."""
        profile = self._make_evaluator_profile()
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(
            return_value=Response(200, json={
                "success": True,
                "profile": {
                    "id": profile.id,
                    "name": profile.name,
                    "agent_type": profile.agent_type,
                    "trust_level": profile.trust_level,
                    "allowed_operations": profile.allowed_operations,
                    "blocked_operations": profile.blocked_operations,
                    "max_file_modifications": profile.max_file_modifications,
                    "max_execution_time_seconds": profile.max_execution_time_seconds,
                    "max_api_calls_per_hour": profile.max_api_calls_per_hour,
                    "enabled": profile.enabled,
                },
                "source": "assignment",
            })
        )

        service = ProfilesService(db_client)
        result = await service.check_operation(
            operation="review",
            agent_id="eval-agent-1",
            agent_type="evaluator",
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_evaluator_allows_evaluate(self, mock_supabase, db_client):
        """Evaluator profile allows evaluate operations."""
        profile = self._make_evaluator_profile()
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(
            return_value=Response(200, json={
                "success": True,
                "profile": {
                    "id": profile.id,
                    "name": profile.name,
                    "agent_type": profile.agent_type,
                    "trust_level": profile.trust_level,
                    "allowed_operations": profile.allowed_operations,
                    "blocked_operations": profile.blocked_operations,
                    "max_file_modifications": profile.max_file_modifications,
                    "max_execution_time_seconds": profile.max_execution_time_seconds,
                    "max_api_calls_per_hour": profile.max_api_calls_per_hour,
                    "enabled": profile.enabled,
                },
                "source": "assignment",
            })
        )

        service = ProfilesService(db_client)
        result = await service.check_operation(
            operation="evaluate",
            agent_id="eval-agent-1",
            agent_type="evaluator",
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_evaluator_blocks_write(self, mock_supabase, db_client):
        """Evaluator profile blocks write operations."""
        profile = self._make_evaluator_profile()
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(
            return_value=Response(200, json={
                "success": True,
                "profile": {
                    "id": profile.id,
                    "name": profile.name,
                    "agent_type": profile.agent_type,
                    "trust_level": profile.trust_level,
                    "allowed_operations": profile.allowed_operations,
                    "blocked_operations": profile.blocked_operations,
                    "max_file_modifications": profile.max_file_modifications,
                    "max_execution_time_seconds": profile.max_execution_time_seconds,
                    "max_api_calls_per_hour": profile.max_api_calls_per_hour,
                    "enabled": profile.enabled,
                },
                "source": "assignment",
            })
        )
        # Mock audit log for denial
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/audit_log"
        ).mock(return_value=Response(201, json={"id": str(uuid4())}))

        service = ProfilesService(db_client)
        result = await service.check_operation(
            operation="write",
            agent_id="eval-agent-1",
            agent_type="evaluator",
        )

        assert result.allowed is False
        assert "operation_blocked" in (result.reason or "")

    @pytest.mark.asyncio
    async def test_evaluator_blocks_commit(self, mock_supabase, db_client):
        """Evaluator profile blocks commit operations."""
        profile = self._make_evaluator_profile()
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(
            return_value=Response(200, json={
                "success": True,
                "profile": {
                    "id": profile.id,
                    "name": profile.name,
                    "agent_type": profile.agent_type,
                    "trust_level": profile.trust_level,
                    "allowed_operations": profile.allowed_operations,
                    "blocked_operations": profile.blocked_operations,
                    "max_file_modifications": profile.max_file_modifications,
                    "max_execution_time_seconds": profile.max_execution_time_seconds,
                    "max_api_calls_per_hour": profile.max_api_calls_per_hour,
                    "enabled": profile.enabled,
                },
                "source": "assignment",
            })
        )
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/audit_log"
        ).mock(return_value=Response(201, json={"id": str(uuid4())}))

        service = ProfilesService(db_client)
        result = await service.check_operation(
            operation="commit",
            agent_id="eval-agent-1",
            agent_type="evaluator",
        )

        assert result.allowed is False
        assert "operation_blocked" in (result.reason or "")

    @pytest.mark.asyncio
    async def test_evaluator_blocks_push(self, mock_supabase, db_client):
        """Evaluator profile blocks push operations."""
        profile = self._make_evaluator_profile()
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(
            return_value=Response(200, json={
                "success": True,
                "profile": {
                    "id": profile.id,
                    "name": profile.name,
                    "agent_type": profile.agent_type,
                    "trust_level": profile.trust_level,
                    "allowed_operations": profile.allowed_operations,
                    "blocked_operations": profile.blocked_operations,
                    "max_file_modifications": profile.max_file_modifications,
                    "max_execution_time_seconds": profile.max_execution_time_seconds,
                    "max_api_calls_per_hour": profile.max_api_calls_per_hour,
                    "enabled": profile.enabled,
                },
                "source": "assignment",
            })
        )
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/audit_log"
        ).mock(return_value=Response(201, json={"id": str(uuid4())}))

        service = ProfilesService(db_client)
        result = await service.check_operation(
            operation="push",
            agent_id="eval-agent-1",
            agent_type="evaluator",
        )

        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_evaluator_blocks_delete(self, mock_supabase, db_client):
        """Evaluator profile blocks delete operations."""
        profile = self._make_evaluator_profile()
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(
            return_value=Response(200, json={
                "success": True,
                "profile": {
                    "id": profile.id,
                    "name": profile.name,
                    "agent_type": profile.agent_type,
                    "trust_level": profile.trust_level,
                    "allowed_operations": profile.allowed_operations,
                    "blocked_operations": profile.blocked_operations,
                    "max_file_modifications": profile.max_file_modifications,
                    "max_execution_time_seconds": profile.max_execution_time_seconds,
                    "max_api_calls_per_hour": profile.max_api_calls_per_hour,
                    "enabled": profile.enabled,
                },
                "source": "assignment",
            })
        )
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/audit_log"
        ).mock(return_value=Response(201, json={"id": str(uuid4())}))

        service = ProfilesService(db_client)
        result = await service.check_operation(
            operation="delete",
            agent_id="eval-agent-1",
            agent_type="evaluator",
        )

        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_evaluator_blocks_non_allowlisted_operation(
        self, mock_supabase, db_client
    ):
        """Evaluator profile blocks operations not in allowed_operations."""
        profile = self._make_evaluator_profile()
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(
            return_value=Response(200, json={
                "success": True,
                "profile": {
                    "id": profile.id,
                    "name": profile.name,
                    "agent_type": profile.agent_type,
                    "trust_level": profile.trust_level,
                    "allowed_operations": profile.allowed_operations,
                    "blocked_operations": profile.blocked_operations,
                    "max_file_modifications": profile.max_file_modifications,
                    "max_execution_time_seconds": profile.max_execution_time_seconds,
                    "max_api_calls_per_hour": profile.max_api_calls_per_hour,
                    "enabled": profile.enabled,
                },
                "source": "assignment",
            })
        )
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/audit_log"
        ).mock(return_value=Response(201, json={"id": str(uuid4())}))

        service = ProfilesService(db_client)
        result = await service.check_operation(
            operation="acquire_lock",
            agent_id="eval-agent-1",
            agent_type="evaluator",
        )

        assert result.allowed is False
        assert "operation_not_in_allowlist" in (result.reason or "")

    def test_evaluator_max_file_modifications_is_zero(self):
        """Evaluator profile has max_file_modifications=0 (truly read-only)."""
        profile = self._make_evaluator_profile()
        assert profile.max_file_modifications == 0


class TestWorkQueueEvaluatorPreference:
    """Tests for work queue evaluator agent_type preference and self-review prevention."""

    @pytest.mark.asyncio
    async def test_evaluation_task_prefers_evaluator_type(
        self, mock_supabase, db_client
    ):
        """Work queue prefers evaluator agent_type for evaluation tasks.

        The claim_task RPC is expected to handle evaluator preference at the
        database level. This test verifies that when an evaluator agent claims
        an evaluation task, the claim succeeds with proper typing.
        """
        from src.work_queue import WorkQueueService

        task_id = str(uuid4())

        # Mock policy engine check
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/evaluate_policy"
        ).mock(return_value=Response(200, json={"allowed": True}))

        # Mock claim_task RPC returning an evaluation task
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/claim_task"
        ).mock(
            return_value=Response(200, json={
                "success": True,
                "task_id": task_id,
                "task_type": "evaluate",
                "description": "Review implementation of auth module",
                "input_data": {
                    "submitted_by": "generator-agent-1",
                    "files": ["src/auth.py"],
                },
                "priority": 3,
                "deadline": None,
            })
        )

        # Mock guardrails check (safe)
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/operation_guardrails"
        ).mock(return_value=Response(200, json=[]))

        # Mock profile lookup for trust level resolution
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/get_agent_profile"
        ).mock(
            return_value=Response(200, json={
                "success": True,
                "profile": {
                    "id": str(uuid4()),
                    "name": "evaluator",
                    "agent_type": "evaluator",
                    "trust_level": 2,
                    "allowed_operations": ["read", "review", "evaluate"],
                    "blocked_operations": ["write", "commit", "push", "delete"],
                    "max_file_modifications": 0,
                },
                "source": "assignment",
            })
        )

        # Mock audit log
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/audit_log"
        ).mock(return_value=Response(201, json={"id": str(uuid4())}))

        service = WorkQueueService(db_client)
        result = await service.claim(
            agent_id="eval-agent-1",
            agent_type="evaluator",
            task_types=["evaluate"],
        )

        assert result.success is True
        assert result.task_type == "evaluate"

    @pytest.mark.asyncio
    async def test_evaluation_task_not_assigned_to_author(
        self, mock_supabase, db_client
    ):
        """Work queue should not assign evaluation tasks to the same agent
        that generated the work. The claim_task RPC is expected to enforce
        this at the DB level using input_data.submitted_by. When the same
        agent tries to claim, no task should be available.
        """
        from src.work_queue import WorkQueueService

        # Mock policy engine check
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/evaluate_policy"
        ).mock(return_value=Response(200, json={"allowed": True}))

        # When the generator agent tries to claim evaluation work,
        # the RPC returns no tasks available (because claim_task excludes
        # tasks where submitted_by = claiming agent_id)
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/claim_task"
        ).mock(
            return_value=Response(200, json={
                "success": False,
                "reason": "no_tasks_available",
            })
        )

        # Mock audit log
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/audit_log"
        ).mock(return_value=Response(201, json={"id": str(uuid4())}))

        service = WorkQueueService(db_client)
        result = await service.claim(
            agent_id="generator-agent-1",
            agent_type="claude_code",
            task_types=["evaluate"],
        )

        # The generator agent should not get any evaluation tasks
        assert result.success is False

"""Tests for the work queue service."""

from uuid import UUID

import pytest
import respx
from httpx import Response

from src.work_queue import WorkQueueService, Task, ClaimResult, CompleteResult, SubmitResult


class TestWorkQueueService:
    """Tests for WorkQueueService."""

    @pytest.mark.asyncio
    async def test_claim_task_success(
        self, mock_supabase, db_client, task_claimed_response
    ):
        """Test successful task claim."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/claim_task"
        ).mock(return_value=Response(200, json=task_claimed_response))

        service = WorkQueueService(db_client)
        result = await service.claim()

        assert result.success is True
        assert result.task_id is not None
        assert result.task_type == "refactor"
        assert result.description == "Refactor authentication module"
        assert result.priority == 3

    @pytest.mark.asyncio
    async def test_claim_task_with_types(
        self, mock_supabase, db_client, task_claimed_response
    ):
        """Test claiming a task with specific types."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/claim_task"
        ).mock(return_value=Response(200, json=task_claimed_response))

        service = WorkQueueService(db_client)
        result = await service.claim(task_types=["refactor", "test"])

        assert result.success is True

    @pytest.mark.asyncio
    async def test_claim_no_tasks_available(
        self, mock_supabase, db_client, no_tasks_response
    ):
        """Test claiming when no tasks are available."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/claim_task"
        ).mock(return_value=Response(200, json=no_tasks_response))

        service = WorkQueueService(db_client)
        result = await service.claim()

        assert result.success is False
        assert result.reason == "no_tasks_available"
        assert result.task_id is None

    @pytest.mark.asyncio
    async def test_complete_task_success(
        self, mock_supabase, db_client, task_completed_response
    ):
        """Test successful task completion."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/complete_task"
        ).mock(return_value=Response(200, json=task_completed_response))

        service = WorkQueueService(db_client)
        task_id = UUID(task_completed_response["task_id"])

        result = await service.complete(
            task_id=task_id,
            success=True,
            result={"files_modified": ["src/auth.py"]},
        )

        assert result.success is True
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_complete_task_failure(self, mock_supabase, db_client):
        """Test marking a task as failed."""
        response = {
            "success": True,
            "status": "failed",
            "task_id": str(UUID(int=1)),
        }
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/complete_task"
        ).mock(return_value=Response(200, json=response))

        service = WorkQueueService(db_client)

        result = await service.complete(
            task_id=UUID(int=1),
            success=False,
            error_message="Tests failed: 3 assertions",
        )

        assert result.success is True
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_submit_task_success(
        self, mock_supabase, db_client, task_submitted_response
    ):
        """Test successful task submission."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/submit_task"
        ).mock(return_value=Response(200, json=task_submitted_response))

        service = WorkQueueService(db_client)
        result = await service.submit(
            task_type="test",
            description="Write tests for new feature",
            input_data={"files": ["src/feature.py"]},
            priority=3,
        )

        assert result.success is True
        assert result.task_id is not None

    @pytest.mark.asyncio
    async def test_submit_task_with_dependencies(
        self, mock_supabase, db_client, task_submitted_response
    ):
        """Test submitting a task with dependencies."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/submit_task"
        ).mock(return_value=Response(200, json=task_submitted_response))

        service = WorkQueueService(db_client)
        dep_id = UUID(int=99)

        result = await service.submit(
            task_type="deploy",
            description="Deploy to staging",
            depends_on=[dep_id],
            priority=2,
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_get_pending_tasks(
        self, mock_supabase, db_client, pending_tasks_response
    ):
        """Test getting pending tasks."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/work_queue"
        ).mock(return_value=Response(200, json=pending_tasks_response))

        service = WorkQueueService(db_client)
        tasks = await service.get_pending()

        assert len(tasks) == 2
        assert tasks[0].task_type == "test"
        assert tasks[0].priority == 2
        assert tasks[1].task_type == "refactor"
        assert tasks[1].priority == 5

    @pytest.mark.asyncio
    async def test_get_pending_with_types(
        self, mock_supabase, db_client, pending_tasks_response
    ):
        """Test getting pending tasks filtered by type."""
        # Return only test tasks
        filtered = [pending_tasks_response[0]]
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/work_queue"
        ).mock(return_value=Response(200, json=filtered))

        service = WorkQueueService(db_client)
        tasks = await service.get_pending(task_types=["test"])

        assert len(tasks) == 1
        assert tasks[0].task_type == "test"

    @pytest.mark.asyncio
    async def test_get_task_by_id(
        self, mock_supabase, db_client, pending_tasks_response
    ):
        """Test getting a specific task by ID."""
        task_data = pending_tasks_response[0]
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/work_queue"
        ).mock(return_value=Response(200, json=[task_data]))

        service = WorkQueueService(db_client)
        task_id = UUID(task_data["id"])
        task = await service.get_task(task_id)

        assert task is not None
        assert task.id == task_id
        assert task.task_type == "test"

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, mock_supabase, db_client):
        """Test getting a task that doesn't exist."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/work_queue"
        ).mock(return_value=Response(200, json=[]))

        service = WorkQueueService(db_client)
        task = await service.get_task(UUID(int=999))

        assert task is None


class TestTaskDataClasses:
    """Tests for Task and result dataclasses."""

    def test_task_from_dict(self, pending_tasks_response):
        """Test creating a Task from a dictionary."""
        task = Task.from_dict(pending_tasks_response[0])

        assert isinstance(task.id, UUID)
        assert task.task_type == "test"
        assert task.description == "Write unit tests for cache module"
        assert task.status == "pending"
        assert task.priority == 2
        assert task.input_data == {"files": ["src/cache.py"]}

    def test_task_from_dict_with_deadline(self, pending_tasks_response):
        """Test creating a Task with a deadline."""
        task = Task.from_dict(pending_tasks_response[1])

        assert task.deadline is not None
        assert task.task_type == "refactor"

    def test_claim_result_from_dict_success(self, task_claimed_response):
        """Test creating a ClaimResult from a success response."""
        result = ClaimResult.from_dict(task_claimed_response)

        assert result.success is True
        assert result.task_id is not None
        assert result.task_type == "refactor"
        assert result.priority == 3

    def test_claim_result_from_dict_failure(self, no_tasks_response):
        """Test creating a ClaimResult from a failure response."""
        result = ClaimResult.from_dict(no_tasks_response)

        assert result.success is False
        assert result.reason == "no_tasks_available"
        assert result.task_id is None

    def test_complete_result_from_dict(self, task_completed_response):
        """Test creating a CompleteResult from a response."""
        result = CompleteResult.from_dict(task_completed_response)

        assert result.success is True
        assert result.status == "completed"
        assert result.task_id is not None

    def test_submit_result_from_dict(self, task_submitted_response):
        """Test creating a SubmitResult from a response."""
        result = SubmitResult.from_dict(task_submitted_response)

        assert result.success is True
        assert result.task_id is not None


class TestWorkQueueAtomicity:
    """Tests for work queue atomicity and race conditions."""

    @pytest.mark.asyncio
    async def test_concurrent_claim_first_wins(self, mock_supabase, db_client):
        """Test that only one agent claims a task in concurrent requests."""
        task_id = str(UUID(int=1))

        # First request succeeds
        first_response = {
            "success": True,
            "task_id": task_id,
            "task_type": "test",
            "description": "Run tests",
            "priority": 5,
        }

        # Second request fails (no more tasks)
        second_response = {
            "success": False,
            "reason": "no_tasks_available",
        }

        call_count = [0]

        def response_callback(request):
            call_count[0] += 1
            if call_count[0] == 1:
                return Response(200, json=first_response)
            return Response(200, json=second_response)

        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/claim_task"
        ).mock(side_effect=response_callback)

        service = WorkQueueService(db_client)

        # First claim succeeds
        result1 = await service.claim()
        assert result1.success is True
        assert str(result1.task_id) == task_id

        # Second claim fails (task already claimed)
        result2 = await service.claim()
        assert result2.success is False
        assert result2.reason == "no_tasks_available"

    @pytest.mark.asyncio
    async def test_complete_wrong_agent_fails(self, mock_supabase, db_client):
        """Test that an agent can't complete another agent's task."""
        response = {
            "success": False,
            "reason": "task_not_found_or_not_claimed_by_agent",
        }
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/complete_task"
        ).mock(return_value=Response(200, json=response))

        service = WorkQueueService(db_client)

        result = await service.complete(
            task_id=UUID(int=1),
            success=True,
        )

        assert result.success is False
        assert "not_claimed_by_agent" in result.reason

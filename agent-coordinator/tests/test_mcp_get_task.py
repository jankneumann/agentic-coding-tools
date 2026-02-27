"""Tests for the get_task MCP tool."""

from uuid import UUID, uuid4

import pytest
from httpx import Response

from src.work_queue import Task, WorkQueueService


class TestGetTaskMCP:
    """Tests for the get_task MCP tool via WorkQueueService."""

    @pytest.mark.asyncio
    async def test_get_task_found(
        self, mock_supabase, db_client, pending_tasks_response
    ):
        """Test retrieving an existing task."""
        task_data = pending_tasks_response[0]
        mock_supabase.get(
            url__regex=r".*/rest/v1/work_queue.*id=eq\."
        ).mock(return_value=Response(200, json=[task_data]))

        service = WorkQueueService(db_client)
        task = await service.get_task(UUID(task_data["id"]))

        assert task is not None
        assert str(task.id) == task_data["id"]
        assert task.task_type == task_data["task_type"]
        assert task.description == task_data["description"]
        assert task.status == task_data["status"]
        assert task.priority == task_data["priority"]

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, mock_supabase, db_client):
        """Test retrieving a non-existent task returns None."""
        mock_supabase.get(
            url__regex=r".*/rest/v1/work_queue.*id=eq\."
        ).mock(return_value=Response(200, json=[]))

        service = WorkQueueService(db_client)
        task = await service.get_task(uuid4())

        assert task is None

    @pytest.mark.asyncio
    async def test_get_task_with_all_fields(self, mock_supabase, db_client):
        """Test that all Task fields are populated correctly."""
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        task_id = str(uuid4())
        dep_id = str(uuid4())
        task_data = {
            "id": task_id,
            "task_type": "implement",
            "description": "Implement feature X",
            "status": "claimed",
            "priority": 2,
            "input_data": {"package_id": "wp-backend"},
            "claimed_by": "agent-1",
            "claimed_at": now.isoformat(),
            "result": None,
            "error_message": None,
            "depends_on": [dep_id],
            "deadline": now.isoformat(),
            "created_at": now.isoformat(),
            "completed_at": None,
        }

        mock_supabase.get(
            url__regex=r".*/rest/v1/work_queue.*id=eq\."
        ).mock(return_value=Response(200, json=[task_data]))

        service = WorkQueueService(db_client)
        task = await service.get_task(UUID(task_id))

        assert task is not None
        assert str(task.id) == task_id
        assert task.claimed_by == "agent-1"
        assert task.input_data == {"package_id": "wp-backend"}
        assert len(task.depends_on) == 1
        assert str(task.depends_on[0]) == dep_id

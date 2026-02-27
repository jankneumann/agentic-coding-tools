"""Tests for the cancellation convention helper."""

from uuid import uuid4

import pytest
from httpx import Response

from src.work_queue import CompleteResult, WorkQueueService


class TestCancelConvention:
    """Tests for cancel_task_convention()."""

    @pytest.mark.asyncio
    async def test_cancel_calls_complete_with_convention(
        self, mock_supabase, db_client
    ):
        """Cancel should call complete(success=False) with the right payload."""
        task_id = uuid4()
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/complete_task"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "status": "failed",
                    "task_id": str(task_id),
                },
            )
        )

        service = WorkQueueService(db_client)
        result = await service.cancel_task_convention(
            task_id=task_id,
            reason="contract revision bump required",
        )

        assert result.success is True
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_cancel_passes_error_code_in_result(
        self, mock_supabase, db_client
    ):
        """The result payload should contain error_code and reason."""
        task_id = uuid4()

        captured_params: dict = {}

        def capture_rpc(request):
            import json

            captured_params.update(json.loads(request.content))
            return Response(
                200,
                json={
                    "success": True,
                    "status": "failed",
                    "task_id": str(task_id),
                },
            )

        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/complete_task"
        ).mock(side_effect=capture_rpc)

        service = WorkQueueService(db_client)
        await service.cancel_task_convention(
            task_id=task_id,
            reason="scope violation detected",
        )

        assert captured_params["p_success"] is False
        result_payload = captured_params["p_result"]
        assert result_payload["error_code"] == "cancelled_by_orchestrator"
        assert "scope violation" in result_payload["reason"]

    @pytest.mark.asyncio
    async def test_cancel_includes_error_message(
        self, mock_supabase, db_client
    ):
        """The error_message should describe the cancellation."""
        task_id = uuid4()

        captured_params: dict = {}

        def capture_rpc(request):
            import json

            captured_params.update(json.loads(request.content))
            return Response(
                200,
                json={
                    "success": True,
                    "status": "failed",
                    "task_id": str(task_id),
                },
            )

        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/complete_task"
        ).mock(side_effect=capture_rpc)

        service = WorkQueueService(db_client)
        await service.cancel_task_convention(
            task_id=task_id,
            reason="timeout exceeded",
        )

        assert "Cancelled by orchestrator" in captured_params["p_error_message"]
        assert "timeout exceeded" in captured_params["p_error_message"]

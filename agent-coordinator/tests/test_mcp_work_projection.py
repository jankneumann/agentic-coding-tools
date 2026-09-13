"""Projection parity tests for direct and HTTP-proxy MCP."""

from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src import coordination_mcp
from src.work_queue import ReconcileResult, SubmitResult


@pytest.mark.asyncio
async def test_direct_mcp_submit_exposes_deduplicated_result(monkeypatch):
    task_id = UUID(int=11)
    service = AsyncMock()
    service.submit.return_value = SubmitResult(
        success=True, task_id=task_id, created=False, deduplicated=True, status="pending"
    )
    monkeypatch.setattr(coordination_mcp, "_transport", "db")
    monkeypatch.setattr(coordination_mcp, "get_work_queue_service", lambda: service)

    result = await coordination_mcp.submit_work(
        task_type="implement",
        description="project",
        projection_key={
            "change_id": "projection-change",
            "phase": "IMPLEMENT",
            "transition_sequence": 3,
        },
    )

    assert result["task_id"] == str(task_id)
    assert result["created"] is False
    assert result["deduplicated"] is True


@pytest.mark.asyncio
async def test_direct_mcp_reconcile_maps_projection_result(monkeypatch):
    task_id = UUID(int=12)
    service = AsyncMock()
    service.reconcile_projection.return_value = ReconcileResult(
        success=True,
        task_id=task_id,
        created=True,
        deduplicated=False,
        status="pending",
        cancelled_task_ids=[UUID(int=2)],
    )
    monkeypatch.setattr(coordination_mcp, "_transport", "db")
    monkeypatch.setattr(coordination_mcp, "get_work_queue_service", lambda: service)

    result = await coordination_mcp.reconcile_work_projection(
        projection_key={
            "change_id": "projection-change",
            "phase": "IMPLEMENT",
            "transition_sequence": 4,
        },
        task_type="implement",
        description="resume",
    )

    assert result["cancelled_task_ids"] == [str(UUID(int=2))]
    assert result["created"] is True


@pytest.mark.asyncio
async def test_proxy_mcp_forwards_one_explicit_projection_key(monkeypatch):
    monkeypatch.setattr(coordination_mcp, "_transport", "http")
    proxy = AsyncMock(
        return_value={
            "success": True,
            "task_id": str(UUID(int=13)),
            "created": False,
            "deduplicated": True,
        }
    )
    monkeypatch.setattr(coordination_mcp.http_proxy, "proxy_submit_work", proxy)
    key = {"change_id": "projection-change", "phase": "IMPLEMENT", "transition_sequence": 5}

    await coordination_mcp.submit_work(
        task_type="implement", description="proxy", projection_key=key
    )

    assert proxy.await_args.kwargs["projection_key"] == key

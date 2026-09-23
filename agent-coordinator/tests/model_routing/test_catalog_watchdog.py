"""Watchdog scheduling tests for model-routing background jobs."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.watchdog import WatchdogService


@pytest.mark.asyncio
@patch("src.watchdog.get_event_bus")
async def test_routing_job_failure_is_recorded_and_does_not_block_other_jobs(mock_bus) -> None:
    mock_bus.return_value = MagicMock(failed=False)
    db = AsyncMock()
    db.query.return_value = []
    db.rpc.return_value = {"success": True}
    failing = AsyncMock(side_effect=RuntimeError("offline"))
    succeeding = AsyncMock(return_value={"entries": 0})
    service = WatchdogService(
        db=db,
        check_interval=60,
        time_fn=lambda: 1000.0,
        routing_jobs={
            "catalog_refresh": (failing, 300),
            "ledger_rollup": (succeeding, 300),
        },
    )

    await service.run_once()

    failing.assert_awaited_once()
    succeeding.assert_awaited_once()
    failure_rows = [
        call
        for call in db.insert.await_args_list
        if call.args[0] == "audit_log" and call.args[1]["operation"] == "signal.routing_job_failed"
    ]
    assert len(failure_rows) == 1


@pytest.mark.asyncio
async def test_routing_jobs_obey_independent_intervals() -> None:
    db = AsyncMock()
    fast = AsyncMock()
    slow = AsyncMock()
    now = [1000.0]
    service = WatchdogService(
        db=db,
        time_fn=lambda: now[0],
        routing_jobs={"fast": (fast, 60), "slow": (slow, 600)},
    )

    await service._run_routing_jobs()
    now[0] += 61
    await service._run_routing_jobs()

    assert fast.await_count == 2
    assert slow.await_count == 1

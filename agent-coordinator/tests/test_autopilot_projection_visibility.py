"""Behavioral/static guards for migration 037 and live board refresh."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest


def test_migration_excludes_all_issue_rows_and_uses_old_label_fallback() -> None:
    sql = (
        Path(__file__).parents[1]
        / "database/migrations/037_autopilot_phase_projection_visibility.sql"
    ).read_text()
    assert "task_type <> 'issue'" in sql
    assert "projection:autopilot-phase" in sql
    assert "NEW.labels" in sql
    assert "OLD.labels" in sql


def test_projection_label_events_coalesce_into_one_fresh_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.event_stream as event_stream
    from src.event_bus import CoordinatorEvent

    class FakeBus:
        task_cb: Any = None

        def on_event(self, channel: str, callback: Any) -> None:
            if channel == "coordinator_task":
                self.task_cb = callback

        def off_event(self, channel: str, callback: Any) -> bool:
            return True

    snapshots = 0

    async def fake_snapshot(ids: list[str]) -> str:
        nonlocal snapshots
        snapshots += 1
        return json.dumps({"work_queue": [], "subscribed_change_ids": ids})

    monkeypatch.setattr(event_stream, "_build_snapshot", fake_snapshot)
    bus = FakeBus()

    async def drive() -> dict[str, Any]:
        gen = event_stream.sse_event_generator(["demo"], bus)
        await gen.__anext__()
        event = CoordinatorEvent(
            event_type="projection.labels_changed",
            channel="coordinator_task",
            entity_id="row",
            agent_id="autopilot",
            urgency="low",
            summary="projection labels changed",
            change_id="demo",
        )
        await bus.task_cb(event)
        await bus.task_cb(event)
        assert snapshots == 1
        result = await gen.__anext__()
        await gen.aclose()
        return result

    event = asyncio.run(drive())
    assert event["event"] == "snapshot"
    assert snapshots == 2

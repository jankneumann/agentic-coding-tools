"""Live PostgreSQL acceptance coverage for Autopilot phase projections."""

from __future__ import annotations

import asyncio
import json

import pytest

from src.event_bus import EventBusService
from src.event_stream import sse_event_generator
from src.issue_service import IssueService

from .conftest import POSTGRES_DSN

pytestmark = pytest.mark.integration

_PROJECTION_LABEL = "projection:autopilot-phase"


def _key(change_id: str, phase: str, sequence: int) -> dict[str, object]:
    return {
        "change_id": change_id,
        "phase": phase,
        "transition_sequence": sequence,
    }


async def _wait_until_listening(bus: EventBusService) -> None:
    for _ in range(100):
        connection = bus._connection
        if connection is not None and not connection.is_closed():
            return
        await asyncio.sleep(0.02)
    pytest.fail("PostgreSQL event bus did not become ready within two seconds")


async def test_three_generations_replay_cancel_stale_and_exclude_issues_from_claim(
    pg_work_queue,
    postgres_db,
) -> None:
    """Three live generations converge to one labelled, unclaimable issue row."""
    issues = IssueService(db=postgres_db)
    change_id = "live-three-generations"
    labels = [f"change:{change_id}", _PROJECTION_LABEL]

    first = await pg_work_queue.submit(
        task_type="issue",
        description="Autopilot phase INIT",
        priority=1,
        projection_key=_key(change_id, "INIT", 0),
        projection_labels=labels,
    )
    assert first.success is True

    second_submit = await pg_work_queue.submit(
        task_type="issue",
        description="Autopilot phase PLAN",
        priority=1,
        projection_key=_key(change_id, "PLAN", 1),
        projection_labels=labels,
    )
    assert second_submit.success is False
    assert second_submit.reason == "reconciliation_required"
    second = await pg_work_queue.reconcile_projection(
        task_type="issue",
        description="Autopilot phase PLAN",
        priority=1,
        projection_key=_key(change_id, "PLAN", 1),
        projection_labels=labels,
    )
    assert first.task_id in second.cancelled_task_ids

    third_submit = await pg_work_queue.submit(
        task_type="issue",
        description="Autopilot phase IMPLEMENT",
        priority=1,
        projection_key=_key(change_id, "IMPLEMENT", 2),
        projection_labels=labels,
    )
    assert third_submit.success is False
    assert third_submit.reason == "reconciliation_required"
    third = await pg_work_queue.reconcile_projection(
        task_type="issue",
        description="Autopilot phase IMPLEMENT",
        priority=1,
        projection_key=_key(change_id, "IMPLEMENT", 2),
        projection_labels=labels,
    )
    assert second.task_id in third.cancelled_task_ids

    replay = await pg_work_queue.submit(
        task_type="issue",
        description="Autopilot phase IMPLEMENT",
        priority=1,
        projection_key=_key(change_id, "IMPLEMENT", 2),
        projection_labels=labels,
    )
    assert replay.success is True
    assert replay.created is False
    assert replay.deduplicated is True
    assert replay.task_id == third.task_id

    stale = await pg_work_queue.submit(
        task_type="issue",
        description="Autopilot phase PLAN",
        priority=1,
        projection_key=_key(change_id, "PLAN", 1),
        projection_labels=labels,
    )
    assert stale.success is False
    assert stale.reason == "stale_projection"

    labelled = await issues.list_issues(
        labels=[f"change:{change_id}", _PROJECTION_LABEL],
        limit=100,
    )
    assert [issue.id for issue in labelled] == [third.task_id]
    rows = await postgres_db.query(
        "work_queue",
        f"input_data->>change_id=eq.{change_id}&order=created_at.asc",
    )
    assert [row["status"] for row in rows] == ["cancelled", "cancelled", "pending"]
    assert [row["labels"] for row in rows] == [
        [],
        [],
        labels,
    ]

    ordinary = await pg_work_queue.submit(
        task_type="test",
        description="Only executable row",
        priority=9,
    )
    claimed = await pg_work_queue.claim(
        agent_id="integ-pg-agent-1",
        agent_type="test_agent",
    )
    assert claimed.success is True
    assert claimed.task_id == ordinary.task_id
    assert claimed.task_type == "test"


async def test_priority_one_projection_survives_exact_label_query_window_over_50(
    pg_work_queue,
    postgres_db,
) -> None:
    """The existing label-only board query retains the projection in its first page."""
    issues = IssueService(db=postgres_db)
    change_id = "live-window"
    label = f"change:{change_id}"

    for index in range(55):
        await issues.create(
            title=f"Ordinary issue {index:02d}",
            priority=2,
            labels=[label],
        )

    projection = await pg_work_queue.submit(
        task_type="issue",
        description="Autopilot phase VALIDATE",
        priority=1,
        projection_key=_key(change_id, "VALIDATE", 3),
        projection_labels=[label, _PROJECTION_LABEL],
    )

    first_page = await issues.list_issues(labels=[label])
    assert len(first_page) == 50
    assert first_page[0].id == projection.task_id
    assert first_page[0].priority == 1
    assert first_page[0].labels == [label, _PROJECTION_LABEL]


async def test_connected_sse_refreshes_after_atomic_projection_reconciliation(
    pg_work_queue,
    postgres_db,
) -> None:
    """A connected client receives a fresh current-only projection snapshot."""
    change_id = "live-sse"
    labels = [f"change:{change_id}", _PROJECTION_LABEL]

    old = await pg_work_queue.submit(
        task_type="issue",
        description="Autopilot phase PLAN",
        priority=1,
        projection_key=_key(change_id, "PLAN", 1),
        projection_labels=labels,
    )

    bus = EventBusService(dsn=POSTGRES_DSN, channels=("coordinator_task",))
    await bus.start()
    await _wait_until_listening(bus)
    stream = sse_event_generator([change_id], bus)
    try:
        initial = await asyncio.wait_for(stream.__anext__(), timeout=5)
        assert initial["event"] == "snapshot"
        assert [row["id"] for row in json.loads(initial["data"])["work_queue"]] == [
            str(old.task_id)
        ]

        current = await pg_work_queue.reconcile_projection(
            task_type="issue",
            description="Autopilot phase IMPLEMENT",
            priority=1,
            projection_key=_key(change_id, "IMPLEMENT", 2),
            projection_labels=labels,
        )

        refreshed = await asyncio.wait_for(stream.__anext__(), timeout=5)
        assert refreshed["event"] == "snapshot"
        assert [row["id"] for row in json.loads(refreshed["data"])["work_queue"]] == [
            str(current.task_id)
        ]
    finally:
        await stream.aclose()
        await bus.stop()

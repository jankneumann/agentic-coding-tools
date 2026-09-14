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


async def test_connected_sse_refreshes_for_first_canonical_projection_insert(
    pg_work_queue,
) -> None:
    """The first labelled projection insert refreshes an already-connected client."""
    change_id = "live-first-insert-sse"
    labels = [f"change:{change_id}", _PROJECTION_LABEL]
    bus = EventBusService(dsn=POSTGRES_DSN, channels=("coordinator_task",))
    await bus.start()
    await _wait_until_listening(bus)
    stream = sse_event_generator([change_id], bus)
    try:
        initial = await asyncio.wait_for(stream.__anext__(), timeout=5)
        assert json.loads(initial["data"])["work_queue"] == []

        created = await pg_work_queue.submit(
            task_type="issue",
            description="Autopilot phase INIT",
            priority=1,
            projection_key=_key(change_id, "INIT", 0),
            projection_labels=labels,
        )
        assert created.success is True

        refreshed = await asyncio.wait_for(stream.__anext__(), timeout=1)
        assert refreshed["event"] == "snapshot"
        assert [row["id"] for row in json.loads(refreshed["data"])["work_queue"]] == [
            str(created.task_id)
        ]
    finally:
        await stream.aclose()
        await bus.stop()


async def test_same_generation_submit_replay_clears_noncanonical_owned_labels(
    pg_work_queue,
    postgres_db,
) -> None:
    change_id = "live-submit-replay-repair"
    labels = [f"change:{change_id}", _PROJECTION_LABEL]
    key = _key(change_id, "INIT", 0)
    canonical = await pg_work_queue.submit(
        task_type="issue",
        description="Autopilot phase INIT",
        priority=1,
        projection_key=key,
        projection_labels=labels,
    )
    stale = await postgres_db.insert(
        "work_queue",
        {
            "task_type": "issue",
            "description": "stale owned projection",
            "input_data": _key(change_id, "PLAN", 1),
            "priority": 1,
            "status": "cancelled",
            "labels": labels,
        },
    )
    await postgres_db.insert(
        "work_queue_projection_ownership",
        {"task_id": str(stale["id"])},
    )

    replay = await pg_work_queue.submit(
        task_type="issue",
        description="Autopilot phase INIT",
        priority=1,
        projection_key=key,
        projection_labels=labels,
    )

    assert replay.success is True
    assert replay.task_id == canonical.task_id
    rows = await postgres_db.query(
        "work_queue", f"input_data->>change_id=eq.{change_id}&order=created_at.asc"
    )
    labels_by_id = {str(row["id"]): row["labels"] for row in rows}
    assert labels_by_id[str(canonical.task_id)] == labels
    assert labels_by_id[str(stale["id"])] == []


async def test_reconcile_leaves_unowned_spoofed_projection_issue_untouched(
    pg_work_queue,
    postgres_db,
) -> None:
    change_id = "live-unowned-noncanonical-spoof"
    labels = [f"change:{change_id}", _PROJECTION_LABEL]
    canonical = await pg_work_queue.submit(
        task_type="issue",
        description="Autopilot phase INIT",
        priority=1,
        projection_key=_key(change_id, "INIT", 0),
        projection_labels=labels,
    )
    spoof = await postgres_db.insert(
        "work_queue",
        {
            "task_type": "issue",
            "description": "ordinary issue spoofing projection metadata",
            "input_data": _key(change_id, "PLAN", 99),
            "priority": 5,
            "labels": labels,
        },
    )

    reconciled = await pg_work_queue.reconcile_projection(
        task_type="issue",
        description="Autopilot phase IMPLEMENT",
        priority=1,
        projection_key=_key(change_id, "IMPLEMENT", 1),
        projection_labels=labels,
    )

    assert reconciled.success is True
    assert canonical.task_id in reconciled.cancelled_task_ids
    assert str(spoof["id"]) not in {str(item) for item in reconciled.cancelled_task_ids}
    rows = await postgres_db.query(
        "work_queue", f"input_data->>change_id=eq.{change_id}&order=created_at.asc"
    )
    rows_by_id = {str(row["id"]): row for row in rows}
    spoof_row = rows_by_id[str(spoof["id"])]
    assert spoof_row["status"] == "pending"
    assert spoof_row["labels"] == labels
    assert spoof_row["result"] is None


async def test_submit_collision_with_nonissue_is_fail_closed(
    pg_work_queue,
    postgres_db,
) -> None:
    change_id = "live-submit-key-collision"
    key = _key(change_id, "INIT", 0)
    collision = await postgres_db.insert(
        "work_queue",
        {
            "task_type": "test",
            "description": "ordinary row owns target key",
            "input_data": key,
            "priority": 5,
            "labels": ["ordinary"],
        },
    )

    result = await pg_work_queue.submit(
        task_type="issue",
        description="Autopilot phase INIT",
        priority=1,
        projection_key=key,
        projection_labels=[f"change:{change_id}", _PROJECTION_LABEL],
    )

    assert result.success is False
    assert result.reason == "projection_key_collision"
    rows = await postgres_db.query("work_queue", f"id=eq.{collision['id']}")
    assert rows[0]["task_type"] == "test"
    assert rows[0]["status"] == "pending"
    assert rows[0]["labels"] == ["ordinary"]
    heads = await postgres_db.query("work_queue_projection_heads", f"change_id=eq.{change_id}")
    assert heads == []


async def test_reconcile_collision_with_nonissue_preserves_head_and_active_row(
    pg_work_queue,
    postgres_db,
) -> None:
    change_id = "live-reconcile-key-collision"
    labels = [f"change:{change_id}", _PROJECTION_LABEL]
    current = await pg_work_queue.submit(
        task_type="issue",
        description="Autopilot phase PLAN",
        priority=1,
        projection_key=_key(change_id, "PLAN", 1),
        projection_labels=labels,
    )
    collision = await postgres_db.insert(
        "work_queue",
        {
            "task_type": "test",
            "description": "ordinary row owns next key",
            "input_data": _key(change_id, "IMPLEMENT", 2),
            "priority": 5,
            "labels": ["ordinary"],
        },
    )

    result = await pg_work_queue.reconcile_projection(
        task_type="issue",
        description="Autopilot phase IMPLEMENT",
        priority=1,
        projection_key=_key(change_id, "IMPLEMENT", 2),
        projection_labels=labels,
    )

    assert result.success is False
    assert result.reason == "projection_key_collision"
    rows = await postgres_db.query(
        "work_queue", f"input_data->>change_id=eq.{change_id}&order=created_at.asc"
    )
    rows_by_id = {str(row["id"]): row for row in rows}
    assert rows_by_id[str(current.task_id)]["status"] == "pending"
    assert rows_by_id[str(current.task_id)]["labels"] == labels
    collision_row = rows_by_id[str(collision["id"])]
    assert collision_row["task_type"] == "test"
    assert collision_row["status"] == "pending"
    assert collision_row["labels"] == ["ordinary"]
    heads = await postgres_db.query("work_queue_projection_heads", f"change_id=eq.{change_id}")
    assert [(row["phase"], row["transition_sequence"]) for row in heads] == [("PLAN", 1)]


@pytest.mark.parametrize("mode", ["submit", "reconcile"])
async def test_owned_projection_cannot_take_over_unowned_issue_key(
    mode,
    pg_work_queue,
    postgres_db,
) -> None:
    change_id = f"live-unowned-issue-collision-{mode}"
    labels = [f"change:{change_id}", _PROJECTION_LABEL]
    target = _key(change_id, "INIT", 0)
    current = None
    if mode == "reconcile":
        current = await pg_work_queue.submit(
            task_type="issue",
            description="Autopilot phase PLAN",
            priority=1,
            projection_key=_key(change_id, "PLAN", 1),
            projection_labels=labels,
        )
        target = _key(change_id, "IMPLEMENT", 2)

    collision = await postgres_db.insert(
        "work_queue",
        {
            "task_type": "issue",
            "description": "ordinary issue owns exact projection tuple",
            "input_data": {**target, "_projection_owner": "autopilot"},
            "priority": 5,
            "labels": labels,
        },
    )
    request = {
        "task_type": "issue",
        "description": "Autopilot phase target",
        "priority": 1,
        "projection_key": target,
        "projection_labels": labels,
    }
    if mode == "submit":
        result = await pg_work_queue.submit(**request)
    else:
        result = await pg_work_queue.reconcile_projection(**request)

    assert result.success is False
    assert result.reason == "projection_key_collision"
    collision_id = str(collision["id"])
    rows = await postgres_db.query("work_queue", f"id=eq.{collision_id}")
    assert rows[0]["description"] == "ordinary issue owns exact projection tuple"
    assert rows[0]["status"] == "pending"
    assert rows[0]["labels"] == labels
    heads = await postgres_db.query(
        "work_queue_projection_heads", f"change_id=eq.{change_id}"
    )
    if mode == "submit":
        assert heads == []
    else:
        assert current is not None
        assert [(row["phase"], row["transition_sequence"]) for row in heads] == [
            ("PLAN", 1)
        ]
        current_rows = await postgres_db.query(
            "work_queue", f"id=eq.{current.task_id}"
        )
        assert current_rows[0]["status"] == "pending"
        assert current_rows[0]["labels"] == labels

@pytest.mark.parametrize("mode", ["submit", "reconcile"])
async def test_owned_same_generation_request_reactivates_terminal_canonical_issue(
    mode,
    pg_work_queue,
    postgres_db,
) -> None:
    change_id = f"live-reactivate-{mode}"
    labels = [f"change:{change_id}", _PROJECTION_LABEL]
    key = _key(change_id, "VALIDATE", 7)
    canonical = await pg_work_queue.submit(
        task_type="issue",
        description="Autopilot phase VALIDATE",
        priority=1,
        projection_key=key,
        projection_labels=labels,
    )
    await postgres_db.update(
        "work_queue",
        {"id": str(canonical.task_id)},
        {
            "status": "cancelled",
            "result": {"reason": "prior terminal state"},
            "error_message": "prior terminal state",
        },
    )
    issues = IssueService(db=postgres_db)
    assert await issues.list_issues(labels=labels) == []

    request = {
        "task_type": "issue",
        "description": "Autopilot phase VALIDATE",
        "priority": 1,
        "projection_key": key,
        "projection_labels": labels,
    }
    if mode == "submit":
        result = await pg_work_queue.submit(**request)
    else:
        result = await pg_work_queue.reconcile_projection(**request)

    assert result.success is True
    visible = await issues.list_issues(labels=labels)
    assert [(issue.id, issue.status) for issue in visible] == [(canonical.task_id, "pending")]
    rows = await postgres_db.query("work_queue", f"id=eq.{canonical.task_id}")
    assert rows[0]["claimed_by"] is None
    assert rows[0]["claimed_at"] is None
    assert rows[0]["started_at"] is None
    assert rows[0]["completed_at"] is None
    assert rows[0]["result"] is None
    assert rows[0]["error_message"] is None


@pytest.mark.parametrize("mode", ["submit", "reconcile"])
async def test_owned_same_generation_replay_preserves_nonterminal_status(
    mode,
    pg_work_queue,
    postgres_db,
) -> None:
    change_id = f"live-preserve-nonterminal-{mode}"
    labels = [f"change:{change_id}", _PROJECTION_LABEL]
    key = _key(change_id, "IMPLEMENT", 5)
    canonical = await pg_work_queue.submit(
        task_type="issue",
        description="Autopilot phase IMPLEMENT",
        priority=1,
        projection_key=key,
        projection_labels=labels,
    )
    await postgres_db.update(
        "work_queue",
        {"id": str(canonical.task_id)},
        {"status": "claimed", "claimed_by": "reviewer-agent"},
    )

    request = {
        "task_type": "issue",
        "description": "Autopilot phase IMPLEMENT replay",
        "priority": 1,
        "projection_key": key,
        "projection_labels": labels,
    }
    if mode == "submit":
        result = await pg_work_queue.submit(**request)
    else:
        result = await pg_work_queue.reconcile_projection(**request)

    assert result.success is True
    assert result.status == "claimed"
    rows = await postgres_db.query("work_queue", f"id=eq.{canonical.task_id}")
    assert rows[0]["status"] == "claimed"
    assert rows[0]["claimed_by"] == "reviewer-agent"
    assert rows[0]["labels"] == labels


async def test_unlabelled_legacy_issue_collision_keeps_pre039_dedupe_semantics(
    pg_work_queue,
    postgres_db,
) -> None:
    change_id = "live-legacy-unlabelled-collision"
    key = _key(change_id, "INIT", 0)
    collision = await postgres_db.insert(
        "work_queue",
        {
            "task_type": "test",
            "description": "legacy keyed row",
            "input_data": key,
            "priority": 5,
            "labels": ["ordinary"],
        },
    )

    result = await pg_work_queue.submit(
        task_type="issue",
        description="legacy unlabeled issue request",
        projection_key=key,
    )

    assert result.success is True
    assert result.created is False
    assert str(result.task_id) == str(collision["id"])
    rows = await postgres_db.query("work_queue", f"id=eq.{collision['id']}")
    assert rows[0]["task_type"] == "test"
    assert rows[0]["labels"] == ["ordinary"]


async def test_terminal_reactivation_refreshes_connected_sse(
    pg_work_queue,
    postgres_db,
) -> None:
    change_id = "live-terminal-reactivation-sse"
    labels = [f"change:{change_id}", _PROJECTION_LABEL]
    key = _key(change_id, "VALIDATE", 7)
    canonical = await pg_work_queue.submit(
        task_type="issue",
        description="Autopilot phase VALIDATE",
        priority=1,
        projection_key=key,
        projection_labels=labels,
    )
    await postgres_db.update(
        "work_queue",
        {"id": str(canonical.task_id)},
        {"status": "completed"},
    )

    bus = EventBusService(dsn=POSTGRES_DSN, channels=("coordinator_task",))
    await bus.start()
    await _wait_until_listening(bus)
    stream = sse_event_generator([change_id], bus)
    try:
        initial = await asyncio.wait_for(stream.__anext__(), timeout=5)
        initial_rows = json.loads(initial["data"])["work_queue"]
        assert initial_rows[0]["status"] == "completed"

        replay = await pg_work_queue.submit(
            task_type="issue",
            description="Autopilot phase VALIDATE",
            priority=1,
            projection_key=key,
            projection_labels=labels,
        )
        assert replay.status == "pending"
        refreshed = await asyncio.wait_for(stream.__anext__(), timeout=1)
        refreshed_rows = json.loads(refreshed["data"])["work_queue"]
        assert refreshed_rows[0]["status"] == "pending"
    finally:
        await stream.aclose()
        await bus.stop()

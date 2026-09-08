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
    assert "DROP FUNCTION IF EXISTS claim_task(TEXT, TEXT, TEXT[])" in sql
    assert (
        "DROP FUNCTION IF EXISTS claim_task(TEXT, TEXT, TEXT[], TEXT[], INTEGER)"
        in sql
    )
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


def test_backpressure_drain_does_not_suppress_later_projection_refresh(
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
    monkeypatch.setattr(event_stream, "_BACKPRESSURE_LIMIT", 2)
    bus = FakeBus()

    async def drive() -> dict[str, Any]:
        gen = event_stream.sse_event_generator(["demo"], bus)
        await gen.__anext__()
        transition = CoordinatorEvent(
            event_type="work.running",
            channel="coordinator_task",
            entity_id="row",
            agent_id="worker",
            urgency="low",
            summary="work running",
            change_id="demo",
        )
        projection = CoordinatorEvent(
            event_type="projection.labels_changed",
            channel="coordinator_task",
            entity_id="projection-row",
            agent_id="autopilot",
            urgency="low",
            summary="projection labels changed",
            change_id="demo",
        )
        for _ in range(3):
            await bus.task_cb(transition)
        await bus.task_cb(projection)

        assert (await gen.__anext__())["event"] == "transition"
        assert (await gen.__anext__())["event"] == "transition"
        assert (await gen.__anext__())["event"] == "snapshot"

        await bus.task_cb(projection)
        result = await asyncio.wait_for(gen.__anext__(), timeout=0.1)
        await gen.aclose()
        return result

    event = asyncio.run(drive())
    assert event["event"] == "snapshot"
    assert snapshots == 3


def test_projection_openapi_problem_contract_matches_runtime() -> None:
    import yaml

    contract_path = (
        Path(__file__).parents[2]
        / "openspec/contracts/agent-coordinator/openapi/work-queue.yaml"
    )
    document = yaml.safe_load(contract_path.read_text())
    problem = document["components"]["schemas"]["Problem"]
    assert problem["required"] == ["type", "title", "status", "detail"]
    assert problem["properties"]["status"]["type"] == "integer"

    for name in ("Problem401", "Problem403", "Problem409", "Problem422"):
        content = document["components"]["responses"][name]["content"]
        assert set(content) == {"application/problem+json"}

    submit = document["paths"]["/work/submit"]["post"]
    reconcile = document["paths"]["/work/reconcile"]["post"]
    assert "agent_requirements" in (
        submit["requestBody"]["content"]["application/json"]["schema"]["properties"]
    )
    for operation in (submit, reconcile):
        assert operation["responses"]["200"]["content"]["application/json"]["schema"][
            "$ref"
        ] == "#/components/schemas/ProjectionMutationResult"
        assert operation["responses"]["401"]["$ref"] == (
            "#/components/responses/Problem401"
        )



def test_projection_payload_rejects_missing_canonical_task_id() -> None:
    from types import SimpleNamespace

    from src.coordination_api import _projection_mutation_payload, _ProjectionProblemError

    result = SimpleNamespace(
        success=True,
        task_id=None,
        created=False,
        deduplicated=False,
        status="pending",
        cancelled_task_ids=[],
    )
    with pytest.raises(_ProjectionProblemError) as exc_info:
        _projection_mutation_payload(result)
    assert exc_info.value.reason == "canonical_task_id_missing"
    assert exc_info.value.status == 422

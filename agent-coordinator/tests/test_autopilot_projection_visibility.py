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
    assert "DROP FUNCTION IF EXISTS claim_task(TEXT, TEXT, TEXT[], TEXT[], INTEGER)" in sql
    assert "projection:autopilot-phase" in sql
    assert "NEW.labels" in sql
    assert "OLD.labels" in sql


def test_migration_038_atomically_repairs_owned_projection_labels() -> None:
    sql = (
        Path(__file__).parents[1] / "database/migrations/038_atomic_projection_labels.sql"
    ).read_text()
    compact = "".join(sql.split())
    assert "p_projection_labelsTEXT[]DEFAULTNULL" in compact
    assert "pg_advisory_xact_lock(hashtextextended" in sql
    assert "projection:autopilot-phase" in sql
    assert "labels=p_projection_labels" in compact
    assert "status='cancelled'" in compact
    assert "COMMIT;" in sql


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
        Path(__file__).parents[2] / "openspec/contracts/agent-coordinator/openapi/work-queue.yaml"
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
    assert (
        "agent_requirements"
        in (submit["requestBody"]["content"]["application/json"]["schema"]["properties"])
    )
    for operation in (submit, reconcile):
        request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
        assert request_schema["additionalProperties"] is False
        properties = request_schema["properties"]
        assert properties["task_type"]["minLength"] == 1
        assert properties["task_description"]["minLength"] == 1
        assert properties["priority"] == {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
        }
        projection_labels = properties["projection_labels"]
        assert projection_labels["minItems"] == 2
        assert projection_labels["maxItems"] == 2
        assert projection_labels["prefixItems"] == [
            {
                "type": "string",
                "pattern": r"^change:[a-z0-9][a-z0-9-]{0,127}$",
                "maxLength": 135,
            },
            {"type": "string", "const": "projection:autopilot-phase"},
        ]
        assert "MUST equal" in projection_labels["description"]
        assert projection_labels["items"] is False
        projection_condition = request_schema["allOf"][0]
        assert projection_condition["if"] == {"required": ["projection_labels"]}
        assert projection_condition["then"]["required"] == [
            "projection_key",
            "task_type",
        ]
        assert projection_condition["then"]["properties"]["task_type"] == {"const": "issue"}
        assert (
            operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/ProjectionMutationResult"
        )
        assert operation["responses"]["401"]["$ref"] == ("#/components/responses/Problem401")
    assert (
        submit["requestBody"]["content"]["application/json"]["schema"]["properties"]["depends_on"][
            "items"
        ]["format"]
        == "uuid"
    )


def test_kanban_label_patch_openapi_declares_projection_forbidden() -> None:
    import yaml

    contract_path = (
        Path(__file__).parents[2]
        / "openspec/contracts/agent-coordinator/openapi/kanban-viz.yaml"
    )
    document = yaml.safe_load(contract_path.read_text())
    responses = document["paths"]["/issues/{issue_id}/labels"]["patch"]["responses"]

    assert "403" in responses
    assert "projection" in responses["403"]["description"].lower()


def test_projection_label_runtime_item_length_matches_openapi() -> None:
    from pydantic import ValidationError

    from src.coordination_api import WorkReconcileRequest, WorkSubmitRequest

    common = {
        "task_type": "issue",
        "task_description": "phase projection",
        "projection_key": {
            "change_id": "ri-09",
            "phase": "IMPLEMENT",
            "transition_sequence": 9,
        },
        "projection_labels": ["x" * 161, "projection:autopilot-phase"],
    }
    with pytest.raises(ValidationError):
        WorkSubmitRequest(**common)
    with pytest.raises(ValidationError):
        WorkReconcileRequest(**common)


@pytest.mark.parametrize("request_type", ["submit", "reconcile"])
def test_projection_label_runtime_uses_heterogeneous_prefix_bounds(
    request_type: str,
) -> None:
    from pydantic import ValidationError

    from src.coordination_api import WorkReconcileRequest, WorkSubmitRequest

    request_model = (
        WorkSubmitRequest if request_type == "submit" else WorkReconcileRequest
    )
    change_id = "a" * 128
    common = {
        "task_type": "issue",
        "task_description": "phase projection",
        "projection_key": {
            "change_id": change_id,
            "phase": "IMPLEMENT",
            "transition_sequence": 9,
        },
    }
    valid = request_model(
        **common,
        projection_labels=[
            f"change:{change_id}",
            "projection:autopilot-phase",
        ],
    )
    assert tuple(valid.projection_labels or ()) == (
        f"change:{change_id}",
        "projection:autopilot-phase",
    )

    with pytest.raises(ValidationError):
        request_model(
            **common,
            projection_labels=[
                "change:" + "a" * 129,
                "projection:autopilot-phase",
            ],
        )

    with pytest.raises(ValidationError):
        request_model(
            **common,
            projection_labels=[f"change:{change_id}", "x" * 160],
        )


def test_truth_projection_guide_documents_terminal_reactivation() -> None:
    guide = (
        Path(__file__).parents[2] / "docs/guides/work-queue-truth-projection.md"
    ).read_text()
    normalized = " ".join(guide.split())
    assert "reactivated to `pending`" in normalized
    assert "blocked rows remain blocked" in normalized


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


def test_projection_key_collision_maps_to_conflict() -> None:
    from types import SimpleNamespace

    from src.coordination_api import _projection_mutation_payload, _ProjectionProblemError

    result = SimpleNamespace(
        success=False,
        failure_category=None,
        reason="projection_key_collision",
    )
    with pytest.raises(_ProjectionProblemError) as exc_info:
        _projection_mutation_payload(result)
    assert exc_info.value.reason == "projection_key_collision"
    assert exc_info.value.status == 409

"""Contract tests for supervisor records on coordinator handoff surfaces."""

from __future__ import annotations

import argparse
import ast
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src import coordination_cli, coordination_mcp, http_proxy
from src.coordination_api import create_coordination_api
from src.handoffs import (
    HandoffDocument,
    HandoffService,
    ReadHandoffResult,
    WriteHandoffResult,
)
from src.policy_engine import PolicyDecision


@pytest.fixture()
def supervisor_record() -> dict[str, Any]:
    """A complete, schema-shaped supervisor record used at every boundary."""
    return {
        "schema_version": 1,
        "written_at": "2026-08-29T03:00:00Z",
        "written_by": {"agent_name": "supervisor", "session_id": "session-1"},
        "active_changes": [
            {
                "change_id": "extend-handoff-document-with-supervisor-record",
                "current_phase": "IMPLEMENT",
            }
        ],
        "pending_gates": [],
        "standing_decisions": [],
        "back_edge": {
            "last_digest_at": None,
            "last_fingerprint": None,
            "digested_stubs": [],
        },
    }


def _handoff_row(supervisor_record: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "agent_name": "supervisor",
        "session_id": "session-1",
        "summary": "Supervisor cycle complete",
        "completed_work": [],
        "in_progress": [],
        "decisions": [],
        "next_steps": [],
        "relevant_files": [],
        "supervisor_record": supervisor_record,
        "created_at": "2026-08-29T03:00:00Z",
    }


def test_handoff_document_defaults_pre_migration_row_to_null_record() -> None:
    row = _handoff_row(None)
    row.pop("supervisor_record")

    document = HandoffDocument.from_dict(row)

    assert document.supervisor_record is None


def test_handoff_document_preserves_supervisor_record(
    supervisor_record: dict[str, Any],
) -> None:
    document = HandoffDocument.from_dict(_handoff_row(supervisor_record))

    assert document.supervisor_record == supervisor_record


def test_handoff_document_preserves_pre_extension_positional_constructor() -> None:
    created_at = datetime(2026, 8, 29, 3, tzinfo=UTC)

    document = HandoffDocument(
        uuid4(),
        "supervisor",
        "session-1",
        "Supervisor cycle complete",
        [],
        [],
        [],
        [],
        [],
        created_at,
    )

    assert document.created_at == created_at
    assert document.supervisor_record is None


@pytest.mark.asyncio
@pytest.mark.parametrize("record", [None, {"schema_version": 1}])
async def test_service_write_forwards_supervisor_record(
    record: dict[str, Any] | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class AllowPolicyEngine:
        async def check_operation(self, **_kwargs: Any) -> PolicyDecision:
            return PolicyDecision.allow("ok")

    class FakeDB:
        async def rpc(self, function_name: str, params: dict[str, Any]) -> dict[str, Any]:
            captured.update(function_name=function_name, params=params)
            return {"success": True, "handoff_id": str(uuid4())}

    monkeypatch.setattr(
        "src.policy_engine.get_policy_engine", lambda: AllowPolicyEngine()
    )

    result = await HandoffService(FakeDB()).write(
        summary="Supervisor cycle complete",
        supervisor_record=record,
    )

    assert result.success is True
    assert captured["function_name"] == "write_handoff"
    assert captured["params"]["p_supervisor_record"] == record


@pytest.mark.asyncio
async def test_service_read_forwards_supervisor_only_filter() -> None:
    captured: dict[str, Any] = {}

    class FakeDB:
        async def rpc(self, function_name: str, params: dict[str, Any]) -> dict[str, Any]:
            captured.update(function_name=function_name, params=params)
            return {"handoffs": []}

    await HandoffService(FakeDB()).read(supervisor_only=True)

    assert captured == {
        "function_name": "read_handoff",
        "params": {
            "p_agent_name": None,
            "p_limit": 1,
            "p_supervisor_only": True,
        },
    }


def test_migration_replaces_rpc_overloads_and_preserves_legacy_behavior() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "database"
        / "migrations"
        / "034_handoff_supervisor_record.sql"
    ).read_text()

    write_signatures = re.findall(
        r"CREATE(?:\s+OR\s+REPLACE)?\s+FUNCTION\s+write_handoff\s*\((.*?)\)\s*RETURNS",
        migration,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert len(write_signatures) == 1
    assert len(re.findall(r"\bp_[a-z_]+\s+[A-Z]+", write_signatures[0])) == 9
    assert "p_supervisor_record JSONB DEFAULT NULL" in write_signatures[0]
    assert (
        "DROP FUNCTION IF EXISTS write_handoff(TEXT, TEXT, TEXT, JSONB, JSONB, "
        "JSONB, JSONB, JSONB);"
        in migration
    )
    assert "p_session_id TEXT DEFAULT NULL" in write_signatures[0]
    assert "p_summary TEXT DEFAULT NULL" in write_signatures[0]
    assert "p_summary IS NULL OR p_summary = ''" in migration
    assert "SECURITY DEFINER" not in migration.upper()

    read_signatures = re.findall(
        r"CREATE(?:\s+OR\s+REPLACE)?\s+FUNCTION\s+read_handoff\s*\((.*?)\)\s*RETURNS",
        migration,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert len(read_signatures) == 1
    assert "p_supervisor_only BOOLEAN DEFAULT FALSE" in read_signatures[0]
    assert "DROP FUNCTION IF EXISTS read_handoff(TEXT, INTEGER);" in migration
    assert "ORDER BY h.created_at DESC" in migration
    assert "NOT p_supervisor_only OR supervisor_record IS NOT NULL" in migration


@pytest.fixture()
def api_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from src.config import reset_config

    reset_config()
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("COORDINATION_API_KEYS", "supervisor-test-key")
    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")
    reset_config()
    return TestClient(create_coordination_api())


def test_http_write_accepts_object_and_null_and_rejects_non_object(
    api_client: TestClient,
    supervisor_record: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.handoffs

    service = AsyncMock()
    service.write.return_value = WriteHandoffResult(success=True)
    monkeypatch.setattr(src.handoffs, "_handoff_service", service)
    headers = {"X-API-Key": "supervisor-test-key"}

    object_response = api_client.post(
        "/handoffs/write",
        headers=headers,
        json={"summary": "object", "supervisor_record": supervisor_record},
    )
    null_response = api_client.post(
        "/handoffs/write",
        headers=headers,
        json={"summary": "null", "supervisor_record": None},
    )
    invalid_response = api_client.post(
        "/handoffs/write",
        headers=headers,
        json={"summary": "invalid", "supervisor_record": ["not", "an", "object"]},
    )

    assert object_response.status_code == 200
    assert service.write.await_args_list[0].kwargs["supervisor_record"] == supervisor_record
    assert null_response.status_code == 200
    assert service.write.await_args_list[1].kwargs["supervisor_record"] is None
    assert invalid_response.status_code == 422
    assert service.write.await_count == 2


def test_http_read_returns_record_and_forwards_supervisor_only(
    api_client: TestClient,
    supervisor_record: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.handoffs

    service = AsyncMock()
    service.read.return_value = ReadHandoffResult(
        handoffs=[HandoffDocument.from_dict(_handoff_row(supervisor_record))]
    )
    monkeypatch.setattr(src.handoffs, "_handoff_service", service)

    response = api_client.post(
        "/handoffs/read",
        headers={"X-API-Key": "supervisor-test-key"},
        json={"limit": 1, "supervisor_only": True},
    )

    assert response.status_code == 200
    assert response.json()["handoffs"][0]["supervisor_record"] == supervisor_record
    assert service.read.await_args.kwargs["supervisor_only"] is True


@pytest.mark.asyncio
async def test_mcp_tools_round_trip_record_and_filter(
    supervisor_record: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AsyncMock()
    service.write.return_value = WriteHandoffResult(success=True, handoff_id=uuid4())
    service.read.return_value = ReadHandoffResult(
        handoffs=[HandoffDocument.from_dict(_handoff_row(supervisor_record))]
    )
    monkeypatch.setattr(coordination_mcp, "_transport", "db")
    monkeypatch.setattr(coordination_mcp, "get_handoff_service", lambda: service)
    monkeypatch.setattr(coordination_mcp, "get_agent_id", lambda: "supervisor")

    write_result = await coordination_mcp.write_handoff(
        summary="Supervisor cycle complete",
        supervisor_record=supervisor_record,
    )
    read_result = await coordination_mcp.read_handoff(supervisor_only=True)

    assert write_result["success"] is True
    assert service.write.await_args.kwargs["supervisor_record"] == supervisor_record
    assert service.read.await_args.kwargs["supervisor_only"] is True
    assert read_result["handoffs"][0]["supervisor_record"] == supervisor_record


@pytest.mark.asyncio
async def test_recent_handoffs_resource_includes_record_as_json(
    supervisor_record: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AsyncMock()
    service.get_recent.return_value = [
        HandoffDocument.from_dict(_handoff_row(supervisor_record))
    ]
    monkeypatch.setattr(coordination_mcp, "_transport", "db")
    monkeypatch.setattr(coordination_mcp, "get_handoff_service", lambda: service)

    rendered = await coordination_mcp.get_recent_handoffs()

    assert json.dumps(supervisor_record, indent=2, sort_keys=True) in rendered


@pytest.mark.asyncio
async def test_http_proxy_forwards_record_and_supervisor_only(
    supervisor_record: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, str, dict[str, Any]]] = []

    async def capture(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        requests.append((method, path, json_body or {}))
        return {"success": True}

    monkeypatch.setattr(http_proxy, "_request", capture)
    monkeypatch.setattr(http_proxy, "_agent_identity", lambda **_kwargs: {})

    await http_proxy.proxy_write_handoff(
        summary="Supervisor cycle complete",
        supervisor_record=supervisor_record,
    )
    await http_proxy.proxy_read_handoff(supervisor_only=True)

    assert requests[0][0:2] == ("POST", "/handoffs/write")
    assert requests[0][2]["supervisor_record"] == supervisor_record
    assert requests[1][0:2] == ("POST", "/handoffs/read")
    assert requests[1][2]["supervisor_only"] is True


def test_cli_read_prints_record_and_forwards_supervisor_only(
    supervisor_record: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import src.handoffs

    service = AsyncMock()
    service.read.return_value = ReadHandoffResult(
        handoffs=[HandoffDocument.from_dict(_handoff_row(supervisor_record))]
    )
    monkeypatch.setattr(src.handoffs, "_handoff_service", service)
    args = argparse.Namespace(
        agent_name="supervisor",
        limit=1,
        supervisor_only=True,
        json=True,
    )

    exit_code = coordination_cli.cmd_handoff_read(args)
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["items"][0]["supervisor_record"] == supervisor_record
    assert service.read.await_args.kwargs["supervisor_only"] is True


def test_handoff_help_documents_schema_valid_supervisor_surfaces(
    supervisor_record: dict[str, Any],
) -> None:
    from src.help_service import get_help_topic

    topic = get_help_topic("handoffs")

    assert topic is not None
    rendered = json.dumps(topic)
    assert "supervisor_record" in rendered
    assert "supervisor_only" in rendered
    example = next(
        item["code"]
        for item in topic["examples"]
        if "supervisor_record" in item["code"]
    )
    call = ast.parse(example).body[0].value
    assert isinstance(call, ast.Call)
    keyword = next(item for item in call.keywords if item.arg == "supervisor_record")
    record = ast.literal_eval(keyword.value)
    assert record.keys() == supervisor_record.keys()

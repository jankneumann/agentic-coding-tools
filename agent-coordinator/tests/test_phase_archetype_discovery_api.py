"""HTTP-layer tests for phase_archetype surfacing through /discovery/agents.

Change: wire-autopilot-phase-subagents — closes deferred D-1.

These tests assert the round-trip from ``DiscoveryService.discover`` to the
JSON response built at ``coordination_api.py``'s ``discovery_agents()``
handler. The handler builds the per-agent dict by hand, so a new
``AgentInfo`` field doesn't reach the wire unless that builder is updated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.coordination_api import create_coordination_api
from src.discovery import AgentInfo, DiscoverResult

_TEST_KEY = "test-key-disco-archetype"


@pytest.fixture()
def _api_config(monkeypatch: pytest.MonkeyPatch) -> Any:
    from src.config import reset_config

    reset_config()
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("COORDINATION_API_KEYS", _TEST_KEY)
    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")
    reset_config()
    yield
    reset_config()


@pytest.fixture()
def client(_api_config: None) -> TestClient:
    return TestClient(create_coordination_api())


def test_get_discovery_agents_includes_phase_archetype(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /discovery/agents MUST include phase_archetype in each AgentInfo dict."""
    from src import discovery

    sample_agents = [
        AgentInfo(
            agent_id="autopilot-1",
            agent_type="claude_code",
            session_id="sess-1",
            capabilities=["coding"],
            status="active",
            current_task="implement",
            last_heartbeat=datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC),
            started_at=datetime(2026, 5, 5, 10, 0, 0, tzinfo=UTC),
            phase_archetype="implementer",
        ),
        AgentInfo(
            agent_id="legacy-2",
            agent_type="codex",
            session_id="sess-2",
            capabilities=[],
            status="idle",
            current_task=None,
            last_heartbeat=datetime(2026, 5, 5, 11, 50, 0, tzinfo=UTC),
            started_at=datetime(2026, 5, 5, 9, 0, 0, tzinfo=UTC),
            phase_archetype=None,
        ),
    ]

    mock_service = AsyncMock()
    mock_service.discover = AsyncMock(
        return_value=DiscoverResult(agents=sample_agents)
    )
    monkeypatch.setattr(
        discovery, "get_discovery_service", lambda: mock_service
    )

    response = client.get("/discovery/agents")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "agents" in body
    agents = body["agents"]
    assert len(agents) == 2

    # The hand-rolled per-agent dict at coordination_api.py:2122 MUST include
    # phase_archetype — without this, the AgentInfo field is silently dropped
    # from the wire response (codex review R1-004).
    assert "phase_archetype" in agents[0]
    assert agents[0]["phase_archetype"] == "implementer"
    assert "phase_archetype" in agents[1]
    assert agents[1]["phase_archetype"] is None


def test_get_discovery_agents_does_not_break_legacy_fields(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adding phase_archetype MUST not remove the existing fields."""
    from src import discovery

    sample = AgentInfo(
        agent_id="a",
        agent_type="t",
        session_id="s",
        capabilities=["c"],
        status="active",
        current_task="task",
        last_heartbeat=datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC),
        started_at=datetime(2026, 5, 5, 10, 0, 0, tzinfo=UTC),
        phase_archetype="architect",
    )
    mock_service = AsyncMock()
    mock_service.discover = AsyncMock(
        return_value=DiscoverResult(agents=[sample])
    )
    monkeypatch.setattr(
        discovery, "get_discovery_service", lambda: mock_service
    )

    response = client.get("/discovery/agents")
    assert response.status_code == 200
    agent = response.json()["agents"][0]
    expected_keys = {
        "agent_id",
        "agent_type",
        "session_id",
        "capabilities",
        "status",
        "current_task",
        "last_heartbeat",
        "started_at",
        "phase_archetype",
    }
    assert expected_keys.issubset(set(agent.keys()))

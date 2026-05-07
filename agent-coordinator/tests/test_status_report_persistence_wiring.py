"""End-to-end wiring tests for POST /status/report persisting phase_archetype.

Change: wire-autopilot-phase-subagents — closes deferred D-2 + D-1 union.

Task 3.7-3.8 specifically: the archived change added ``phase_archetype`` to
the ``StatusReportRequest`` Pydantic model AND to the event-bus context
(coordination_api.py:2006), but the heartbeat call at line 1983 only
passes ``agent_id``. As a result, ``DiscoveryService.heartbeat`` never
receives the value, the agent_sessions row never gets it, and
``GET /discovery/agents`` returns ``phase_archetype: null`` for every
agent that reports through this path.

These tests assert the gap is closed: a status report carrying
``phase_archetype: "architect"`` MUST reach DiscoveryService.heartbeat
with that value, and the corresponding session row would be updated.

Task 3.9: out-of-enum values MUST be rejected by Pydantic with HTTP 422
before ever reaching the discovery layer.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.coordination_api import create_coordination_api

_TEST_KEY = "test-key-status-wire"


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


# ---------------------------------------------------------------------------
# 3.7 + 3.8: phase_archetype reaches DiscoveryService.heartbeat
# ---------------------------------------------------------------------------


def test_status_report_forwards_phase_archetype_to_heartbeat(
    client: TestClient,
) -> None:
    """The endpoint MUST pass ``phase_archetype`` through to discovery.heartbeat.

    Without this forwarding, the value lives only in the event bus context
    (NOTIFY payload) but never reaches the agent_sessions row. /discovery/agents
    would then return ``phase_archetype: null`` even when status reports
    arrive with the value populated.
    """
    mock_heartbeat = AsyncMock()
    with (
        patch("src.discovery.get_discovery_service") as mock_disc,
        patch("src.event_bus.get_event_bus") as mock_bus_fn,
    ):
        mock_disc.return_value.heartbeat = mock_heartbeat
        mock_bus = MagicMock()
        mock_bus.running = False
        mock_bus.failed = False
        mock_bus_fn.return_value = mock_bus

        response = client.post(
            "/status/report",
            json={
                "agent_id": "test-agent",
                "change_id": "c",
                "phase": "PLAN",
                "phase_archetype": "architect",
            },
        )

    assert response.status_code == 200, response.text
    mock_heartbeat.assert_awaited_once()
    call_kwargs = mock_heartbeat.await_args.kwargs
    assert call_kwargs.get("agent_id") == "test-agent"
    assert call_kwargs.get("phase_archetype") == "architect", (
        "phase_archetype MUST be forwarded to DiscoveryService.heartbeat. "
        "Without this, the value would only reach the event bus and the "
        "agent_sessions row would never persist it."
    )


def test_status_report_without_phase_archetype_passes_none_to_heartbeat(
    client: TestClient,
) -> None:
    """Older clients omitting phase_archetype MUST NOT cause a 400 — the
    heartbeat should be called with ``phase_archetype=None``."""
    mock_heartbeat = AsyncMock()
    with (
        patch("src.discovery.get_discovery_service") as mock_disc,
        patch("src.event_bus.get_event_bus") as mock_bus_fn,
    ):
        mock_disc.return_value.heartbeat = mock_heartbeat
        mock_bus = MagicMock()
        mock_bus.running = False
        mock_bus.failed = False
        mock_bus_fn.return_value = mock_bus

        response = client.post(
            "/status/report",
            json={
                "agent_id": "older-agent",
                "change_id": "c",
                "phase": "PLAN",
            },
        )

    assert response.status_code == 200, response.text
    mock_heartbeat.assert_awaited_once()
    # phase_archetype should be None or absent
    call_kwargs = mock_heartbeat.await_args.kwargs
    assert call_kwargs.get("phase_archetype") is None


# ---------------------------------------------------------------------------
# 3.9: Pydantic Literal enum validation rejects out-of-enum values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valid_archetype",
    ["architect", "reviewer", "implementer", "analyst", "runner"],
)
def test_status_report_accepts_each_valid_archetype(
    client: TestClient,
    valid_archetype: str,
) -> None:
    """All five enum values MUST be accepted by Pydantic Literal validation."""
    with (
        patch("src.discovery.get_discovery_service") as mock_disc,
        patch("src.event_bus.get_event_bus") as mock_bus_fn,
    ):
        mock_disc.return_value.heartbeat = AsyncMock()
        mock_bus = MagicMock()
        mock_bus.running = False
        mock_bus.failed = False
        mock_bus_fn.return_value = mock_bus

        response = client.post(
            "/status/report",
            json={
                "agent_id": "agent-1",
                "change_id": "c",
                "phase": "PLAN",
                "phase_archetype": valid_archetype,
            },
        )

    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "invalid_archetype",
    [
        "ADMIN",
        "wizard",
        "implementer; DROP TABLE agent_sessions",
        "  architect  ",
        "Architect",  # case-sensitive
        "implementers",  # close-but-not-quite
        "",  # empty string
    ],
)
def test_status_report_rejects_out_of_enum_phase_archetype_with_422(
    client: TestClient,
    invalid_archetype: str,
) -> None:
    """Pydantic ``Literal[...] | None`` MUST reject out-of-enum values with HTTP 422.

    Spec: "POST /status/report rejects out-of-enum phase_archetype values".
    The rejection MUST come from the API layer (Pydantic enum validation),
    independently of any database CHECK constraint, AND the agent_sessions
    row MUST remain unchanged because the heartbeat is never called.
    """
    mock_heartbeat = AsyncMock()
    with (
        patch("src.discovery.get_discovery_service") as mock_disc,
        patch("src.event_bus.get_event_bus") as mock_bus_fn,
    ):
        mock_disc.return_value.heartbeat = mock_heartbeat
        mock_bus = MagicMock()
        mock_bus.running = False
        mock_bus.failed = False
        mock_bus_fn.return_value = mock_bus

        response = client.post(
            "/status/report",
            json={
                "agent_id": "agent-1",
                "change_id": "c",
                "phase": "PLAN",
                "phase_archetype": invalid_archetype,
            },
        )

    assert response.status_code == 422, (
        f"Out-of-enum phase_archetype {invalid_archetype!r} MUST return 422; "
        f"got {response.status_code}: {response.text}"
    )
    # The persistence path MUST NOT have been reached.
    mock_heartbeat.assert_not_awaited()


def test_status_report_explicit_null_phase_archetype_is_accepted(
    client: TestClient,
) -> None:
    """``phase_archetype: null`` (explicit) MUST be accepted — it's the
    state-only INIT/SUBMIT_PR phase signature."""
    with (
        patch("src.discovery.get_discovery_service") as mock_disc,
        patch("src.event_bus.get_event_bus") as mock_bus_fn,
    ):
        mock_disc.return_value.heartbeat = AsyncMock()
        mock_bus = MagicMock()
        mock_bus.running = False
        mock_bus.failed = False
        mock_bus_fn.return_value = mock_bus

        response = client.post(
            "/status/report",
            json={
                "agent_id": "init-agent",
                "change_id": "c",
                "phase": "INIT",
                "phase_archetype": None,
            },
        )

    assert response.status_code == 200, response.text

"""End-to-end round-trip test: loop-state.json → POST /status/report → GET /discovery/agents.

Spec: openspec/changes/wire-autopilot-phase-subagents/specs/agent-coordinator/spec.md
Scenarios covered:
    - "AgentInfo round-trip via heartbeat and discovery"
    - "Status report with phase_archetype is persisted"
    - "report_status.py reads phase_archetype from loop-state.json"
Design decisions: D6 (status reporter wiring), D8 (AgentInfo persistence column).

Round-trip path validated end-to-end (in-process, hermetic):

    autopilot writes loop-state.json
        → report_status.py reads phase_archetype from loop-state.json
        → POST /status/report (FastAPI TestClient)
            → coordination_api.report_status forwards to DiscoveryService.heartbeat
                → (in this test) we then directly populate the DiscoveryService
                  for the discovery query (the agent_heartbeat RPC and
                  discover_agents RPC are exercised in isolation by
                  test_phase_archetype_migration.py against a real Postgres
                  container; this test uses an in-process stub to keep the
                  round-trip hermetic and validates the wiring contract).
        → GET /discovery/agents → response surfaces phase_archetype

This is the integration test referenced by task 4.2. The lower-level
slices are already covered:
    - test_status_report_persistence_wiring.py covers POST /status/report → heartbeat
    - test_phase_archetype_discovery_api.py covers GET /discovery/agents builder
    - test_report_status_phase_archetype.py covers report_status.py logic
This test stitches them together so a single ``phase_archetype`` value flows
from disk to the wire.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.coordination_api import create_coordination_api
from src.discovery import AgentInfo, DiscoverResult, HeartbeatResult

_TEST_KEY = "test-key-roundtrip"
_REPO_ROOT = Path(__file__).resolve().parents[2]


class _FakeResponse:
    """Minimal urlopen-shaped response used by tests below.

    Module-level so the three patched-urlopen call sites share one definition
    (closes SonarCloud duplication finding from PR #146 review).
    """

    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


def _make_fake_urlopen(client: TestClient) -> Any:
    """Build a urlopen replacement that proxies to a FastAPI TestClient.

    The closure exists because each test brings its own ``client`` instance;
    extracting the helper itself is enough to dedupe the body without
    forcing the test to thread the client through a global.
    """

    def _fake_urlopen(req: Any, timeout: float = 5.0) -> _FakeResponse:
        path = req.full_url.replace("http://testclient", "")
        body = req.data
        headers = dict(req.headers) if hasattr(req, "headers") else {}
        api_key = headers.get("X-api-key") or headers.get("X-API-Key")
        kwargs: dict[str, Any] = {"json": json.loads(body) if body else None}
        if api_key:
            kwargs["headers"] = {"X-API-Key": api_key}
        resp = client.post(path, **kwargs)
        return _FakeResponse(status=resp.status_code)

    return _fake_urlopen


@pytest.fixture()
def _api_config(monkeypatch: pytest.MonkeyPatch) -> Any:
    from tests.conftest import setup_api_config_env
    yield from setup_api_config_env(monkeypatch, _TEST_KEY)


@pytest.fixture()
def client(_api_config: None) -> TestClient:
    return TestClient(create_coordination_api())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_loop_state(
    cwd: Path,
    *,
    change_id: str,
    phase: str,
    phase_archetype: str | None,
) -> Path:
    """Write a minimal loop-state.json that report_status.py can read."""
    state = {
        "schema_version": 3,
        "change_id": change_id,
        "current_phase": phase,
        "phase_archetype": phase_archetype,
        "findings_trend": [],
    }
    path = cwd / "loop-state.json"
    path.write_text(json.dumps(state, indent=2) + "\n")
    return path


# ---------------------------------------------------------------------------
# Round-trip test
# ---------------------------------------------------------------------------


def test_phase_archetype_round_trips_from_loop_state_to_discovery_agents(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Full round-trip: loop-state.json → status/report → discovery/agents.

    This is the integration assertion that the entire chain agrees on the
    field name + serialization. Any one link breaking the contract (e.g.
    report_status.py renaming the field, the API dropping it, or the
    discovery handler not including it in the per-agent dict) fails this
    test.
    """
    # 1. Seed loop-state.json with phase_archetype="implementer".
    monkeypatch.chdir(tmp_path)
    _seed_loop_state(
        tmp_path,
        change_id="round-trip-demo",
        phase="IMPLEMENT",
        phase_archetype="implementer",
    )

    # 2. Capture the heartbeat call so we can verify the value reached
    #    DiscoveryService.heartbeat from the POST /status/report endpoint.
    heartbeat_calls: list[dict[str, Any]] = []

    async def _capture_heartbeat(**kwargs: Any) -> HeartbeatResult:
        heartbeat_calls.append(kwargs)
        return HeartbeatResult(success=True, session_id="sess-rt-1")

    # The API resolves get_discovery_service() lazily inside the route; we
    # patch the singleton accessor.
    from src import discovery
    captured_service = AsyncMock()
    captured_service.heartbeat = _capture_heartbeat  # type: ignore[assignment]
    captured_service.discover = AsyncMock(
        return_value=DiscoverResult(
            agents=[
                AgentInfo(
                    agent_id="autopilot-rt-1",
                    agent_type="claude_code",
                    session_id="sess-rt-1",
                    capabilities=["coding"],
                    status="active",
                    current_task="implement",
                    last_heartbeat=datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC),
                    started_at=datetime(2026, 5, 5, 11, 0, 0, tzinfo=UTC),
                    phase_archetype="implementer",
                )
            ]
        )
    )
    monkeypatch.setattr(discovery, "get_discovery_service", lambda: captured_service)

    # 3. Drive report_status.py against the test server. Run as a subprocess
    #    so we exercise its real CLI path (not in-process imports).
    monkeypatch.setenv("AGENT_ID", "autopilot-rt-1")
    monkeypatch.setenv("CHANGE_ID", "round-trip-demo")

    # Call report_status's main() in-process — TestClient is in this same
    # process, so we can't use a subprocess to talk to it. Instead, mock
    # urlopen at the report_status module level to dispatch into TestClient.
    sys.path.insert(0, str(_REPO_ROOT / "agent-coordinator" / "scripts"))
    import report_status  # type: ignore[import-not-found]

    monkeypatch.setenv("COORDINATION_API_URL", "http://testclient")
    monkeypatch.setenv("COORDINATION_API_KEY", _TEST_KEY)

    # Replace urlopen with a TestClient-routed shim. We also have to mock
    # event_bus to avoid asyncpg connection attempts.
    import contextlib
    from unittest.mock import MagicMock, patch

    _fake_urlopen = _make_fake_urlopen(client)

    with (
        patch.object(report_status, "urlopen", _fake_urlopen),
        patch("src.event_bus.get_event_bus") as mock_bus_fn,
    ):
        mock_bus = MagicMock()
        mock_bus.running = False
        mock_bus.failed = False
        mock_bus_fn.return_value = mock_bus

        # Run report_status.main(). Top-level guard swallows exceptions —
        # test still asserts on the captured heartbeat list and the GET
        # response.
        with contextlib.suppress(SystemExit):
            report_status.main()

    # 4. Verify the heartbeat received phase_archetype="implementer" through
    #    the entire stack (report_status → POST → coordination_api.report_status).
    assert len(heartbeat_calls) == 1, (
        f"expected exactly 1 heartbeat call from /status/report; got "
        f"{len(heartbeat_calls)}: {heartbeat_calls!r}"
    )
    assert heartbeat_calls[0].get("agent_id") == "autopilot-rt-1"
    assert heartbeat_calls[0].get("phase_archetype") == "implementer", (
        "phase_archetype must round-trip from loop-state.json through "
        "report_status.py → POST /status/report → DiscoveryService.heartbeat"
    )

    # 5. Now query GET /discovery/agents and assert phase_archetype is in
    #    the response. (The discover() call is mocked above to return an
    #    AgentInfo with phase_archetype="implementer" — this verifies the
    #    handler builder correctly serializes that field to the wire.)
    response = client.get("/discovery/agents")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["agents"], "discovery returned no agents"
    agent = body["agents"][0]
    assert "phase_archetype" in agent, (
        "GET /discovery/agents response MUST include phase_archetype on each agent"
    )
    assert agent["phase_archetype"] == "implementer"


def test_round_trip_with_null_phase_archetype_is_accepted(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Older-client path: loop-state.json has no phase_archetype → round-trip OK.

    This covers spec scenarios:
        - "Status report without phase_archetype is accepted"
        - "AgentInfo without phase_archetype defaults to None"
    """
    monkeypatch.chdir(tmp_path)
    _seed_loop_state(
        tmp_path,
        change_id="legacy-demo",
        phase="INIT",
        phase_archetype=None,
    )

    heartbeat_calls: list[dict[str, Any]] = []

    async def _capture_heartbeat(**kwargs: Any) -> HeartbeatResult:
        heartbeat_calls.append(kwargs)
        return HeartbeatResult(success=True)

    from src import discovery
    captured_service = AsyncMock()
    captured_service.heartbeat = _capture_heartbeat  # type: ignore[assignment]
    captured_service.discover = AsyncMock(
        return_value=DiscoverResult(
            agents=[
                AgentInfo(
                    agent_id="legacy-rt",
                    agent_type="codex",
                    session_id="sess-leg",
                    capabilities=[],
                    status="idle",
                    current_task=None,
                    last_heartbeat=datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC),
                    started_at=datetime(2026, 5, 5, 9, 0, 0, tzinfo=UTC),
                    phase_archetype=None,
                )
            ]
        )
    )
    monkeypatch.setattr(discovery, "get_discovery_service", lambda: captured_service)

    monkeypatch.setenv("AGENT_ID", "legacy-rt")
    monkeypatch.setenv("CHANGE_ID", "legacy-demo")

    sys.path.insert(0, str(_REPO_ROOT / "agent-coordinator" / "scripts"))
    import report_status  # type: ignore[import-not-found]

    monkeypatch.setenv("COORDINATION_API_URL", "http://testclient")
    monkeypatch.setenv("COORDINATION_API_KEY", _TEST_KEY)

    import contextlib
    from unittest.mock import MagicMock, patch

    _fake_urlopen = _make_fake_urlopen(client)

    with (
        patch.object(report_status, "urlopen", _fake_urlopen),
        patch("src.event_bus.get_event_bus") as mock_bus_fn,
    ):
        mock_bus = MagicMock()
        mock_bus.running = False
        mock_bus.failed = False
        mock_bus_fn.return_value = mock_bus

        with contextlib.suppress(SystemExit):
            report_status.main()

    assert len(heartbeat_calls) == 1, heartbeat_calls
    assert heartbeat_calls[0].get("phase_archetype") is None, (
        "phase_archetype absent in loop-state.json must round-trip as None"
    )

    response = client.get("/discovery/agents")
    assert response.status_code == 200
    agent = response.json()["agents"][0]
    assert agent["phase_archetype"] is None


def test_round_trip_drops_invalid_phase_archetype_at_client_layer(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local file tampering with phase_archetype must be dropped, not sent.

    Covers spec scenario:
        - "report_status.py drops invalid phase_archetype values from POST"

    This is the defense-in-depth assertion: even though the API rejects
    out-of-enum values with 422, report_status.py must NOT forward them in
    the first place (avoids polluting the audit log + 422 round-trip noise).
    """
    monkeypatch.chdir(tmp_path)
    _seed_loop_state(
        tmp_path,
        change_id="tamper-demo",
        phase="PLAN",
        phase_archetype="malicious_value",  # not in the allowed enum
    )

    heartbeat_calls: list[dict[str, Any]] = []

    async def _capture_heartbeat(**kwargs: Any) -> HeartbeatResult:
        heartbeat_calls.append(kwargs)
        return HeartbeatResult(success=True)

    from src import discovery
    captured_service = AsyncMock()
    captured_service.heartbeat = _capture_heartbeat  # type: ignore[assignment]
    monkeypatch.setattr(discovery, "get_discovery_service", lambda: captured_service)

    monkeypatch.setenv("AGENT_ID", "tamper-rt")
    monkeypatch.setenv("CHANGE_ID", "tamper-demo")

    sys.path.insert(0, str(_REPO_ROOT / "agent-coordinator" / "scripts"))
    import report_status  # type: ignore[import-not-found]

    monkeypatch.setenv("COORDINATION_API_URL", "http://testclient")
    monkeypatch.setenv("COORDINATION_API_KEY", _TEST_KEY)

    import contextlib
    from unittest.mock import MagicMock, patch

    _fake_urlopen = _make_fake_urlopen(client)

    with (
        patch.object(report_status, "urlopen", _fake_urlopen),
        patch("src.event_bus.get_event_bus") as mock_bus_fn,
    ):
        mock_bus = MagicMock()
        mock_bus.running = False
        mock_bus.failed = False
        mock_bus_fn.return_value = mock_bus

        with contextlib.suppress(SystemExit):
            report_status.main()

    # The tampered value must be dropped client-side; the heartbeat receives
    # phase_archetype=None (NOT "malicious_value").
    assert len(heartbeat_calls) == 1
    assert heartbeat_calls[0].get("phase_archetype") is None, (
        "report_status.py MUST drop invalid phase_archetype values "
        "(client-side defense in depth — task 3.10)"
    )

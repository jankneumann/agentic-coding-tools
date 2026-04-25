"""End-to-end integration test wiring all three packages of
add-per-phase-archetype-resolution together.

Exercises the path: phase_agent._build_options
    -> coordination_bridge.try_resolve_archetype_for_phase (HTTP)
    -> coordination_api.POST /archetypes/resolve_for_phase
    -> agents_config.resolve_archetype_for_phase
    -> response back through the chain.

We use FastAPI's TestClient as the HTTP server (no Docker needed) and
monkeypatch the bridge's _http_request to dispatch into the TestClient.
This validates that the wiring contracts agree without requiring the
live coordinator container.

Marked @pytest.mark.integration so it can be selected separately from
the unit suite.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

# Make the agent-coordinator src importable.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_COORD_ROOT = _REPO_ROOT / "agent-coordinator"
if str(_COORD_ROOT) not in sys.path:
    sys.path.insert(0, str(_COORD_ROOT))


pytestmark = pytest.mark.integration


@pytest.fixture()
def _api_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import reset_config

    reset_config()
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("COORDINATION_API_KEYS", "e2e-key")
    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")
    reset_config()
    yield  # type: ignore[misc]
    reset_config()


@pytest.fixture()
def coordinator_with_v2_archetypes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _api_config: None,
) -> Any:
    """Spin up a TestClient with a v2 archetypes.yaml loaded."""
    from fastapi.testclient import TestClient
    from src import agents_config
    from src.coordination_api import create_coordination_api

    archetypes_yaml = textwrap.dedent("""
        schema_version: 2
        archetypes:
          architect:
            model: opus
            system_prompt: "You are an architect."
          implementer:
            model: sonnet
            system_prompt: "You are an implementer."
            escalation:
              escalate_to: opus
              loc_threshold: 100
          reviewer:
            model: opus
            system_prompt: "You are a reviewer."
          runner:
            model: haiku
            system_prompt: "Execute and report."
        phase_mapping:
          PLAN:        {archetype: architect, signals: [capabilities_touched]}
          IMPLEMENT:   {archetype: implementer, signals: [loc_estimate]}
          IMPL_REVIEW: {archetype: reviewer}
          INIT:        {archetype: runner}
          SUBMIT_PR:   {archetype: runner}
    """).lstrip()
    yaml_path = tmp_path / "archetypes.yaml"
    yaml_path.write_text(archetypes_yaml)

    monkeypatch.setattr(
        agents_config, "_default_archetypes_path", lambda: yaml_path,
    )
    agents_config.reset_archetypes_config()
    return TestClient(create_coordination_api())


@pytest.fixture()
def bridge_routed_to_testclient(
    coordinator_with_v2_archetypes: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    """Re-route coordination_bridge._http_request through the TestClient."""
    import coordination_bridge

    client = coordinator_with_v2_archetypes

    def fake_http(*, method: str, path: str,
                  payload: dict[str, Any] | None = None,
                  http_url: str | None = None,
                  api_key: str | None = None,
                  timeout: float = 1.5,
                  ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if api_key:
            headers["X-API-Key"] = api_key
        if method.upper() == "POST":
            response = client.post(path, json=payload, headers=headers)
        else:
            response = client.get(path, headers=headers)
        try:
            data = response.json()
        except Exception:  # noqa: BLE001
            data = {"raw": response.text}
        return {"status_code": response.status_code, "data": data, "error": None}

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http)
    monkeypatch.setenv("COORDINATION_API_URL", "http://testclient")
    monkeypatch.setenv("COORDINATION_API_KEY", "e2e-key")
    return client


def test_e2e_plan_phase_resolves_to_architect(
    bridge_routed_to_testclient: Any,
) -> None:
    import phase_agent

    state_dict: dict[str, Any] = {"capabilities_touched": 3}
    options = phase_agent._build_options("PLAN", state_dict)

    assert options["model"] == "opus"
    assert "architect" in options["system_prompt"].lower()
    assert state_dict["_resolved_archetype"] == "architect"


def test_e2e_implement_escalates_via_loc_threshold(
    bridge_routed_to_testclient: Any,
) -> None:
    import phase_agent

    state_dict: dict[str, Any] = {"loc_estimate": 250}
    options = phase_agent._build_options("IMPLEMENT", state_dict)

    assert options["model"] == "opus"  # escalated from sonnet
    assert state_dict["_resolved_archetype"] == "implementer"


def test_e2e_unknown_phase_falls_back_to_harness_default(
    bridge_routed_to_testclient: Any,
) -> None:
    import phase_agent

    state_dict: dict[str, Any] = {}
    options = phase_agent._build_options("BOGUS_PHASE", state_dict)

    # Coordinator returns 404 -> bridge returns None -> options stays bare
    assert "model" not in options
    assert "system_prompt" not in options
    assert "_resolved_archetype" not in state_dict


def test_e2e_override_skips_bridge_and_system_prompt(
    bridge_routed_to_testclient: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import phase_agent

    monkeypatch.setenv("AUTOPILOT_PHASE_MODEL_OVERRIDE", "PLAN=haiku")
    state_dict: dict[str, Any] = {"capabilities_touched": 5}
    options = phase_agent._build_options("PLAN", state_dict)

    assert options["model"] == "haiku"
    assert "system_prompt" not in options
    assert "_resolved_archetype" not in state_dict


def test_e2e_status_report_round_trips_phase_archetype(
    coordinator_with_v2_archetypes: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /status/report accepts phase_archetype and returns 200."""
    from src import discovery

    class _StubDiscovery:
        async def heartbeat(self, *, agent_id: str) -> Any:
            from src.discovery import HeartbeatResult
            return HeartbeatResult(success=True)

    monkeypatch.setattr(discovery, "_discovery_service", _StubDiscovery())

    response = coordinator_with_v2_archetypes.post(
        "/status/report",
        json={
            "agent_id": "e2e-agent",
            "change_id": "e2e-change",
            "phase": "PLAN",
            "phase_archetype": "architect",
        },
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

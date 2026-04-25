"""Tests for per-phase archetype resolution: loader, function, endpoint.

Spec deltas:
- specs/agent-archetypes/spec.md
    - Per-Phase Archetype Mapping (loader)
    - Phase Archetype Resolution Function
    - Phase Archetype Resolution Endpoint Contract
- specs/agent-coordinator/spec.md
    - Phase Archetype Resolution Endpoint
    - Status Report Payload Phase Archetype Field

Contracts:
- contracts/openapi/v1.yaml#/paths/~1archetypes~1resolve_for_phase
- contracts/schemas/archetypes-config-v2.schema.json

Design decisions: D1, D2, D3, D7, D11.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.agents_config import (
    PhaseMappingEntry,
    ResolvedArchetype,
    get_archetype,
    get_phase_mapping,
    load_archetypes_config,
    reset_archetypes_config,
    resolve_archetype_for_phase,
    resolve_model,
)
from src.coordination_api import create_coordination_api

_TEST_KEY = "test-key-001"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _api_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch config so the API accepts our test key."""
    from src.config import reset_config

    reset_config()
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("COORDINATION_API_KEYS", _TEST_KEY)
    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")
    reset_config()
    yield  # type: ignore[misc]
    reset_config()


@pytest.fixture(autouse=True)
def _clean_archetypes_cache() -> None:
    """Ensure each test starts with a fresh archetypes cache."""
    reset_archetypes_config()
    yield
    reset_archetypes_config()


@pytest.fixture()
def client(_api_config: None) -> TestClient:
    return TestClient(create_coordination_api())


def _auth() -> dict[str, str]:
    return {"X-API-Key": _TEST_KEY}


def _write_yaml(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "archetypes.yaml"
    path.write_text(textwrap.dedent(content).lstrip())
    return path


_BASE_ARCHETYPES = """
schema_version: 2
archetypes:
  architect:
    model: opus
    system_prompt: |
      You are a software architect. Focus on cross-cutting concerns.
  implementer:
    model: sonnet
    system_prompt: |
      You are a focused implementer.
    escalation:
      escalate_to: opus
      loc_threshold: 100
  reviewer:
    model: opus
    system_prompt: |
      You are a code reviewer.
  runner:
    model: haiku
    system_prompt: |
      Execute and report.
"""


# ---------------------------------------------------------------------------
# 2.1 / agent-archetypes.1 — phase_mapping loader
# ---------------------------------------------------------------------------


def test_load_archetypes_with_phase_mapping(tmp_path: Path) -> None:
    yaml_text = _BASE_ARCHETYPES + textwrap.dedent("""
        phase_mapping:
          PLAN:
            archetype: architect
            signals: [capabilities_touched]
          IMPLEMENT:
            archetype: implementer
            signals: [loc_estimate, write_allow, dependencies, complexity]
          INIT:
            archetype: runner
    """)
    config_path = _write_yaml(tmp_path, yaml_text)

    archetypes = load_archetypes_config(config_path)
    mapping = get_phase_mapping()

    assert "architect" in archetypes
    assert isinstance(mapping["PLAN"], PhaseMappingEntry)
    assert mapping["PLAN"].archetype == "architect"
    assert mapping["PLAN"].signals == ["capabilities_touched"]
    assert mapping["IMPLEMENT"].signals == [
        "loc_estimate",
        "write_allow",
        "dependencies",
        "complexity",
    ]
    # signals defaults to [] when omitted
    assert mapping["INIT"].signals == []


def test_load_archetypes_legacy_v1_no_phase_mapping(tmp_path: Path) -> None:
    yaml_text = textwrap.dedent("""
        schema_version: 1
        archetypes:
          architect:
            model: opus
            system_prompt: "You are an architect."
    """)
    config_path = _write_yaml(tmp_path, yaml_text)

    archetypes = load_archetypes_config(config_path)
    mapping = get_phase_mapping()

    assert "architect" in archetypes
    assert mapping == {}


def test_load_archetypes_undefined_archetype_in_mapping(tmp_path: Path) -> None:
    yaml_text = _BASE_ARCHETYPES + textwrap.dedent("""
        phase_mapping:
          PLAN:
            archetype: nonexistent_archetype
    """)
    config_path = _write_yaml(tmp_path, yaml_text)

    with pytest.raises(ValueError) as exc_info:
        load_archetypes_config(config_path)

    msg = str(exc_info.value)
    assert "PLAN" in msg
    assert "nonexistent_archetype" in msg


def test_load_archetypes_unknown_phase_name_rejected(tmp_path: Path) -> None:
    yaml_text = _BASE_ARCHETYPES + textwrap.dedent("""
        phase_mapping:
          BOGUS_PHASE:
            archetype: architect
    """)
    config_path = _write_yaml(tmp_path, yaml_text)

    # JSON schema enforces the phase name enum, so this should raise during validate()
    with pytest.raises(Exception) as exc_info:  # noqa: PT011 — jsonschema or ValueError
        load_archetypes_config(config_path)
    assert "BOGUS_PHASE" in str(exc_info.value) or "enum" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# 2.4 / agent-archetypes.2 — resolve_archetype_for_phase
# ---------------------------------------------------------------------------


def _setup_default_mapping(tmp_path: Path) -> None:
    yaml_text = _BASE_ARCHETYPES + textwrap.dedent("""
        phase_mapping:
          PLAN:        {archetype: architect}
          IMPLEMENT:   {archetype: implementer, signals: [loc_estimate, write_allow, dependencies]}
          IMPL_REVIEW: {archetype: reviewer}
          INIT:        {archetype: runner}
    """)
    load_archetypes_config(_write_yaml(tmp_path, yaml_text))


def test_resolve_for_phase_known_returns_archetype(tmp_path: Path) -> None:
    _setup_default_mapping(tmp_path)

    result = resolve_archetype_for_phase("PLAN", {})

    assert isinstance(result, ResolvedArchetype)
    assert result.archetype == "architect"
    assert result.model == "opus"
    assert "architect" in result.system_prompt.lower()
    assert any(
        "phase=PLAN" in r and "architect" in r for r in result.reasons
    ), f"reasons missing phase->archetype trace: {result.reasons}"


def test_resolve_for_phase_unknown_raises_keyerror(tmp_path: Path) -> None:
    _setup_default_mapping(tmp_path)

    with pytest.raises(KeyError) as exc_info:
        resolve_archetype_for_phase("UNKNOWN_PHASE", {})
    assert "UNKNOWN_PHASE" in str(exc_info.value)


def test_resolve_for_phase_with_escalation_signals(tmp_path: Path) -> None:
    _setup_default_mapping(tmp_path)

    result = resolve_archetype_for_phase(
        "IMPLEMENT",
        {"loc_estimate": 250, "write_allow": ["src/api/**"], "dependencies": []},
    )

    assert result.archetype == "implementer"
    assert result.model == "opus"  # escalated from sonnet via loc_threshold=100
    assert any("loc_estimate" in r for r in result.reasons), (
        f"reasons missing loc_estimate trigger: {result.reasons}"
    )


def test_resolve_for_phase_signals_are_filtered_to_listed_keys(tmp_path: Path) -> None:
    """Signal keys not listed in the phase entry are silently dropped."""
    _setup_default_mapping(tmp_path)

    # IMPLEMENT lists [loc_estimate, write_allow, dependencies] — `complexity` not listed
    # so the explicit-complexity escalation should NOT fire.
    result = resolve_archetype_for_phase(
        "IMPLEMENT",
        {"complexity": "high"},
    )

    assert result.archetype == "implementer"
    assert result.model == "sonnet"  # not escalated, complexity was filtered out


def test_resolve_for_phase_no_escalation_records_default_reason(tmp_path: Path) -> None:
    _setup_default_mapping(tmp_path)

    result = resolve_archetype_for_phase("PLAN", {})

    # Architect has no escalation block; should fall through to default model
    assert result.model == "opus"
    assert any("phase=PLAN" in r for r in result.reasons)


def test_resolve_model_phase_kwarg_is_backward_compatible(tmp_path: Path) -> None:
    """Adding phase= to resolve_model must not change existing-call behavior."""
    _setup_default_mapping(tmp_path)
    archetype = get_archetype("implementer")
    assert archetype is not None

    # Without phase
    model_no_phase = resolve_model(archetype, {})
    # With phase
    model_with_phase = resolve_model(archetype, {}, phase="IMPLEMENT")

    assert model_no_phase == model_with_phase == "sonnet"


# ---------------------------------------------------------------------------
# 3.1 / agent-coordinator.1 — POST /archetypes/resolve_for_phase
# ---------------------------------------------------------------------------


def _patch_loader_with_default_mapping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Make load_archetypes_config use a tmp file with a known phase mapping."""
    from src import agents_config

    yaml_text = _BASE_ARCHETYPES + textwrap.dedent("""
        phase_mapping:
          PLAN:       {archetype: architect}
          IMPLEMENT:  {archetype: implementer, signals: [loc_estimate]}
          INIT:        {archetype: runner}
    """)
    config_path = _write_yaml(tmp_path, yaml_text)
    monkeypatch.setattr(
        agents_config,
        "_default_archetypes_path",
        lambda: config_path,
    )
    reset_archetypes_config()


def test_endpoint_resolve_for_phase_200(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_loader_with_default_mapping(monkeypatch, tmp_path)

    response = client.post(
        "/archetypes/resolve_for_phase",
        headers=_auth(),
        json={"phase": "PLAN", "signals": {}},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["archetype"] == "architect"
    assert body["model"] == "opus"
    assert "architect" in body["system_prompt"].lower()
    assert isinstance(body["reasons"], list) and len(body["reasons"]) >= 1


def test_endpoint_resolve_for_phase_with_escalation(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_loader_with_default_mapping(monkeypatch, tmp_path)

    response = client.post(
        "/archetypes/resolve_for_phase",
        headers=_auth(),
        json={"phase": "IMPLEMENT", "signals": {"loc_estimate": 250}},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["archetype"] == "implementer"
    assert body["model"] == "opus"  # escalated


def test_endpoint_resolve_for_phase_missing_phase_400(client: TestClient) -> None:
    response = client.post(
        "/archetypes/resolve_for_phase",
        headers=_auth(),
        json={"signals": {}},  # missing phase
    )

    assert response.status_code in (400, 422)  # FastAPI default is 422 for body validation


def test_endpoint_resolve_for_phase_no_api_key_401(client: TestClient) -> None:
    response = client.post(
        "/archetypes/resolve_for_phase",
        json={"phase": "PLAN", "signals": {}},
    )
    assert response.status_code == 401


def test_endpoint_resolve_for_phase_unknown_phase_404(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_loader_with_default_mapping(monkeypatch, tmp_path)

    response = client.post(
        "/archetypes/resolve_for_phase",
        headers=_auth(),
        json={"phase": "BOGUS", "signals": {}},
    )

    assert response.status_code == 404
    body = response.json()
    # Could be RFC 7807 problem or plain {"error": ...}; just look for the phase name
    assert "BOGUS" in str(body)


def test_endpoint_resolve_for_phase_audit_logged(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_loader_with_default_mapping(monkeypatch, tmp_path)

    captured: list[dict[str, Any]] = []

    from src import audit

    class _StubAuditService:
        async def log_operation(self, **kwargs: Any) -> Any:
            captured.append(kwargs)
            from src.audit import AuditResult
            return AuditResult(success=True)

    monkeypatch.setattr(audit, "_audit_service", _StubAuditService())

    response = client.post(
        "/archetypes/resolve_for_phase",
        headers=_auth(),
        json={"phase": "PLAN", "signals": {}},
    )
    assert response.status_code == 200, response.text

    # Find the audit entry for our operation
    matches = [c for c in captured if c.get("operation") == "resolve_archetype_for_phase"]
    assert matches, f"no resolve_archetype_for_phase audit entry in {captured}"
    entry = matches[0]
    assert entry.get("success") is True
    params = entry.get("parameters") or {}
    result = entry.get("result") or {}
    assert params.get("phase") == "PLAN"
    assert result.get("archetype") == "architect"
    assert result.get("model") == "opus"


# ---------------------------------------------------------------------------
# 4.3 / agent-coordinator.3 — POST /status/report accepts phase_archetype
# ---------------------------------------------------------------------------


def test_status_report_accepts_phase_archetype(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Avoid the discovery side-effect during the test.
    from src import discovery

    class _StubDiscovery:
        async def heartbeat(self, *, agent_id: str) -> Any:
            from src.discovery import HeartbeatResult
            return HeartbeatResult(success=True)

    monkeypatch.setattr(discovery, "_discovery_service", _StubDiscovery())

    response = client.post(
        "/status/report",
        json={
            "agent_id": "test-agent",
            "change_id": "demo-change",
            "phase": "PLAN",
            "phase_archetype": "architect",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True


def test_status_report_without_phase_archetype_is_accepted(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src import discovery

    class _StubDiscovery:
        async def heartbeat(self, *, agent_id: str) -> Any:
            from src.discovery import HeartbeatResult
            return HeartbeatResult(success=True)

    monkeypatch.setattr(discovery, "_discovery_service", _StubDiscovery())

    response = client.post(
        "/status/report",
        json={
            "agent_id": "older-agent",
            "change_id": "demo",
            "phase": "PLAN",
            # phase_archetype omitted (older client)
        },
    )

    assert response.status_code == 200, response.text

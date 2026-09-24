"""HTTP contract tests for exact-agent network export and sandbox audit."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src import coordination_api as api_module
from src.audit import AuditService, sandbox_endpoint_digest
from src.config import reset_config
from src.network_policies import NetworkPolicyExportError


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    reset_config()
    monkeypatch.setenv("COORDINATION_API_KEYS", "dispatcher-key")
    monkeypatch.setenv(
        "COORDINATION_API_KEY_IDENTITIES",
        '{"dispatcher-key":{"agent_id":"dispatch-host","agent_type":"codex"}}',
    )
    reset_config()
    return TestClient(api_module.create_coordination_api())


def _event(**changes):
    event = {
        "schema_version": 1,
        "event_id": str(uuid4()),
        "context_source": "agents_yaml",
        "decision_id": None,
        "item_id": None,
        "phase": None,
        "attempt": 1,
        "dispatch_work_id": None,
        "routing_context_digest": None,
        "workspace_content_digest": None,
        "agent_id": "codex-local",
        "vendor_type": "codex",
        "policy_vendor": "openai",
        "catalog_vendor": "openai",
        "assignment_location": "local",
        "execution_location": "local",
        "enforcement_scope": "execution",
        "write_capable": False,
        "dispatch_mode": "review",
        "model": "gpt-5.6-sol",
        "endpoint_kind": "openai",
        "endpoint_digest": "1" * 64,
        "requested_isolation": "sandbox",
        "sandbox_applied": False,
        "backend": "local-process",
        "runtime_version": None,
        "platform": "unsupported",
        "preflight_status": "unsupported_platform",
        "policy_revision": None,
        "policy_digest": None,
        "settings_digest": None,
        "worktree_root": None,
        "executable_paths": ["/usr/bin/codex"],
        "environment_keys": ["OPENAI_API_KEY"],
        "degradation_reason": "unsupported_platform",
        "cleanup_status": "not_started",
        "cleanup_residual_paths": [],
    }
    event.update(changes)
    return event


def test_policy_export_requires_cross_agent_trust_three(client, monkeypatch):
    monkeypatch.setattr(api_module, "resolve_trust_level", AsyncMock(return_value=2))
    response = client.get(
        "/policies/network/export?agent_id=codex-local", headers={"X-API-Key": "dispatcher-key"}
    )
    assert response.status_code == 403


def test_policy_export_maps_exact_agent_errors(client, monkeypatch):
    monkeypatch.setattr(api_module, "resolve_trust_level", AsyncMock(return_value=3))
    service = AsyncMock()
    service.export_for_agent.side_effect = NetworkPolicyExportError("agent_unassigned", 409)
    monkeypatch.setattr("src.network_policies.get_network_policy_service", lambda: service)
    response = client.get(
        "/policies/network/export?agent_id=missing", headers={"X-API-Key": "dispatcher-key"}
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "agent_unassigned"


def test_sandbox_event_binds_authenticated_actor_and_replays(client, monkeypatch):
    monkeypatch.setattr(api_module, "resolve_trust_level", AsyncMock(return_value=3))
    audit = AsyncMock()
    audit.record_sandbox_event.return_value = type(
        "Recorded", (), {"entry_id": "audit-1", "replayed": True}
    )()
    monkeypatch.setattr("src.audit.get_audit_service", lambda: audit)
    event = _event()
    response = client.post(
        "/dispatch/sandbox-events", headers={"X-API-Key": "dispatcher-key"}, json=event
    )
    assert response.status_code == 200
    kwargs = audit.record_sandbox_event.await_args.kwargs
    assert kwargs["actor_agent_id"] == "dispatch-host"
    assert kwargs["event"] == event
    assert response.json()["replayed"] is True


def test_sandbox_event_rejects_secret_or_truthful_cross_field_violation(client, monkeypatch):
    monkeypatch.setattr(api_module, "resolve_trust_level", AsyncMock(return_value=3))
    response = client.post(
        "/dispatch/sandbox-events",
        headers={"X-API-Key": "dispatcher-key"},
        json=_event(prompt="secret", sandbox_applied=True),
    )
    assert response.status_code == 422


def test_sandbox_event_rejects_untruthful_applied_fields(client, monkeypatch):
    monkeypatch.setattr(api_module, "resolve_trust_level", AsyncMock(return_value=3))
    response = client.post(
        "/dispatch/sandbox-events",
        headers={"X-API-Key": "dispatcher-key"},
        json=_event(sandbox_applied=True, degradation_reason=None),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_durable_audit_service_returns_idempotent_replay_identity():
    db = AsyncMock()
    db.rpc.return_value = {
        "success": True,
        "audit_entry_id": "audit-original",
        "replayed": True,
    }
    event = _event()
    result = await AuditService(db).record_sandbox_event(
        actor_agent_id="dispatch-host",
        event=event,
    )
    assert result.entry_id == "audit-original"
    assert result.replayed is True
    db.rpc.assert_awaited_once_with(
        "record_sandbox_execution_event",
        {"p_actor_agent_id": "dispatch-host", "p_event": event},
    )


def test_endpoint_digest_golden_parity_and_unsafe_url_rejection():
    assert sandbox_endpoint_digest("openai", None) == (
        "9f97e75b8bcf71a0319e60a437a2091cf801990a5cd7ebe591694a8635ef050f"
    )
    with pytest.raises(ValueError, match="userinfo"):
        sandbox_endpoint_digest("openai", "https://user:secret@example.com/v1")
    with pytest.raises(ValueError, match="fragment"):
        sandbox_endpoint_digest("openai", "https://example.com/v1#hidden")

"""Authenticated HTTP contract for the vendor registry."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import src.coordination_api as api_module
from src.config import reset_config
from src.vendor_registry import ObservationConflictError, UnknownVendorLaneError

_KEYS = ("bearer-key", "coordinator-key", "legacy-key")


@pytest.fixture()
def registry_client(monkeypatch: pytest.MonkeyPatch):
    identities = {
        key: {"agent_id": "dispatcher", "agent_type": "codex"}
        for key in _KEYS
    }
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("COORDINATION_API_KEYS", ",".join(_KEYS))
    monkeypatch.setenv(
        "COORDINATION_API_KEY_IDENTITIES", json.dumps(identities)
    )
    reset_config()

    registry = AsyncMock()
    registry.list_vendors.return_value = []
    registry.get_availability.return_value = {
        "agent_id": "dispatcher",
        "status": "available",
        "available": True,
        "reason": None,
        "source": "watchdog",
        "observed_at": "2026-09-16T12:00:00+00:00",
        "stale_after": "2026-09-16T12:02:00+00:00",
        "reset_at": None,
        "rate_limits": [],
    }
    registry.record_rate_limit.return_value = {
        "observation_id": "obs-1",
        "status": "accepted",
        "reset_at": "2026-09-16T12:15:00+00:00",
    }
    monkeypatch.setattr(
        api_module, "get_vendor_registry", lambda: registry, raising=False
    )
    client = TestClient(api_module.create_coordination_api())
    yield client, registry
    reset_config()


@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Bearer bearer-key"},
        {"X-Coordinator-API-Key": "coordinator-key"},
        {"X-API-Key": "legacy-key"},
    ],
)
def test_list_vendors_accepts_all_repository_auth_schemes(
    registry_client, headers: dict[str, str]
) -> None:
    client, registry = registry_client

    response = client.get(
        "/vendors",
        headers=headers,
        params={
            "capability": "queue",
            "archetype": "reviewer",
            "dispatch_mode": "review",
            "location": "cloud",
            "available_only": "true",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"vendors": []}
    registry.list_vendors.assert_awaited_with(
        capability="queue",
        archetype="reviewer",
        dispatch_mode="review",
        location="cloud",
        available_only=True,
    )


def test_availability_detail_is_authenticated(registry_client) -> None:
    client, registry = registry_client

    response = client.get(
        "/vendors/dispatcher/availability",
        headers={"X-API-Key": "legacy-key"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "available"
    registry.get_availability.assert_awaited_once_with("dispatcher")


def test_rate_limit_write_binds_source_to_authenticated_principal(
    registry_client,
) -> None:
    client, registry = registry_client

    response = client.post(
        "/vendors/dispatcher/rate-limit-observations",
        headers={"Authorization": "Bearer bearer-key"},
        json={"observation_id": "obs-1", "reason": "capacity"},
    )

    assert response.status_code == 202
    kwargs = registry.record_rate_limit.await_args.kwargs
    assert kwargs["source_agent_id"] == "dispatcher"
    assert kwargs["received_at"] is not None


def test_cross_lane_write_accepts_explicit_reporting_authority(
    registry_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, registry = registry_client
    authorize = AsyncMock()
    monkeypatch.setattr(api_module, "authorize_operation", authorize)

    response = client.post(
        "/vendors/other-lane/rate-limit-observations",
        headers={"X-Coordinator-API-Key": "coordinator-key"},
        json={"observation_id": "obs-1", "reason": "capacity"},
    )

    assert response.status_code == 202
    authorize.assert_awaited_once_with(
        agent_id="dispatcher",
        agent_type="codex",
        operation="report_vendor_rate_limit",
        resource="other-lane",
        context={"target_agent_id": "other-lane"},
    )
    registry.record_rate_limit.assert_awaited_once()

def test_trust_three_admin_can_report_cross_lane_without_reporter_capability(
    registry_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src import policy_engine, profiles, trust_resolution
    from src.agents_config import derive_allowed_operations
    from src.policy_engine import NativePolicyEngine
    from src.profiles import ProfilesService

    client, registry = registry_client
    profile_db = AsyncMock()
    profile_db.rpc.return_value = {
        "success": True,
        "source": "assignment",
        "profile": {
            "id": "profile-trust-three",
            "name": "trust_three_admin",
            "agent_type": "codex",
            "trust_level": 3,
            "allowed_operations": derive_allowed_operations(["lock"], trust_level=3),
            "enabled": True,
        },
    }
    monkeypatch.setattr(profiles, "_profiles_service", ProfilesService(profile_db))
    engine = NativePolicyEngine(AsyncMock())
    engine._log_policy_decision = AsyncMock()
    monkeypatch.setattr(policy_engine, "_policy_engine", engine)
    monkeypatch.setattr(
        trust_resolution, "resolve_trust_level", AsyncMock(return_value=3)
    )

    response = client.post(
        "/vendors/other-lane/rate-limit-observations",
        headers={"X-Coordinator-API-Key": "coordinator-key"},
        json={"observation_id": "obs-admin", "reason": "capacity"},
    )

    assert response.status_code == 202
    registry.record_rate_limit.assert_awaited_once()


def test_cross_lane_write_requires_reporting_authority(
    registry_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _registry = registry_client
    authorize = AsyncMock(
        side_effect=HTTPException(status_code=403, detail="operation_not_permitted")
    )
    monkeypatch.setattr(api_module, "authorize_operation", authorize)

    response = client.post(
        "/vendors/other-lane/rate-limit-observations",
        headers={"X-Coordinator-API-Key": "coordinator-key"},
        json={"observation_id": "obs-1", "reason": "capacity"},
    )

    assert response.status_code == 403
    authorize.assert_awaited_once()


@pytest.mark.parametrize(
    ("method", "path", "error", "status", "problem_type"),
    [
        (
            "get",
            "/vendors/missing/availability",
            UnknownVendorLaneError("missing"),
            404,
            "urn:vendor-registry:unknown-lane",
        ),
        (
            "post",
            "/vendors/dispatcher/rate-limit-observations",
            ObservationConflictError("obs-1"),
            409,
            "urn:vendor-registry:observation-conflict",
        ),
        (
            "get",
            "/vendors",
            RuntimeError("database unavailable"),
            503,
            "urn:vendor-registry:unavailable",
        ),
    ],
)
def test_registry_errors_are_rfc7807_problems(
    registry_client,
    method: str,
    path: str,
    error: Exception,
    status: int,
    problem_type: str,
) -> None:
    client, registry = registry_client
    if path == "/vendors":
        registry.list_vendors.side_effect = error
    elif method == "get":
        registry.get_availability.side_effect = error
    else:
        registry.record_rate_limit.side_effect = error

    kwargs = {"headers": {"X-API-Key": "legacy-key"}}
    if method == "post":
        kwargs["json"] = {"observation_id": "obs-1", "reason": "capacity"}
    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == problem_type
    assert response.json()["status"] == status


@pytest.mark.parametrize(
    "payload",
    [
        {
            "observation_id": "obs-1",
            "reason": "capacity",
            "reset_at": "2026-09-17T12:00:00Z",
            "retry_after_seconds": 60,
        },
        {
            "observation_id": "obs-1",
            "reason": "capacity",
            "scope": "model",
        },
        {
            "observation_id": "obs-1",
            "reason": "capacity",
            "metadata": {str(index): index for index in range(21)},
        },
        {
            "observation_id": "obs-1",
            "reason": "capacity",
            "unexpected": True,
        },
    ],
)
def test_invalid_observations_are_400_problems(registry_client, payload) -> None:
    client, registry = registry_client

    response = client.post(
        "/vendors/dispatcher/rate-limit-observations",
        headers={"X-API-Key": "legacy-key"},
        json=payload,
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    registry.record_rate_limit.assert_not_awaited()


def test_contract_maximum_reason_length_is_accepted(registry_client) -> None:
    client, registry = registry_client

    response = client.post(
        "/vendors/dispatcher/rate-limit-observations",
        headers={"X-API-Key": "legacy-key"},
        json={"observation_id": "obs-1", "reason": "x" * 2000},
    )

    assert response.status_code == 202
    assert registry.record_rate_limit.await_args.kwargs["reason"] == "x" * 2000

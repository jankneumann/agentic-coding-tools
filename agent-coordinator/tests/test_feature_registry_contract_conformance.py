"""Response conformance: the feature-registry HTTP API against its contract.

Every operation declared in ``openspec/contracts/agent-coordinator/openapi/features.yaml``
is driven through ``create_coordination_api()`` with a fake feature registry
service (no database), and each response body is validated with
``Draft202012Validator`` against the schema the *contract* declares for the
returned status code. The contract is the source of truth; the app's own
``openapi()`` document is never consulted here.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import jsonschema
import pytest
import yaml
from fastapi.testclient import TestClient
from gen_eval.openapi import iter_operations

from src.coordination_api import create_coordination_api
from src.feature_registry import (
    ConflictReport,
    DeregisterResult,
    Feasibility,
    Feature,
    RegisterResult,
)

_TEST_KEY = "test-key-001"
_CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "openspec"
    / "contracts"
    / "agent-coordinator"
    / "openapi"
    / "features.yaml"
)
_DOC: dict[str, Any] = yaml.safe_load(_CONTRACT.read_text())
_OPERATIONS = {op.raw["operationId"]: op for op in iter_operations(_DOC)}

_KNOWN_ID = "add-port-leases"
_ACTIVE_ONLY_ID = "only-active-on-register"


# --------------------------------------------------------------------------- #
# Contract helpers
# --------------------------------------------------------------------------- #


def _resolve(node: dict[str, Any]) -> dict[str, Any]:
    """Follow a local ``#/...`` $ref (e.g. components/responses/Unauthorized)."""
    while "$ref" in node:
        target: Any = _DOC
        for part in node["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        node = target
    return node


def _response_schema(operation_id: str, status: int) -> dict[str, Any] | None:
    responses = _OPERATIONS[operation_id].raw.get("responses") or {}
    declared = responses.get(str(status))
    assert declared is not None, (
        f"{operation_id}: app returned {status}, which the contract does not declare "
        f"(declared: {sorted(responses)})"
    )
    content = _resolve(declared).get("content") or {}
    schema = (content.get("application/json") or {}).get("schema")
    return schema if isinstance(schema, dict) else None


def _conformance_errors(
    operation_id: str, status: int, schema: dict[str, Any], body: Any
) -> list[str]:
    """Validate ``body`` against ``schema`` with the contract's components in scope."""
    root = {"$ref": schema["$ref"]} if "$ref" in schema else dict(schema)
    root["components"] = _DOC["components"]
    validator = jsonschema.Draft202012Validator(root)
    return [
        f"{operation_id} {status} at /{'/'.join(map(str, err.absolute_path))}: {err.message}"
        for err in validator.iter_errors(body)
    ]


def _assert_conforms(operation_id: str, response: httpx.Response) -> None:
    schema = _response_schema(operation_id, response.status_code)
    assert schema is not None, f"{operation_id} {response.status_code}: contract declares no schema"
    errors = _conformance_errors(operation_id, response.status_code, schema, response.json())
    assert not errors, "\n".join(errors)


# --------------------------------------------------------------------------- #
# Fake service and fixtures
# --------------------------------------------------------------------------- #


def _feature(feature_id: str) -> Feature:
    now = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)
    return Feature(
        feature_id=feature_id,
        title="Port leases",
        status="active",
        registered_by="claude-code-1",
        registered_at=now,
        updated_at=now,
        completed_at=None,
        resource_claims=["api:POST /ports/allocate", "db:schema:port_leases"],
        branch_name="openspec/standardize-port-leases",
        merge_priority=3,
        metadata={"source": "test"},
    )


class _FakeRegistry:
    """Covers success and failure shapes of FeatureRegistryService."""

    def __init__(self, features: list[Feature]) -> None:
        self._features = {f.feature_id: f for f in features}

    async def get_active_features(self) -> list[Feature]:
        return list(self._features.values())

    async def get_feature(self, feature_id: str) -> Feature | None:
        return self._features.get(feature_id)

    async def register(self, feature_id: str, **_: Any) -> RegisterResult:
        if feature_id == _ACTIVE_ONLY_ID:
            return RegisterResult(success=False, reason="feature_not_active")
        action = "updated" if feature_id in self._features else "registered"
        return RegisterResult(success=True, feature_id=feature_id, action=action)

    async def deregister(self, feature_id: str, status: str = "completed") -> DeregisterResult:
        if feature_id not in self._features:
            return DeregisterResult(success=False, reason="feature_not_found_or_not_active")
        return DeregisterResult(success=True, feature_id=feature_id, status=status)

    async def analyze_conflicts(
        self, candidate_feature_id: str, candidate_claims: list[str]
    ) -> ConflictReport:
        conflicts = [
            {
                "feature_id": f.feature_id,
                "overlapping_keys": sorted(set(f.resource_claims) & set(candidate_claims)),
            }
            for f in self._features.values()
            if set(f.resource_claims) & set(candidate_claims)
        ]
        conflicting = {k for c in conflicts for k in c["overlapping_keys"]}
        return ConflictReport(
            candidate_feature_id=candidate_feature_id,
            candidate_claims=candidate_claims,
            conflicts=conflicts,
            feasibility=Feasibility.PARTIAL if conflicts else Feasibility.FULL,
            total_candidate_claims=len(candidate_claims),
            total_conflicting_claims=len(conflicting),
        )


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


class _Api:
    """A TestClient plus a switch for the registry contents the fake serves."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch
        monkeypatch.setattr("src.coordination_api.authorize_operation", AsyncMock())
        self.client = TestClient(create_coordination_api())
        self.serve([_feature(_KNOWN_ID)])

    def serve(self, features: list[Feature]) -> TestClient:
        registry = _FakeRegistry(features)
        self._monkeypatch.setattr(
            "src.feature_registry.get_feature_registry_service", lambda: registry
        )
        return self.client


@pytest.fixture()
def api(_api_config: None, monkeypatch: pytest.MonkeyPatch) -> _Api:
    return _Api(monkeypatch)


def _auth() -> dict[str, str]:
    return {"X-API-Key": _TEST_KEY}


# --------------------------------------------------------------------------- #
# Drivers: one per contracted operation, each covering success + failure shapes
# --------------------------------------------------------------------------- #

Driver = Callable[[_Api], list[tuple[httpx.Response, int]]]


def _drive_list_active(api: _Api) -> list[tuple[httpx.Response, int]]:
    populated = api.client.get("/features/active", headers=_auth())
    empty = api.serve([]).get("/features/active", headers=_auth())
    return [(populated, 200), (empty, 200)]


def _drive_register(api: _Api) -> list[tuple[httpx.Response, int]]:
    def post(body: dict[str, Any]) -> httpx.Response:
        return api.client.post("/features/register", json=body, headers=_auth())

    return [
        (post({"feature_id": "new-feature", "resource_claims": ["x"]}), 200),
        (post({"feature_id": _KNOWN_ID, "resource_claims": ["x"]}), 200),
        (post({"feature_id": _ACTIVE_ONLY_ID, "resource_claims": []}), 200),
        (post({"resource_claims": "not-a-list"}), 422),
    ]


def _drive_deregister(api: _Api) -> list[tuple[httpx.Response, int]]:
    def post(body: dict[str, Any]) -> httpx.Response:
        return api.client.post("/features/deregister", json=body, headers=_auth())

    return [
        (post({"feature_id": _KNOWN_ID, "status": "cancelled"}), 200),
        (post({"feature_id": "unknown-feature"}), 200),
        (post({}), 422),
    ]


def _drive_get_feature(api: _Api) -> list[tuple[httpx.Response, int]]:
    return [
        (api.client.get(f"/features/{_KNOWN_ID}", headers=_auth()), 200),
        (api.client.get("/features/unknown-feature", headers=_auth()), 404),
    ]


_OVERLAPPING = {
    "candidate_feature_id": "add-usage-ledger",
    "candidate_claims": ["db:schema:port_leases", "x"],
}


def _drive_conflicts(api: _Api) -> list[tuple[httpx.Response, int]]:
    def post(body: dict[str, Any]) -> httpx.Response:
        return api.client.post("/features/conflicts", json=body, headers=_auth())

    partial = post(_OVERLAPPING)
    invalid = post({"candidate_feature_id": "x"})
    api.serve([])
    return [(partial, 200), (invalid, 422), (post(_OVERLAPPING), 200)]


_DRIVERS: dict[str, Driver] = {
    "listActiveFeatures": _drive_list_active,
    "registerFeature": _drive_register,
    "deregisterFeature": _drive_deregister,
    "getFeature": _drive_get_feature,
    "analyzeFeatureConflicts": _drive_conflicts,
}


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_every_contracted_operation_has_a_driver() -> None:
    assert set(_DRIVERS) == set(_OPERATIONS), (
        f"undriven: {sorted(set(_OPERATIONS) - set(_DRIVERS))}; "
        f"driven but not contracted: {sorted(set(_DRIVERS) - set(_OPERATIONS))}"
    )


def test_every_success_response_declares_a_schema() -> None:
    untyped = [
        f"{op_id} {status}"
        for op_id, op in _OPERATIONS.items()
        for status in (op.raw.get("responses") or {})
        if str(status).startswith("2") and _response_schema(op_id, int(status)) is None
    ]
    assert not untyped, f"success responses without a schema: {untyped}"


@pytest.mark.parametrize("operation_id", sorted(_DRIVERS))
def test_responses_conform_to_contract(operation_id: str, api: _Api) -> None:
    exchanges = _DRIVERS[operation_id](api)
    for response, expected in exchanges:
        assert response.status_code == expected, (
            f"{operation_id}: {response.status_code} {response.text}"
        )
        _assert_conforms(operation_id, response)
    declared_4xx = {
        s for s in (_OPERATIONS[operation_id].raw.get("responses") or {}) if s in {"404", "422"}
    }
    exercised = {str(code) for _, code in exchanges}
    assert declared_4xx <= exercised, (
        f"{operation_id}: declared {sorted(declared_4xx - exercised)} not exercised"
    )


@pytest.mark.parametrize(
    "operation_id", sorted(op for op, o in _OPERATIONS.items() if o.raw.get("security"))
)
def test_secured_operations_reject_missing_key(operation_id: str, api: _Api) -> None:
    op = _OPERATIONS[operation_id]
    path = op.path.replace("{feature_id}", _KNOWN_ID)
    response = api.client.request(
        op.method.upper(), path, json={} if op.method.lower() == "post" else None
    )
    assert response.status_code == 401, f"{operation_id}: {response.status_code} {response.text}"
    _assert_conforms(operation_id, response)


def test_list_active_features_serves_populated_and_empty_lists(api: _Api) -> None:
    rows = api.client.get("/features/active", headers=_auth()).json()["features"]
    assert [f["feature_id"] for f in rows] == [_KNOWN_ID]
    body = api.serve([]).get("/features/active", headers=_auth()).json()
    assert body["features"] == [] and body["count"] == 0


def test_conflicts_report_carries_partial_feasibility(api: _Api) -> None:
    body = api.client.post("/features/conflicts", json=_OVERLAPPING, headers=_auth()).json()
    assert body["feasibility"] == "PARTIAL"
    assert body["conflicts"] == [
        {"feature_id": _KNOWN_ID, "overlapping_keys": ["db:schema:port_leases"]}
    ]


def test_failure_results_carry_null_fields(api: _Api) -> None:
    registered = api.client.post(
        "/features/register",
        json={"feature_id": _ACTIVE_ONLY_ID, "resource_claims": []},
        headers=_auth(),
    ).json()
    assert registered == {
        "success": False,
        "feature_id": None,
        "action": None,
        "reason": "feature_not_active",
    }
    deregistered = api.client.post(
        "/features/deregister", json={"feature_id": "nope"}, headers=_auth()
    ).json()
    assert deregistered == {
        "success": False,
        "feature_id": None,
        "status": None,
        "reason": "feature_not_found_or_not_active",
    }


def test_drift_is_detected_and_named() -> None:
    """Self-test: the validator is not vacuous — a missing required property fails."""
    schema = _response_schema("registerFeature", 200)
    assert schema is not None
    drifted = {"success": False, "reason": "feature_not_active"}  # feature_id/action omitted
    errors = _conformance_errors("registerFeature", 200, schema, drifted)
    assert errors
    assert all(e.startswith("registerFeature 200") for e in errors)
    assert any("'feature_id' is a required property" in e for e in errors)
    assert any("'action' is a required property" in e for e in errors)

"""HTTP routing tests for the feature registry endpoints.

`GET /features/active` and `GET /features/{feature_id}` share a prefix. Starlette
matches routes in registration order, so if the parameterised route is registered
first it captures `/features/active` with `feature_id="active"` and answers 404.
The bridge's capability probe reads that 404 as "feature registry not deployed".
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.coordination_api import create_coordination_api
from src.feature_registry import Feature

_TEST_KEY = "test-key-001"


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
        resource_claims=["api:POST /ports/allocate"],
        branch_name="openspec/standardize-port-leases",
        merge_priority=3,
    )


class _FakeRegistry:
    def __init__(self, features: list[Feature]) -> None:
        self._features = {f.feature_id: f for f in features}

    async def get_active_features(self) -> list[Feature]:
        return list(self._features.values())

    async def get_feature(self, feature_id: str) -> Feature | None:
        return self._features.get(feature_id)


@pytest.fixture()
def client(_api_config: None, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    registry = _FakeRegistry([_feature("add-port-leases")])
    monkeypatch.setattr("src.feature_registry.get_feature_registry_service", lambda: registry)
    return TestClient(create_coordination_api())


def _auth() -> dict[str, str]:
    return {"X-API-Key": _TEST_KEY}


def test_list_active_features_is_not_shadowed_by_feature_id_route(client: TestClient) -> None:
    response = client.get("/features/active", headers=_auth())

    assert response.status_code == 200, response.text
    body = response.json()
    assert [f["feature_id"] for f in body["features"]] == ["add-port-leases"]
    assert body["count"] == 1
    assert body["truncated"] is False


def test_get_single_feature_still_routes_to_feature_id(client: TestClient) -> None:
    response = client.get("/features/add-port-leases", headers=_auth())

    assert response.status_code == 200, response.text
    assert response.json()["feature_id"] == "add-port-leases"


def test_unknown_feature_is_404(client: TestClient) -> None:
    response = client.get("/features/no-such-feature", headers=_auth())

    assert response.status_code == 404


def test_list_active_features_requires_api_key(client: TestClient) -> None:
    assert client.get("/features/active").status_code == 401

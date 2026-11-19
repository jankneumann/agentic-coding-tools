"""HTTP tests for the project-keyed gate projection (``/gates/*``).

The service is replaced by a fake so these tests pin the route layer: which
credential reaches which route, what each route asks the policy engine, and
how service refusals map to status codes. The service's own behaviour is
covered by ``tests/test_gate_projection_service.py``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import src.gate_projection
from src.config import reset_config
from src.coordination_api import create_coordination_api
from src.gate_projection import (
    GateNotDecidableError,
    GateNotFoundError,
    ProjectNotEnrolledError,
)

_TEST_KEY = "gate-test-key"
_PROJECT = "acme/api"
_GATE_ID = "0123456789abcdef"
_APPROVAL_ID = "11111111-1111-4111-8111-111111111111"


class FakeGateProjection:
    def __init__(self) -> None:
        self.replace_snapshot = AsyncMock(
            return_value={
                "success": True,
                "project": _PROJECT,
                "gate_count": 1,
                "digest": "d" * 64,
                "received_at": "2026-11-19T12:00:00+00:00",
            }
        )
        self.delete_snapshot = AsyncMock(
            return_value={"success": True, "project": _PROJECT, "deleted": True}
        )
        self.list_pending = AsyncMock(
            return_value={
                "generated_at": "2026-11-19T12:00:00+00:00",
                "gates": [],
                "projects": [],
            }
        )
        self.decide = AsyncMock(
            return_value={
                "success": True,
                "project": _PROJECT,
                "gate_id": _GATE_ID,
                "approval": {"request_id": _APPROVAL_ID, "status": "approved"},
            }
        )


@pytest.fixture()
def fake_service(monkeypatch: pytest.MonkeyPatch) -> FakeGateProjection:
    fake = FakeGateProjection()
    monkeypatch.setattr(src.gate_projection, "_gate_projection_service", fake)
    return fake


@pytest.fixture()
def authorize(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    # Captured by install_gate_projection_routes when the app is built.
    mock = AsyncMock()
    monkeypatch.setattr("src.coordination_api.authorize_operation", mock)
    return mock


@pytest.fixture()
def client(
    monkeypatch: pytest.MonkeyPatch, fake_service: FakeGateProjection, authorize: AsyncMock
) -> TestClient:
    monkeypatch.setenv("COORDINATION_API_KEYS", _TEST_KEY)
    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")
    reset_config()
    return TestClient(create_coordination_api())


def _key() -> dict[str, str]:
    return {"X-API-Key": _TEST_KEY}


def _gate(**updates: Any) -> dict[str, Any]:
    gate: dict[str, Any] = {
        "gate_id": _GATE_ID,
        "gate": "merge",
        "source": "checkpoint",
        "subject": "ri-01 add-thing",
    }
    gate.update(updates)
    return gate


def _snapshot(**updates: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "project": _PROJECT,
        "collected_at": "2026-11-19T11:59:00+00:00",
        "gates": [_gate()],
    }
    body.update(updates)
    return body


def _decision(**updates: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"project": _PROJECT, "gate_id": _GATE_ID, "decision": "approved"}
    body.update(updates)
    return body


_ROUTES = [
    ("post", "/gates/projection", {"json": _snapshot()}),
    ("delete", "/gates/projection", {"params": {"project": _PROJECT}}),
    ("get", "/gates/pending", {}),
    ("post", "/gates/decide", {"json": _decision()}),
]


# --------------------------------------------------------------------------- #
# Credentials and policy
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("method", "path", "kwargs"), _ROUTES)
def test_every_route_requires_the_api_key(
    client: TestClient,
    fake_service: FakeGateProjection,
    method: str,
    path: str,
    kwargs: dict[str, Any],
) -> None:
    response = client.request(method, path, **kwargs)

    assert response.status_code == 401
    for call in (
        fake_service.replace_snapshot,
        fake_service.delete_snapshot,
        fake_service.list_pending,
        fake_service.decide,
    ):
        call.assert_not_awaited()


@pytest.mark.parametrize(
    ("method", "path", "kwargs", "operation", "resource"),
    [
        (*_ROUTES[0], "request_approval", _PROJECT),
        (*_ROUTES[1], "request_approval", _PROJECT),
        (*_ROUTES[2], "check_approval", ""),
        (*_ROUTES[3], "request_approval", _PROJECT),
    ],
)
def test_every_route_asks_the_policy_engine(
    client: TestClient,
    authorize: AsyncMock,
    method: str,
    path: str,
    kwargs: dict[str, Any],
    operation: str,
    resource: str,
) -> None:
    response = client.request(method, path, headers=_key(), **kwargs)

    assert response.status_code == 200
    authorize.assert_awaited_once()
    assert authorize.await_args.kwargs["operation"] == operation
    assert authorize.await_args.kwargs["resource"] == resource


@pytest.mark.parametrize(("method", "path", "kwargs"), _ROUTES)
def test_a_policy_denial_stops_the_request_before_the_service(
    client: TestClient,
    fake_service: FakeGateProjection,
    authorize: AsyncMock,
    method: str,
    path: str,
    kwargs: dict[str, Any],
) -> None:
    authorize.side_effect = HTTPException(status_code=403, detail="Forbidden")

    response = client.request(method, path, headers=_key(), **kwargs)

    assert response.status_code == 403
    fake_service.replace_snapshot.assert_not_awaited()
    fake_service.delete_snapshot.assert_not_awaited()
    fake_service.list_pending.assert_not_awaited()
    fake_service.decide.assert_not_awaited()


# --------------------------------------------------------------------------- #
# POST /gates/projection
# --------------------------------------------------------------------------- #


def test_a_pushed_snapshot_reaches_the_service(
    client: TestClient, fake_service: FakeGateProjection
) -> None:
    response = client.post("/gates/projection", headers=_key(), json=_snapshot())

    assert response.status_code == 200
    assert response.json()["gate_count"] == 1
    snapshot = fake_service.replace_snapshot.await_args.args[0]
    assert snapshot.project == _PROJECT
    assert [g.gate_id for g in snapshot.gates] == [_GATE_ID]


def test_a_push_for_a_project_that_is_not_enrolled_is_forbidden(
    client: TestClient, fake_service: FakeGateProjection
) -> None:
    fake_service.replace_snapshot.side_effect = ProjectNotEnrolledError(_PROJECT)

    response = client.post("/gates/projection", headers=_key(), json=_snapshot())

    assert response.status_code == 403
    assert response.json()["detail"] == "Project not enrolled"


@pytest.mark.parametrize(
    "body",
    [
        _snapshot(project="not-a-project"),
        _snapshot(gates=[_gate(gate_id="XYZ")]),
        _snapshot(gates=[_gate(source="elsewhere")]),
        _snapshot(gates=[_gate(gate_id=f"{i:016x}") for i in range(501)]),
        {"project": _PROJECT, "gates": []},
    ],
)
def test_a_malformed_snapshot_is_rejected_whole(
    client: TestClient, fake_service: FakeGateProjection, body: dict[str, Any]
) -> None:
    response = client.post("/gates/projection", headers=_key(), json=body)

    assert response.status_code == 422
    fake_service.replace_snapshot.assert_not_awaited()


# --------------------------------------------------------------------------- #
# DELETE /gates/projection
# --------------------------------------------------------------------------- #


def test_delete_names_the_project_in_the_query(
    client: TestClient, fake_service: FakeGateProjection
) -> None:
    response = client.delete(
        "/gates/projection", headers=_key(), params={"project": _PROJECT}
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "project": _PROJECT, "deleted": True}
    fake_service.delete_snapshot.assert_awaited_once_with(_PROJECT)


def test_delete_for_a_project_that_is_not_enrolled_is_forbidden(
    client: TestClient, fake_service: FakeGateProjection
) -> None:
    fake_service.delete_snapshot.side_effect = ProjectNotEnrolledError(_PROJECT)

    response = client.delete(
        "/gates/projection", headers=_key(), params={"project": _PROJECT}
    )

    assert response.status_code == 403


def test_delete_rejects_a_value_that_is_not_a_project(
    client: TestClient, fake_service: FakeGateProjection
) -> None:
    response = client.delete(
        "/gates/projection", headers=_key(), params={"project": "x)&digest=eq.1"}
    )

    assert response.status_code == 422
    fake_service.delete_snapshot.assert_not_awaited()


# --------------------------------------------------------------------------- #
# GET /gates/pending
# --------------------------------------------------------------------------- #


def test_the_listing_is_returned_as_the_service_built_it(
    client: TestClient, fake_service: FakeGateProjection
) -> None:
    response = client.get("/gates/pending", headers=_key())

    assert response.status_code == 200
    assert response.json() == fake_service.list_pending.return_value


# --------------------------------------------------------------------------- #
# POST /gates/decide
# --------------------------------------------------------------------------- #


def test_a_decision_is_attributed_to_the_caller_by_default(
    client: TestClient, fake_service: FakeGateProjection
) -> None:
    response = client.post("/gates/decide", headers=_key(), json=_decision())

    assert response.status_code == 200
    assert response.json()["approval"] == {"request_id": _APPROVAL_ID, "status": "approved"}
    decided_by = fake_service.decide.await_args.kwargs["decided_by"]
    assert decided_by and decided_by != "operator-1"


def test_a_decision_can_name_who_decided(
    client: TestClient, fake_service: FakeGateProjection
) -> None:
    response = client.post(
        "/gates/decide", headers=_key(), json=_decision(decided_by="operator-1")
    )

    assert response.status_code == 200
    assert fake_service.decide.await_args.kwargs["decided_by"] == "operator-1"


def test_a_gate_that_is_not_listed_is_not_found(
    client: TestClient, fake_service: FakeGateProjection
) -> None:
    fake_service.decide.side_effect = GateNotFoundError("acme/api 0123")

    response = client.post("/gates/decide", headers=_key(), json=_decision())

    assert response.status_code == 404
    assert response.json()["detail"] == "Gate not found"


def test_a_gate_the_coordinator_cannot_decide_says_where_to_answer_it(
    client: TestClient, fake_service: FakeGateProjection
) -> None:
    fake_service.decide.side_effect = GateNotDecidableError(
        "no_approval_request", "cycle_state.py gate-answer --gate merge"
    )

    response = client.post("/gates/decide", headers=_key(), json=_decision())

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "reason": "no_approval_request",
        "answer_hint": "cycle_state.py gate-answer --gate merge",
    }


def test_a_decision_for_a_project_that_is_not_enrolled_is_forbidden(
    client: TestClient, fake_service: FakeGateProjection
) -> None:
    fake_service.decide.side_effect = ProjectNotEnrolledError(_PROJECT)

    response = client.post("/gates/decide", headers=_key(), json=_decision())

    assert response.status_code == 403


@pytest.mark.parametrize(
    "body", [_decision(decision="rejected"), _decision(gate_id="nope"), {"project": _PROJECT}]
)
def test_a_malformed_decision_is_rejected(
    client: TestClient, fake_service: FakeGateProjection, body: dict[str, Any]
) -> None:
    response = client.post("/gates/decide", headers=_key(), json=body)

    assert response.status_code == 422
    fake_service.decide.assert_not_awaited()

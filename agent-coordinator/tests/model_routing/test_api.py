"""Contract tests for the model-routing HTTP and MCP surfaces."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from src.config import reset_config
from src.coordination_api import create_coordination_api
from src.model_routing.api import RoutingService, RoutingUnavailableError

_TEST_KEY = "routing-test-key"


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    reset_config()
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("COORDINATION_API_KEYS", _TEST_KEY)
    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")
    reset_config()
    yield TestClient(create_coordination_api())
    reset_config()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_TEST_KEY}"}


def _selection() -> dict[str, Any]:
    return {
        "decision_id": "3f1b7c1e-9a3d-4f9d-8b1a-2c6e5d4a9b0c",
        "selected": {
            "vendor": "local",
            "model": "qwen3-coder-32b",
            "endpoint_kind": "local",
            "score": 0.66,
        },
        "alternatives": [],
        "exploration": False,
        "fallback": False,
        "excluded": [],
    }


def test_all_five_routing_routes_are_registered(client: TestClient) -> None:
    paths = {route.path for route in client.app.routes if hasattr(route, "path")}
    assert {
        "/routing/select_model",
        "/routing/catalog",
        "/routing/decisions/{decision_id}",
        "/routing/usage",
        "/routing/feedback",
    } <= paths


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/routing/select_model", {"task_signals": {"archetype": "runner"}}),
        ("GET", "/routing/catalog", None),
        ("GET", "/routing/decisions/3f1b7c1e-9a3d-4f9d-8b1a-2c6e5d4a9b0c", None),
        ("GET", "/routing/usage", None),
        (
            "POST",
            "/routing/feedback",
            {
                "source": "validation",
                "vendor": "local",
                "model": "qwen",
                "task_type": "runner/low",
                "metrics": {"success": True},
            },
        ),
    ],
)
def test_routing_routes_require_bearer_auth(
    client: TestClient, method: str, path: str, body: dict[str, Any] | None
) -> None:
    response = client.request(method, path, json=body)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API key"}


def test_select_model_returns_contract_shape(client: TestClient) -> None:
    service = AsyncMock()
    service.select_model.return_value = _selection()

    with patch("src.model_routing.api.get_routing_service", return_value=service):
        response = client.post(
            "/routing/select_model",
            headers=_auth_headers(),
            json={
                "task_signals": {
                    "archetype": "implementer",
                    "phase": "IMPLEMENT",
                    "complexity": "high",
                },
                "objective_profile": "quality-first",
                "allow_exploration": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision_id"] == _selection()["decision_id"]
    assert payload["selected"]["model"] == "qwen3-coder-32b"
    assert payload["fallback"] is False
    request = service.select_model.await_args.args[0]
    assert request.task_signals.complexity == "high"
    assert request.objective_profile == "quality-first"


def test_select_model_requires_task_signal_archetype(client: TestClient) -> None:
    response = client.post(
        "/routing/select_model",
        headers=_auth_headers(),
        json={"task_signals": {"phase": "IMPLEMENT"}},
    )

    assert response.status_code == 422


def test_select_model_maps_no_candidate_to_documented_503(client: TestClient) -> None:
    service = AsyncMock()
    service.select_model.side_effect = RoutingUnavailableError("no feasible candidate")

    with patch("src.model_routing.api.get_routing_service", return_value=service):
        response = client.post(
            "/routing/select_model",
            headers=_auth_headers(),
            json={"task_signals": {"archetype": "runner"}},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "no feasible candidate"}


def test_catalog_filters_without_external_refresh(client: TestClient) -> None:
    service = AsyncMock()
    service.list_catalog.return_value = [
        {
            "vendor": "local",
            "model": "qwen",
            "endpoint_kind": "local",
            "available": True,
            "refreshed_at": "2026-09-16T00:00:00Z",
            "stale": False,
        }
    ]

    with patch("src.model_routing.api.get_routing_service", return_value=service):
        response = client.get(
            "/routing/catalog?endpoint_kind=local&available_only=true",
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    assert response.json()[0]["model"] == "qwen"
    service.list_catalog.assert_awaited_once_with(
        endpoint_kind="local", available_only=True
    )


def test_decision_not_found_is_404_problem(client: TestClient) -> None:
    service = AsyncMock()
    service.get_decision.return_value = None
    decision_id = UUID("3f1b7c1e-9a3d-4f9d-8b1a-2c6e5d4a9b0c")

    with patch("src.model_routing.api.get_routing_service", return_value=service):
        response = client.get(
            f"/routing/decisions/{decision_id}", headers=_auth_headers()
        )

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 404


def test_usage_and_feedback_delegate_to_service(client: TestClient) -> None:
    service = AsyncMock()
    service.get_usage.return_value = {
        "window": "week",
        "by_model": [],
        "net_savings_usd": 1.25,
        "net_savings_usd_excluding_estimates": 1.0,
        "exploration_usd_used": 0.0,
        "metered_ceiling_usd": 0.0,
        "metered_usd_used": 2.0,
    }
    service.post_feedback.return_value = {"accepted": True}
    feedback = {
        "source": "validation",
        "vendor": "local",
        "model": "qwen",
        "task_type": "runner/low",
        "metrics": {"success": True, "cost_observed_usd": 0.0},
    }

    with patch("src.model_routing.api.get_routing_service", return_value=service):
        usage = client.get(
            "/routing/usage?window=week&include_estimates=false",
            headers=_auth_headers(),
        )
        accepted = client.post(
            "/routing/feedback", headers=_auth_headers(), json=feedback
        )

    assert usage.status_code == 200
    assert usage.json()["window"] == "week"
    assert usage.json()["estimated_fraction"] == 0.0
    service.get_usage.assert_awaited_once_with(
        window="week", include_estimates=False
    )
    assert accepted.status_code == 202
    assert accepted.json() == {"accepted": True}
    assert service.post_feedback.await_args.args[0].task_type == "runner/low"


@pytest.mark.asyncio
async def test_routing_service_forwards_usage_window_and_reports_verified_savings() -> None:
    ledger = AsyncMock()
    ledger.usage_summary.return_value = {
        "actual_usd": 3.0,
        "counterfactual_usd": 10.0,
        "savings_usd": 7.0,
        "verified_savings_usd": 3.0,
        "estimated_entries": 1,
        "entries": 2,
    }
    service = RoutingService(catalog=AsyncMock(), ledger=ledger)

    usage = await service.get_usage(window="week", include_estimates=True)

    ledger.usage_summary.assert_awaited_once_with(
        window="week", include_estimated=True
    )
    assert usage["net_savings_usd"] == pytest.approx(7.0)
    assert usage["net_savings_usd_excluding_estimates"] == pytest.approx(3.0)
    assert usage["estimated_fraction"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_usage_tolerates_malformed_monthly_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROUTING_MONTHLY_CEILING_USD", "not-a-number")
    ledger = AsyncMock()
    ledger.usage_summary.return_value = {"entries": 0}

    usage = await RoutingService(catalog=AsyncMock(), ledger=ledger).get_usage(
        window="month", include_estimates=True
    )

    assert usage["metered_ceiling_usd"] == 0.0


@pytest.mark.asyncio
async def test_mcp_select_model_uses_same_service_in_db_mode() -> None:
    from src import coordination_mcp

    service = AsyncMock()
    service.select_model.return_value = _selection()

    with (
        patch.object(coordination_mcp, "_transport", "db"),
        patch("src.model_routing.api.get_routing_service", return_value=service),
    ):
        result = await coordination_mcp.select_model_for_task(
            task_signals={"archetype": "runner", "phase": "INIT"},
            objective_profile="balanced",
            allow_exploration=False,
        )

    assert result == _selection()
    assert service.select_model.await_args.args[0].task_signals.phase == "INIT"


@pytest.mark.asyncio
async def test_mcp_no_candidate_matches_http_proxy_error_semantics() -> None:
    from src import coordination_mcp

    expected = {
        "success": False,
        "error": "http_503",
        "status_code": 503,
        "detail": {"detail": "no feasible model-routing candidate"},
    }
    service = AsyncMock()
    service.select_model.side_effect = RoutingUnavailableError(
        "no feasible model-routing candidate"
    )

    with (
        patch.object(coordination_mcp, "_transport", "db"),
        patch("src.model_routing.api.get_routing_service", return_value=service),
    ):
        direct = await coordination_mcp.select_model_for_task(
            task_signals={"archetype": "runner"}
        )

    with (
        patch.object(coordination_mcp, "_transport", "http"),
        patch(
            "src.coordination_mcp.http_proxy.proxy_select_model_for_task",
            new=AsyncMock(return_value=expected),
        ),
    ):
        proxied = await coordination_mcp.select_model_for_task(
            task_signals={"archetype": "runner"}
        )

    assert direct == proxied == expected


@pytest.mark.asyncio
async def test_mcp_select_model_uses_http_proxy_in_proxy_mode() -> None:
    from src import coordination_mcp

    with (
        patch.object(coordination_mcp, "_transport", "http"),
        patch(
            "src.coordination_mcp.http_proxy.proxy_select_model_for_task",
            new=AsyncMock(return_value=_selection()),
        ) as proxy,
    ):
        result = await coordination_mcp.select_model_for_task(
            task_signals={"archetype": "runner"},
            weight_overrides={"w_quality": 1.0, "w_cost": 0.0, "w_latency": 0.0},
        )

    assert result == _selection()
    proxy.assert_awaited_once_with(
        task_signals={"archetype": "runner"},
        objective_profile=None,
        weight_overrides={"w_quality": 1.0, "w_cost": 0.0, "w_latency": 0.0},
        allow_exploration=True,
    )

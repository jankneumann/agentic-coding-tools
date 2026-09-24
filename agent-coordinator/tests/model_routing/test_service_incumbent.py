"""Service/API coverage for incumbent retention (retain-static-model-until-routing-evidence).

Covers task 4.1: request ``incumbent``, the ``ROUTING_INCUMBENT_MARGIN`` knob,
``retention`` on the response and persisted decision, null ``selected`` for
catalog-less retention, and evidenced-only exploration at the service seam.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from openspec_paths import change_dir, repo_root_from

from src.config import reset_config
from src.coordination_api import create_coordination_api
from src.model_routing.api import RoutingService, SelectModelRequest
from src.model_routing.resolver import CandidateInput

_RECORD_SCHEMA = (
    change_dir(repo_root_from(__file__, 3), "retain-static-model-until-routing-evidence")
    / "contracts"
    / "events"
    / "routing-decision-record.schema.json"
)
_INCUMBENT = {"vendor": "claude_code", "model": "fable"}


class _AlwaysExplore:
    """Deterministic rng stub: every epsilon draw explores, picking index 1."""

    def random(self) -> float:
        return 0.0

    def randrange(self, start: int, stop: int) -> int:
        return start


def _cand(vendor: str, model: str, prior: float = 0.0, **kw: Any) -> CandidateInput:
    return CandidateInput(
        vendor=vendor, model=model, endpoint_kind="vendor-cli", benchmark_prior=prior, **kw
    )


def _plain_service(candidates: list[CandidateInput], rng: Any = None) -> tuple[RoutingService, Any]:
    catalog = AsyncMock()
    catalog.list_candidates.return_value = candidates
    catalog.record_decision.return_value = {}
    ledger = AsyncMock()
    ledger.usage_summary.return_value = {}
    return RoutingService(catalog=catalog, ledger=ledger, rng=rng), catalog


def _request(incumbent: dict[str, Any] | None = _INCUMBENT, **kw: Any) -> SelectModelRequest:
    body: dict[str, Any] = {"task_signals": {"archetype": "architect"}, **kw}
    if incumbent is not None:
        body["incumbent"] = incumbent
    return SelectModelRequest(**body)


# ── request shape ────────────────────────────────────────────────────────────

def test_request_accepts_incumbent_with_null_vendor() -> None:
    request = _request({"vendor": None, "model": "premium"})
    assert request.incumbent is not None
    assert request.incumbent.vendor is None


def test_request_rejects_unknown_incumbent_fields() -> None:
    with pytest.raises(ValueError):
        _request({"vendor": "claude_code", "model": "fable", "endpoint_kind": "vendor-cli"})


# ── plain (dg-00) path ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_incumbent_keeps_prior_behavior_and_omits_retention() -> None:
    service, catalog = _plain_service(
        [_cand("antigravity", "gemini-3.6-flash-low"), _cand("claude_code", "fable")]
    )
    result = await service.select_model(_request(None, allow_exploration=False))

    assert result["selected"]["vendor"] == "antigravity"  # today's tie-break, unchanged
    assert "retention" not in result
    assert "retention" not in catalog.record_decision.await_args.args[0]


@pytest.mark.asyncio
async def test_empty_evidence_keeps_incumbent_and_persists_reason(monkeypatch) -> None:
    monkeypatch.delenv("ROUTING_INCUMBENT_MARGIN", raising=False)
    service, catalog = _plain_service(
        [_cand("antigravity", "gemini-3.6-flash-low"), _cand("claude_code", "fable")]
    )
    result = await service.select_model(_request(allow_exploration=False))

    assert result["selected"]["model"] == "fable"
    assert result["retention"] == {
        "retained": True,
        "reason": "no-evidence",
        "margin": 0.05,
        "incumbent_score": result["selected"]["score"],
    }
    persisted = catalog.record_decision.await_args.args[0]
    assert persisted["retention"] == result["retention"]
    assert persisted["request"]["incumbent"] == _INCUMBENT


@pytest.mark.parametrize(
    ("env", "expected_reason"),
    [
        (None, "challenger-evidenced-above-margin"),  # default 0.05 < 0.3 lead
        ("0.4", "below-margin"),
        ("-1", "challenger-evidenced-above-margin"),  # negative → default
        ("not-a-number", "challenger-evidenced-above-margin"),
    ],
)
@pytest.mark.asyncio
async def test_margin_knob_is_read_server_side(monkeypatch, env, expected_reason) -> None:
    if env is None:
        monkeypatch.delenv("ROUTING_INCUMBENT_MARGIN", raising=False)
    else:
        monkeypatch.setenv("ROUTING_INCUMBENT_MARGIN", env)
    # Challenger lead: 0.6 * 0.5 = 0.3 on the balanced profile.
    service, _ = _plain_service([_cand("claude_code", "fable"), _cand("codex", "terra", 0.5)])
    result = await service.select_model(_request(allow_exploration=False))
    assert result["retention"]["reason"] == expected_reason


@pytest.mark.asyncio
async def test_unresolved_incumbent_persists_null_selection() -> None:
    service, catalog = _plain_service([_cand("codex", "terra", 0.9)])
    result = await service.select_model(
        _request({"vendor": None, "model": "premium"}, allow_exploration=False)
    )

    assert result["selected"] is None
    assert result["retention"]["reason"] == "incumbent-unresolved"
    persisted = catalog.record_decision.await_args.args[0]
    assert persisted["selected"] is None
    assert persisted["retention"]["retained"] is True


@pytest.mark.asyncio
async def test_all_infeasible_with_incumbent_does_not_raise() -> None:
    service, catalog = _plain_service(
        [_cand("claude_code", "fable", available=False), _cand("codex", "terra", available=False)]
    )
    result = await service.select_model(_request(allow_exploration=False))

    assert result["selected"] is None
    assert result["retention"]["reason"] == "incumbent-infeasible-no-evidenced-alternative"
    catalog.record_decision.assert_awaited_once()


@pytest.mark.asyncio
async def test_exploration_is_inert_on_an_empty_catalog_with_an_incumbent() -> None:
    candidates = [
        _cand("antigravity", "gemini-3.6-flash-low"),
        _cand("claude_code", "fable"),
        _cand("codex", "terra"),
    ]
    held, _ = _plain_service(candidates, rng=_AlwaysExplore())
    unheld, _ = _plain_service(candidates, rng=_AlwaysExplore())

    with_incumbent = await held.select_model(_request())
    without_incumbent = await unheld.select_model(_request(None))

    assert without_incumbent["exploration"] is True  # today's behavior
    assert with_incumbent["exploration"] is False
    assert with_incumbent["selected"]["model"] == "fable"


@pytest.mark.asyncio
async def test_evidenced_exploration_records_its_reason() -> None:
    service, _ = _plain_service(
        [_cand("claude_code", "fable"), _cand("codex", "terra", 0.02), _cand("grok", "g5", 0.01)],
        rng=_AlwaysExplore(),
    )
    result = await service.select_model(_request())

    assert result["exploration"] is True
    assert result["selected"]["model"] in {"terra", "g5"}
    assert result["retention"]["retained"] is False
    assert result["retention"]["reason"] == "exploration-evidenced"


# ── assignment (dg-04) path ──────────────────────────────────────────────────

def _assignment_service(model: str) -> tuple[RoutingService, Any]:
    catalog = AsyncMock()
    catalog.list_candidates.return_value = [_cand("codex", model, 0.8)]
    catalog.record_decision_and_audit.return_value = {}
    registry = AsyncMock()
    registry.list_vendors.return_value = [
        {
            "agent_id": "codex-local",
            "vendor_type": "codex",
            "policy_vendor": "codex",
            "catalog_vendor": "codex",
            "location": "local",
            "isolation": "worktree",
            "archetypes": ["architect"],
            "dispatch_modes": ["quick"],
            "dispatchable": True,
            "availability": {"available": True, "rate_limits": []},
            "cost": {
                "models": [
                    {
                        "catalog_vendor": "codex",
                        "model": model,
                        "endpoint_kind": "vendor-cli",
                        "base_url": None,
                        "available": True,
                    }
                ]
            },
        }
    ]
    policy = MagicMock()
    policy.version = "dg04-v1"
    policy.checksum = "a" * 64
    policy.evaluate.return_value = MagicMock(
        location=None,
        isolation=None,
        dispatch_mode="quick",
        matched_rule_ids=(),
        rationale=("default:dispatch_mode=quick",),
    )
    service = RoutingService(
        catalog=catalog, ledger=AsyncMock(), registry=registry, policy=policy
    )
    return service, catalog


@pytest.mark.asyncio
async def test_assignment_path_persists_catalogless_retention_against_v12_schema() -> None:
    service, catalog = _assignment_service("gpt-5.6-terra")
    result = await service.select_model(
        _request({"vendor": None, "model": "premium"}, allow_exploration=False)
    )

    assert result["selected"] is None
    assert result["assignment"] is None
    assert result["provenance"]["catalog_key"] is None
    durable = catalog.record_decision_and_audit.await_args.args[0]
    assert durable["selected"] is None
    assert durable["retention"]["reason"] == "incumbent-unresolved"
    schema = json.loads(_RECORD_SCHEMA.read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(durable)


@pytest.mark.asyncio
async def test_assignment_path_keeps_resolved_incumbent() -> None:
    service, catalog = _assignment_service("gpt-5.6-terra")
    result = await service.select_model(
        _request({"vendor": "codex", "model": "gpt-5.6-terra"}, allow_exploration=False)
    )

    assert result["selected"]["model"] == "gpt-5.6-terra"
    assert result["assignment"]["agent_id"] == "codex-local"
    assert result["retention"]["reason"] == "no-evidence"
    durable = catalog.record_decision_and_audit.await_args.args[0]
    schema = json.loads(_RECORD_SCHEMA.read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(durable)


# ── HTTP surface ─────────────────────────────────────────────────────────────

@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    reset_config()
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("COORDINATION_API_KEYS", "routing-test-key")
    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")
    reset_config()
    yield TestClient(create_coordination_api())
    reset_config()


def test_http_select_model_serializes_null_selected_with_retention(client: TestClient) -> None:
    service = AsyncMock()
    service.select_model.return_value = {
        "decision_id": "3f1b7c1e-9a3d-4f9d-8b1a-2c6e5d4a9b0c",
        "selected": None,
        "alternatives": [],
        "exploration": False,
        "fallback": False,
        "excluded": [],
        "retention": {
            "retained": True,
            "reason": "incumbent-unresolved",
            "margin": 0.05,
            "incumbent_score": None,
        },
    }
    with patch("src.model_routing.api.get_routing_service", return_value=service):
        response = client.post(
            "/routing/select_model",
            headers={"Authorization": "Bearer routing-test-key"},
            json={
                "task_signals": {"archetype": "architect"},
                "incumbent": {"vendor": None, "model": "premium"},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected"] is None
    assert payload["retention"]["reason"] == "incumbent-unresolved"
    request = service.select_model.await_args.args[0]
    assert request.incumbent.model == "premium"


# ── MCP / HTTP-proxy parity (task 4.3) ───────────────────────────────────────

_SELECTION = {
    "decision_id": "3f1b7c1e-9a3d-4f9d-8b1a-2c6e5d4a9b0c",
    "selected": None,
    "alternatives": [],
    "exploration": False,
    "fallback": False,
    "excluded": [],
}


@pytest.mark.asyncio
async def test_mcp_threads_incumbent_in_db_mode() -> None:
    from src import coordination_mcp

    service = AsyncMock()
    service.select_model.return_value = _SELECTION
    with (
        patch.object(coordination_mcp, "_transport", "db"),
        patch("src.model_routing.api.get_routing_service", return_value=service),
    ):
        await coordination_mcp.select_model_for_task(
            task_signals={"archetype": "architect"}, incumbent=_INCUMBENT
        )

    request = service.select_model.await_args.args[0]
    assert request.incumbent is not None
    assert (request.incumbent.vendor, request.incumbent.model) == ("claude_code", "fable")


@pytest.mark.asyncio
async def test_mcp_threads_incumbent_in_proxy_mode() -> None:
    from src import coordination_mcp

    with (
        patch.object(coordination_mcp, "_transport", "http"),
        patch(
            "src.coordination_mcp.http_proxy.proxy_select_model_for_task",
            new=AsyncMock(return_value=_SELECTION),
        ) as proxy,
    ):
        await coordination_mcp.select_model_for_task(
            task_signals={"archetype": "architect"}, incumbent=_INCUMBENT
        )

    assert proxy.await_args.kwargs["incumbent"] == _INCUMBENT


@pytest.mark.asyncio
@pytest.mark.parametrize("incumbent", [None, _INCUMBENT])
async def test_proxy_sends_incumbent_only_when_supplied(incumbent) -> None:
    # An older coordinator's SelectModelRequest forbids unknown keys, so an
    # absent incumbent must not appear in the body even as null.
    from src import http_proxy

    with patch.object(http_proxy, "_request", new=AsyncMock(return_value=_SELECTION)) as sent:
        await http_proxy.proxy_select_model_for_task(
            task_signals={"archetype": "architect"}, incumbent=incumbent
        )

    body = sent.await_args.kwargs["json_body"]
    if incumbent is None:
        assert "incumbent" not in body
    else:
        assert body["incumbent"] == _INCUMBENT

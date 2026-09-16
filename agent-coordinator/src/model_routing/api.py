"""Transport-neutral service and HTTP routes for adaptive model routing."""

from __future__ import annotations

import math
import os
import random
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .exploration import ExplorationBudget, choose
from .resolver import OBJECTIVE_PROFILES, Weights, score_and_rank

EndpointKind = Literal["vendor-cli", "vendor-sdk", "openrouter", "local"]
ObjectiveProfile = Literal["quality-first", "balanced", "cost-first", "resilience"]
FeedbackSource = Literal[
    "gen-eval",
    "validation",
    "vendor-switch",
    "procedural-memory",
    "transcript-triage",
]


class WeightOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    w_quality: float | None = None
    w_cost: float | None = None
    w_latency: float | None = None


class TaskSignals(BaseModel):
    model_config = ConfigDict(extra="allow")

    archetype: str = Field(min_length=1)
    phase: str | None = None
    task_type: str | None = None
    complexity: Literal["low", "medium", "high"] | None = None
    modality: Literal["interactive", "programmatic"] = "programmatic"


class SelectModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_signals: TaskSignals
    objective_profile: ObjectiveProfile | None = None
    weight_overrides: WeightOverrides | None = None
    allow_exploration: bool = True


class CandidateResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vendor: str
    model: str
    endpoint_kind: EndpointKind
    score: float
    quality: float | None = None
    norm_cost: float | None = None
    norm_latency: float | None = None
    posterior_sample_size: int | float | None = None
    stale_catalog: bool = False
    cost_source: Literal["posterior", "prior"] | None = None


class ExcludedCandidate(BaseModel):
    vendor: str
    model: str
    reason: str


class SelectModelResponse(BaseModel):
    decision_id: UUID
    selected: CandidateResponse
    alternatives: list[CandidateResponse]
    exploration: bool = False
    fallback: bool = False
    excluded: list[ExcludedCandidate] = Field(default_factory=list)


class UsageByModelResponse(BaseModel):
    vendor: str
    model: str
    endpoint_kind: EndpointKind
    prompt_tokens: int = 0
    completion_tokens: int = 0
    actual_usd: float = 0.0
    counterfactual_usd: float = 0.0
    estimated_fraction: float = 0.0


class UsageAggregateResponse(BaseModel):
    window: Literal["day", "week", "month"]
    by_model: list[UsageByModelResponse] = Field(default_factory=list)
    net_savings_usd: float = 0.0
    net_savings_usd_excluding_estimates: float = 0.0
    exploration_usd_used: float = 0.0
    metered_ceiling_usd: float = 0.0
    metered_usd_used: float = 0.0
    estimated_fraction: float = 0.0


class HTTPErrorResponse(BaseModel):
    detail: str


class FeedbackMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool | None = None
    quality_score: float | None = None
    cost_observed_usd: float | None = Field(default=None, ge=0)
    latency_observed_seconds: float | None = Field(default=None, ge=0)
    tokens_estimated: bool = False


class FeedbackEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: UUID | None = None
    source: FeedbackSource
    vendor: str
    model: str
    task_type: str
    metrics: FeedbackMetrics
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class _Catalog(Protocol):
    async def list_candidates(self, task_type: str) -> list[Any]: ...

    async def list_entries(
        self,
        endpoint_kind: str | None = None,
        include_unavailable: bool = True,
    ) -> list[dict[str, Any]]: ...

    async def record_decision(self, decision: dict[str, Any]) -> dict[str, Any]: ...

    async def get_decision(self, decision_id: str) -> dict[str, Any] | None: ...


class _Ledger(Protocol):
    async def usage_summary(
        self,
        *,
        include_estimated: bool = True,
        window: Literal["day", "week", "month"] = "month",
        month: Any = None,
    ) -> dict[str, Any]: ...


class RoutingUnavailableError(RuntimeError):
    """No feasible candidate or backing service is currently available."""


def _candidate_payload(candidate: Any) -> dict[str, Any]:
    raw = asdict(candidate)
    return {
        "vendor": raw["vendor"],
        "model": raw["model"],
        "endpoint_kind": raw["endpoint_kind"],
        "score": raw["score"],
        "quality": raw["quality"],
        "norm_cost": raw["norm_cost"],
        "norm_latency": raw["norm_latency"],
        "posterior_sample_size": raw["posterior_sample_size"],
        "stale_catalog": bool(raw.get("stale_catalog", False)),
        "cost_source": raw["cost_source"],
    }


def _task_type(signals: TaskSignals) -> str:
    explicit = signals.task_type
    if explicit is not None and explicit.strip():
        return explicit.strip()
    archetype = signals.archetype
    complexity = signals.complexity or "medium"
    return f"{archetype}/{complexity}-complexity"


def _weights(request: SelectModelRequest) -> Weights | None:
    if request.weight_overrides is None:
        return None
    base = OBJECTIVE_PROFILES[request.objective_profile or "balanced"]
    supplied = request.weight_overrides
    return replace(
        base,
        w_quality=supplied.w_quality if supplied.w_quality is not None else base.w_quality,
        w_cost=supplied.w_cost if supplied.w_cost is not None else base.w_cost,
        w_latency=supplied.w_latency if supplied.w_latency is not None else base.w_latency,
    )


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _nonnegative_env_float(name: str, default: float) -> float:
    parsed = _safe_float(os.environ.get(name), default)
    return parsed if parsed >= 0 else default


class RoutingService:
    """Compose catalog reads, pure ranking, provenance, feedback, and usage."""

    def __init__(
        self,
        catalog: _Catalog | None = None,
        ledger: _Ledger | None = None,
        *,
        rng: random.Random | None = None,
    ) -> None:
        self._catalog = catalog
        self._ledger = ledger
        self._rng = rng

    @property
    def catalog(self) -> _Catalog:
        if self._catalog is None:
            from .catalog import get_catalog_service

            self._catalog = get_catalog_service()
        return self._catalog

    @property
    def ledger(self) -> _Ledger:
        if self._ledger is None:
            from .ledger import get_routing_ledger

            self._ledger = get_routing_ledger()
        return self._ledger

    async def _current_exploration_budget(
        self,
    ) -> tuple[ExplorationBudget, dict[str, float]]:
        summary = await self.ledger.usage_summary(
            window="month",
            include_estimated=True,
        )
        entries = max(_safe_float(summary.get("entries")), 0.0)
        exploration_entries = max(
            _safe_float(summary.get("exploration_entries")),
            0.0,
        )
        pct_used = exploration_entries / entries if entries else 0.0
        usd_used = max(_safe_float(summary.get("exploration_usd_used")), 0.0)
        metered_usd_used = max(_safe_float(summary.get("actual_usd")), 0.0)
        budget = ExplorationBudget(
            pct_used=pct_used,
            pct_cap=_nonnegative_env_float("ROUTING_EXPLORATION_PCT", 0.10),
            usd_used=usd_used,
            usd_cap=_nonnegative_env_float(
                "ROUTING_EXPLORATION_MONTHLY_USD",
                0.0,
            ),
        )
        return budget, {
            "exploration_pct_used": pct_used,
            "exploration_usd_used": usd_used,
            "metered_usd_used": metered_usd_used,
        }

    async def select_model(self, request: SelectModelRequest) -> dict[str, Any]:
        candidates = await self.catalog.list_candidates(_task_type(request.task_signals))
        ranked, excluded = score_and_rank(
            candidates,
            profile=request.objective_profile or "balanced",
            weight_overrides=_weights(request),
        )
        budget, budget_state = await self._current_exploration_budget()
        selection = choose(
            ranked,
            allow_exploration=request.allow_exploration,
            budget=budget,
            rng=self._rng,
        )
        if selection is None:
            raise RoutingUnavailableError("no feasible model-routing candidate")

        selected = _candidate_payload(selection.selected)
        alternatives = [
            _candidate_payload(candidate) for candidate in ranked if candidate != selection.selected
        ]
        payload: dict[str, Any] = {
            "decision_id": str(uuid4()),
            "selected": selected,
            "alternatives": alternatives,
            "exploration": selection.exploration,
            "fallback": False,
            "excluded": [
                {"vendor": candidate.vendor, "model": candidate.model, "reason": reason}
                for candidate, reason in excluded
            ],
        }
        await self.catalog.record_decision(
            {
                **payload,
                "created_at": datetime.now(UTC).isoformat(),
                "request": request.model_dump(mode="json"),
                "policy_version": "linear-utility-v1",
                "budget_state": budget_state,
            }
        )
        return payload

    async def list_catalog(
        self, *, endpoint_kind: str | None, available_only: bool
    ) -> list[dict[str, Any]]:
        return await self.catalog.list_entries(
            endpoint_kind=endpoint_kind,
            include_unavailable=not available_only,
        )

    async def get_decision(self, decision_id: UUID) -> dict[str, Any] | None:
        return await self.catalog.get_decision(str(decision_id))

    async def get_usage(
        self,
        *,
        window: Literal["day", "week", "month"],
        include_estimates: bool,
    ) -> dict[str, Any]:
        summary = await self.ledger.usage_summary(
            window=window,
            include_estimated=include_estimates,
        )
        actual = _safe_float(summary.get("actual_usd"))
        counterfactual = _safe_float(summary.get("counterfactual_usd"))
        estimates = max(int(_safe_float(summary.get("estimated_entries"))), 0)
        entries = max(int(_safe_float(summary.get("entries"))), 0)
        savings = _safe_float(summary.get("savings_usd"), counterfactual - actual)
        return {
            "window": window,
            "by_model": summary.get("by_model", []),
            "net_savings_usd": savings,
            "net_savings_usd_excluding_estimates": _safe_float(
                summary.get("verified_savings_usd"),
                savings if estimates == 0 else 0.0,
            ),
            "exploration_usd_used": _safe_float(summary.get("exploration_usd_used")),
            "metered_ceiling_usd": _nonnegative_env_float("ROUTING_MONTHLY_CEILING_USD", 0.0),
            "metered_usd_used": actual,
            "estimated_fraction": estimates / entries if entries else 0.0,
        }

    async def post_feedback(self, event: FeedbackEvent) -> dict[str, bool]:
        """Accept feedback without coupling callers to aggregation cadence."""
        from ..audit import get_audit_service

        try:
            await get_audit_service().log_operation(
                agent_id=None,
                agent_type=None,
                operation="routing_feedback",
                parameters=event.model_dump(mode="json"),
                result={"accepted": True},
                success=True,
            )
        except Exception:  # noqa: BLE001 - feedback is explicitly best-effort
            pass
        return {"accepted": True}


_routing_service: RoutingService | None = None


def get_routing_service() -> RoutingService:
    global _routing_service
    if _routing_service is None:
        _routing_service = RoutingService()
    return _routing_service


def reset_routing_service() -> None:
    global _routing_service
    _routing_service = None


def resolve_phase_model(
    *,
    task_signals: dict[str, Any],
    static_model: str,
    provider: str | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Synchronous HTTP seam used by the synchronous archetype resolver."""
    from ..http_proxy import HttpProxyConfig

    config = HttpProxyConfig.from_env()
    if config is None:
        raise RoutingUnavailableError("COORDINATION_API_URL is not configured")
    headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
    response = httpx.post(
        f"{config.base_url}/routing/select_model",
        json={"task_signals": task_signals},
        headers=headers,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict) or not isinstance(result.get("selected"), dict):
        raise RoutingUnavailableError("adaptive router returned an invalid selection")
    return result


_AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {
        "model": HTTPErrorResponse,
        "description": "Missing or invalid coordinator API key",
    }
}
_SELECT_RESPONSES = {
    **_AUTH_RESPONSES,
    503: {
        "model": HTTPErrorResponse,
        "description": "No feasible model-routing candidate is available",
    },
}


def install_routing_routes(app: FastAPI, auth_dependency: Any) -> None:
    """Register the five OpenAPI routing paths on the coordinator app."""

    @app.post(
        "/routing/select_model",
        response_model=SelectModelResponse,
        dependencies=[Depends(auth_dependency)],
        responses=_SELECT_RESPONSES,
    )
    async def select_model_endpoint(request: SelectModelRequest) -> dict[str, Any]:
        try:
            return await get_routing_service().select_model(request)
        except RoutingUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get(
        "/routing/catalog",
        dependencies=[Depends(auth_dependency)],
        responses=_AUTH_RESPONSES,
    )
    async def catalog_endpoint(
        endpoint_kind: EndpointKind | None = None,
        available_only: bool = True,
    ) -> list[dict[str, Any]]:
        return await get_routing_service().list_catalog(
            endpoint_kind=endpoint_kind, available_only=available_only
        )

    @app.get(
        "/routing/decisions/{decision_id}",
        dependencies=[Depends(auth_dependency)],
        responses=_AUTH_RESPONSES,
    )
    async def decision_endpoint(decision_id: UUID) -> Any:
        decision = await get_routing_service().get_decision(decision_id)
        if decision is not None:
            return decision
        return JSONResponse(
            status_code=404,
            media_type="application/problem+json",
            content={
                "type": "urn:coordinator:routing:decision-not-found",
                "title": "Routing decision not found",
                "status": 404,
                "detail": f"No routing decision exists for {decision_id}",
            },
        )

    @app.get(
        "/routing/usage",
        response_model=UsageAggregateResponse,
        dependencies=[Depends(auth_dependency)],
        responses=_AUTH_RESPONSES,
    )
    async def usage_endpoint(
        window: Literal["day", "week", "month"] = "month",
        include_estimates: bool = True,
    ) -> dict[str, Any]:
        return await get_routing_service().get_usage(
            window=window, include_estimates=include_estimates
        )

    @app.post(
        "/routing/feedback",
        status_code=202,
        dependencies=[Depends(auth_dependency)],
        responses=_AUTH_RESPONSES,
    )
    async def feedback_endpoint(event: FeedbackEvent) -> dict[str, bool]:
        return await get_routing_service().post_feedback(event)

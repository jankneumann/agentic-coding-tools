"""Transport-neutral service and HTTP routes for adaptive model routing."""

from __future__ import annotations

import math
import os
import random
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.isolation_contract import IsolationMode

from .exploration import ExplorationBudget, choose, choose_evidenced
from .resolver import (
    OBJECTIVE_PROFILES,
    ExcludedAssignmentInput,
    IncumbentIdentity,
    ScoredCandidate,
    Weights,
    apply_incumbent_retention,
    build_feasible_assignments,
    score_and_rank,
)

# Match contracts/events/routing-decision-record.schema.json's
# alternatives.maxItems / excluded.maxItems -- a real catalog refresh (e.g.
# OpenRouter's full model list) can produce far more candidates/exclusions
# than the persisted-record contract allows; both the response and the
# durable payload are built from the same truncated lists so neither can
# violate it (Codex review on PR #605, round 5).
_ALTERNATIVES_MAX = 64
_EXCLUDED_MAX = 256
# Absolute utility lead an evidenced challenger needs over the incumbent
# (retain-static-model-until-routing-evidence, design D3). Server-side knob:
# ROUTING_INCUMBENT_MARGIN.
DEFAULT_INCUMBENT_MARGIN = 0.05

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

    # max_length matches contracts/events/routing-decision-record.schema.json's
    # persistedRequest.task_signals bounds -- a value the HTTP boundary accepts
    # but the persisted-record contract would reject must never reach a
    # successful select_model() call (Codex review on PR #605, round 4).
    archetype: str = Field(min_length=1, max_length=128)
    phase: str | None = Field(default=None, max_length=128)
    task_type: str | None = Field(default=None, max_length=128)
    complexity: Literal["low", "medium", "high"] | None = None
    modality: Literal["interactive", "programmatic"] = "programmatic"


class RoadmapRoutingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # min_length matches contracts/events/routing-decision-record.schema.json's
    # persistedRoadmapPolicy item bounds -- an empty string excludes no real
    # lane but would still reach persistence unchanged (Codex review on
    # PR #605, round 5).
    allowed_agent_ids: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(
        default_factory=list, max_length=64
    )
    excluded_agent_ids: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(
        default_factory=list, max_length=64
    )
    allowed_vendor_types: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(
        default_factory=list, max_length=32
    )
    excluded_vendor_types: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(
        default_factory=list, max_length=32
    )
    allowed_locations: list[Literal["local", "cloud", "unknown"]] = Field(
        default_factory=list, max_length=3
    )

    @model_validator(mode="after")
    def validate_unique_lists(self) -> RoadmapRoutingPolicy:
        for field_name in (
            "allowed_agent_ids",
            "excluded_agent_ids",
            "allowed_vendor_types",
            "excluded_vendor_types",
            "allowed_locations",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} entries must be unique")
        return self


class TaskRoutingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Bounds match contracts/events/routing-decision-record.schema.json's
    # persistedRequest.routing_profile (Codex review on PR #605, round 4).
    expected_duration_seconds: int | None = Field(default=None, ge=0, le=31536000)
    scope: Literal["read-only", "bounded-write", "broad-write"] = "read-only"
    interactivity: Literal["interactive", "headless"] = "headless"
    secret_need: Literal["none", "brokered", "direct"] = "none"
    parallelism: int = Field(default=1, ge=1, le=1024)
    repo_shape: Literal["single-package", "monorepo", "unknown"] = "unknown"
    roadmap_policy: RoadmapRoutingPolicy | None = None
    required_location: Literal["local", "cloud", "unknown"] | None = None
    required_isolation: IsolationMode | None = None
    required_dispatch_mode: Literal["review", "alternative", "quick", "sdk"] | None = None


class IncumbentRequest(BaseModel):
    """The caller's static resolution, offered as the incumbent (design D2)."""

    model_config = ConfigDict(extra="forbid")

    vendor: str | None = Field(default=None, max_length=128)
    model: str = Field(min_length=1, max_length=256)


class SelectModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_signals: TaskSignals
    routing_profile: TaskRoutingProfile | None = None
    objective_profile: ObjectiveProfile | None = None
    weight_overrides: WeightOverrides | None = None
    allow_exploration: bool = True
    incumbent: IncumbentRequest | None = None


class RoutingAssignmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    vendor_type: str
    policy_vendor: str
    catalog_vendor: str
    location: Literal["local", "cloud", "unknown"]
    isolation: IsolationMode
    dispatch_mode: Literal["review", "alternative", "quick", "sdk"]
    model: str
    endpoint_kind: str
    base_url: str | None = None


class RoutingProvenanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["coordinator", "local-static"]
    policy_version: str
    policy_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    matched_rule_ids: list[str] = Field(max_length=32)
    rationale: list[str] = Field(max_length=32)
    persisted: bool
    durable_audit: bool
    catalog_key: tuple[str, str, str, str | None] | None


class CandidateResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vendor: str
    model: str
    endpoint_kind: EndpointKind
    base_url: str | None = None
    score: float
    quality: float | None = None
    norm_cost: float | None = None
    norm_latency: float | None = None
    posterior_sample_size: int | float | None = None
    stale_catalog: bool = False
    cost_source: Literal["posterior", "prior"] | None = None
    # dg-04's own overlay: absent whenever assignment-based routing (policy/
    # registry/catalog-driven location+isolation+dispatch_mode) is disabled,
    # i.e. the base dg-00 linear-utility selection shape.
    assignment: RoutingAssignmentResponse | None = None


class ExcludedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str | None = None
    vendor: str
    model: str
    endpoint_kind: str
    base_url: str | None = None
    reason: str


RetentionReason = Literal[
    "challenger-evidenced-above-margin",
    "no-evidence",
    "below-margin",
    "incumbent-unresolved",
    "incumbent-infeasible-evidenced-alternative",
    "incumbent-infeasible-no-evidenced-alternative",
    "exploration-evidenced",
]


class RetentionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retained: bool
    reason: RetentionReason
    margin: float = Field(ge=0)
    incumbent_score: float | None = None


class SelectModelResponse(BaseModel):
    decision_id: UUID
    # Null only when an incumbent was kept that no feasible catalog row
    # represents; ``retention`` then says why (design D5).
    selected: CandidateResponse | None
    alternatives: list[CandidateResponse]
    exploration: bool = False
    fallback: bool = False
    excluded: list[ExcludedCandidate] = Field(default_factory=list)
    # Both absent together whenever assignment-based routing is disabled --
    # see CandidateResponse.assignment.
    assignment: RoutingAssignmentResponse | None = None
    provenance: RoutingProvenanceResponse | None = None
    # ``retention`` exists only for requests that supplied an incumbent; everyone
    # else keeps the exact pre-change response shape. A field-level exclusion
    # (not a model serializer) keeps the published OpenAPI schema intact.
    retention: RetentionResponse | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


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

    async def record_decision_and_audit(
        self, decision: dict[str, Any]
    ) -> dict[str, Any]: ...

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
        "base_url": raw.get("base_url"),
        "score": raw["score"],
        "quality": raw["quality"],
        "norm_cost": raw["norm_cost"],
        "norm_latency": raw["norm_latency"],
        "posterior_sample_size": raw["posterior_sample_size"],
        "stale_catalog": bool(raw.get("stale_catalog", False)),
        "cost_source": raw["cost_source"],
        **({"assignment": raw["assignment"]} if raw.get("assignment") is not None else {}),
    }


def _excluded_payload(item: ExcludedAssignmentInput) -> dict[str, Any]:
    return asdict(item)


def _sanitized_request(request: SelectModelRequest) -> dict[str, Any]:
    signals = request.task_signals.model_dump(
        mode="json",
        include={"archetype", "phase", "task_type", "complexity", "modality"},
    )
    return {
        "task_signals": signals,
        "routing_profile": (
            request.routing_profile.model_dump(mode="json")
            if request.routing_profile is not None
            else None
        ),
        "objective_profile": request.objective_profile,
        "weight_overrides": (
            request.weight_overrides.model_dump(mode="json")
            if request.weight_overrides is not None
            else None
        ),
        "allow_exploration": request.allow_exploration,
        **(
            {"incumbent": request.incumbent.model_dump(mode="json")}
            if request.incumbent is not None
            else {}
        ),
    }


def _persisted_request(request: SelectModelRequest) -> dict[str, Any]:
    # Omit an absent incumbent so pre-change requests persist unchanged.
    return request.model_dump(
        mode="json", exclude={"incumbent"} if request.incumbent is None else None
    )


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
        registry: Any | None = None,
        policy: Any | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._catalog = catalog
        self._ledger = ledger
        self._registry = registry
        self._policy = policy
        self._assignment_enabled = registry is not None or policy is not None or catalog is None
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

    @property
    def registry(self) -> Any:
        if self._registry is None:
            from ..vendor_registry import VendorRegistryService

            self._registry = VendorRegistryService(audit=None)
        return self._registry

    @property
    def policy(self) -> Any:
        if self._policy is None:
            from .routing_policy import load_routing_policy

            self._policy = load_routing_policy()
        return self._policy

    async def _current_exploration_budget(
        self,
    ) -> tuple[ExplorationBudget, dict[str, Any]]:
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
            "status": "available",
            "exploration_pct_used": pct_used,
            "exploration_usd_used": usd_used,
            "metered_usd_used": metered_usd_used,
        }

    async def select_model(self, request: SelectModelRequest) -> dict[str, Any]:
        candidates = await self.catalog.list_candidates(_task_type(request.task_signals))
        assignment_excluded: list[ExcludedAssignmentInput] = []
        evaluation: Any | None = None
        if self._assignment_enabled:
            try:
                lanes = await self.registry.list_vendors(available_only=False)
                if not isinstance(lanes, list):
                    raise TypeError("registry result is not a list")
            except Exception as exc:
                raise RoutingUnavailableError("routing-registry-unavailable") from exc
            profile = (
                request.routing_profile.model_dump(mode="python")
                if request.routing_profile is not None
                else TaskRoutingProfile().model_dump(mode="python")
            )
            profile.update(
                {
                    "phase": request.task_signals.phase,
                    "archetype": request.task_signals.archetype,
                }
            )
            evaluation = self.policy.evaluate(profile)
            explicit = request.routing_profile
            required_location: str | None = (
                explicit.required_location if explicit is not None else None
            )
            if (
                required_location is not None
                and evaluation.location is not None
                and required_location != evaluation.location
            ):
                required_location = "__constraint-conflict__"
            elif required_location is None:
                required_location = evaluation.location
            required_isolation: str | None = (
                explicit.required_isolation if explicit is not None else None
            )
            if (
                required_isolation is not None
                and evaluation.isolation is not None
                and required_isolation != evaluation.isolation
            ):
                required_isolation = "__constraint-conflict__"
            elif required_isolation is None:
                required_isolation = evaluation.isolation
            explicit_dispatch = (
                explicit.required_dispatch_mode if explicit is not None else None
            )
            rule_dispatch = getattr(evaluation, "rule_dispatch_mode", None)
            if (
                explicit_dispatch is not None
                and rule_dispatch is not None
                and explicit_dispatch != rule_dispatch
            ):
                dispatch_mode = "__constraint-conflict__"
            else:
                dispatch_mode = explicit_dispatch or evaluation.dispatch_mode
            roadmap = (
                explicit.roadmap_policy.model_dump(mode="python")
                if explicit is not None and explicit.roadmap_policy is not None
                else None
            )
            candidates, assignment_excluded = build_feasible_assignments(
                lanes,
                candidates,
                archetype=request.task_signals.archetype,
                dispatch_mode=dispatch_mode,
                required_location=required_location,
                required_isolation=required_isolation,
                roadmap_policy=roadmap,
            )
        ranked, excluded = score_and_rank(
            candidates,
            profile=request.objective_profile or "balanced",
            weight_overrides=_weights(request),
        )
        budget: ExplorationBudget | None = None
        exploration_allowed = request.allow_exploration
        budget_state: dict[str, Any] = {
            "status": "not-requested",
            "exploration_pct_used": None,
            "exploration_usd_used": None,
            "metered_usd_used": None,
        }
        if exploration_allowed:
            try:
                budget, budget_state = await self._current_exploration_budget()
            except Exception:  # noqa: BLE001 - budget failure degrades to exploitation
                exploration_allowed = False
                budget_state = {
                    "status": "unavailable",
                    "exploration_pct_used": None,
                    "exploration_usd_used": None,
                    "metered_usd_used": None,
                    "degraded_reason": "ledger-read-failed",
                }
        retention: dict[str, Any] | None = None
        chosen: ScoredCandidate | None
        if request.incumbent is None:
            selection = choose(
                ranked,
                allow_exploration=exploration_allowed,
                budget=budget,
                rng=self._rng,
            )
            if selection is None:
                raise RoutingUnavailableError("no feasible model-routing candidate")
            chosen, explored = selection.selected, selection.exploration
        else:
            chosen, explored, retention = self._retain_incumbent(
                request.incumbent,
                ranked,
                [(c.vendor, c.model) for c, _reason in excluded]
                + [(item.vendor, item.model) for item in assignment_excluded],
                allow_exploration=exploration_allowed,
                budget=budget,
            )

        selected = _candidate_payload(chosen) if chosen is not None else None
        alternatives = [
            _candidate_payload(candidate) for candidate in ranked if candidate != chosen
        ][:_ALTERNATIVES_MAX]
        excluded_payloads = [_excluded_payload(item) for item in assignment_excluded]
        excluded_payloads.extend(
            _excluded_payload(
                ExcludedAssignmentInput(
                    agent_id=(
                        candidate.assignment.agent_id
                        if candidate.assignment is not None
                        else None
                    ),
                    vendor=candidate.vendor,
                    model=candidate.model,
                    endpoint_kind=candidate.endpoint_kind,
                    base_url=candidate.base_url,
                    reason=reason,
                )
            )
            for candidate, reason in excluded
        )
        excluded_payloads = excluded_payloads[:_EXCLUDED_MAX]
        payload: dict[str, Any] = {
            "decision_id": str(uuid4()),
            "selected": selected,
            "alternatives": alternatives,
            "exploration": explored,
            "fallback": False,
            "excluded": excluded_payloads,
        }
        if retention is not None:
            payload["retention"] = retention
        if self._assignment_enabled:
            assignment = selected["assignment"] if selected is not None else None
            assert selected is None or isinstance(assignment, dict)
            assert evaluation is not None
            provenance = {
                "source": "coordinator",
                "policy_version": self.policy.version,
                "policy_checksum": self.policy.checksum,
                "matched_rule_ids": list(evaluation.matched_rule_ids),
                "rationale": list(evaluation.rationale),
                "persisted": True,
                "durable_audit": True,
                "catalog_key": (
                    [
                        assignment["catalog_vendor"],
                        assignment["model"],
                        assignment["endpoint_kind"],
                        assignment["base_url"],
                    ]
                    if assignment is not None
                    else None
                ),
            }
            payload["assignment"] = assignment
            payload["provenance"] = provenance
            durable_payload = {
                **payload,
                "selected": (
                    {**selected, "provenance": provenance} if selected is not None else None
                ),
                "created_at": datetime.now(UTC).isoformat(),
                "request": _sanitized_request(request),
                "policy_version": "linear-utility-v1",
                "budget_state": budget_state,
            }
            try:
                await self.catalog.record_decision_and_audit(durable_payload)
            except Exception as exc:
                raise RoutingUnavailableError("routing-durability-unavailable") from exc
        else:
            await self.catalog.record_decision(
                {
                    **payload,
                    "created_at": datetime.now(UTC).isoformat(),
                    "request": _persisted_request(request),
                    "policy_version": "linear-utility-v1",
                    "budget_state": budget_state,
                }
            )
        return payload

    def _retain_incumbent(
        self,
        incumbent: IncumbentRequest,
        ranked: list[ScoredCandidate],
        excluded_identities: list[tuple[str, str]],
        *,
        allow_exploration: bool,
        budget: ExplorationBudget | None,
    ) -> tuple[ScoredCandidate | None, bool, dict[str, Any]]:
        """Apply incumbent retention, then evidenced-only exploration (D3, D4)."""
        decision = apply_incumbent_retention(
            ranked,
            excluded_identities,
            IncumbentIdentity(vendor=incumbent.vendor, model=incumbent.model),
            _nonnegative_env_float("ROUTING_INCUMBENT_MARGIN", DEFAULT_INCUMBENT_MARGIN),
        )
        retention: dict[str, Any] = {
            "retained": decision.retained,
            "reason": decision.reason,
            "margin": decision.margin,
            "incumbent_score": decision.incumbent_score,
        }
        if decision.selected is None:
            return None, False, retention
        selection = choose_evidenced(
            decision.selected,
            ranked,
            allow_exploration=allow_exploration,
            budget=budget,
            rng=self._rng,
        )
        if selection.exploration:
            retention = {**retention, "retained": False, "reason": "exploration-evidenced"}
        return selection.selected, selection.exploration, retention

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
    incumbent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Synchronous HTTP seam used by the synchronous archetype resolver.

    ``incumbent`` is sent only when given, so this client still works against a
    coordinator that predates the field. A null ``selected`` is valid only when
    the router reports the incumbent as retained.
    """
    from ..http_proxy import HttpProxyConfig

    config = HttpProxyConfig.from_env()
    if config is None:
        raise RoutingUnavailableError("COORDINATION_API_URL is not configured")
    headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
    body: dict[str, Any] = {"task_signals": task_signals}
    if incumbent is not None:
        body["incumbent"] = incumbent
    response = httpx.post(
        f"{config.base_url}/routing/select_model",
        json=body,
        headers=headers,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict):
        raise RoutingUnavailableError("adaptive router returned an invalid selection")
    retention = result.get("retention")
    retained = isinstance(retention, dict) and retention.get("retained") is True
    if not isinstance(result.get("selected"), dict) and not retained:
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

"""Pydantic models generated from contracts/openapi/v1.yaml (routing API surface).

Hand-materialized from the OpenAPI 3.1 component schemas so downstream packages
(wp-resolver, wp-dispatch, wp-feedback, wp-dashboard) share one typed contract
rather than each other's internals. Keep in sync with contracts/openapi/v1.yaml;
the parity test in tests/model_routing/test_contracts_generated.py asserts the
field sets match the OpenAPI source.

Source of truth: openspec/changes/add-adaptive-model-router/contracts/openapi/v1.yaml
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

EndpointKind = Literal["vendor-cli", "vendor-sdk", "openrouter", "local"]
ObjectiveProfile = Literal["quality-first", "balanced", "cost-first", "resilience"]
FeedbackSource = Literal[
    "gen-eval", "validation", "vendor-switch", "procedural-memory", "transcript-triage"
]


class WeightOverrides(BaseModel):
    w_quality: float | None = None
    w_cost: float | None = None
    w_latency: float | None = None


class TaskSignals(BaseModel):
    archetype: str
    phase: str | None = None
    task_type: str | None = None
    complexity: Literal["low", "medium", "high"] | None = None
    modality: Literal["interactive", "programmatic"] = "programmatic"

    model_config = {"extra": "allow"}  # additionalProperties: true in the contract


class SelectModelRequest(BaseModel):
    task_signals: TaskSignals
    objective_profile: ObjectiveProfile | None = None
    weight_overrides: WeightOverrides | None = None
    allow_exploration: bool = True


class Candidate(BaseModel):
    vendor: str
    model: str
    endpoint_kind: EndpointKind
    score: float
    quality: float | None = None
    norm_cost: float | None = None
    norm_latency: float | None = None
    posterior_sample_size: int | None = None
    stale_catalog: bool = False
    # Provenance for the cost term (design D3, rev2): "posterior" once the
    # (model, task_type) cost-per-completed-task sample clears confidence,
    # else "prior" (catalog per-Mtok price).
    cost_source: Literal["posterior", "prior"] | None = None


class ExcludedCandidate(BaseModel):
    vendor: str
    model: str
    reason: str


class SelectModelResponse(BaseModel):
    decision_id: str
    selected: Candidate
    alternatives: list[Candidate] = Field(default_factory=list)
    exploration: bool = False
    fallback: bool = False
    excluded: list[ExcludedCandidate] = Field(default_factory=list)


class CatalogRow(BaseModel):
    vendor: str
    model: str
    endpoint_kind: EndpointKind
    base_url: str | None = None
    prompt_usd_per_mtok: float | None = None
    completion_usd_per_mtok: float | None = None
    context_window: int | None = None
    benchmark_priors: dict[str, float] = Field(default_factory=dict)
    p50_latency_ms: float | None = None
    available: bool = True
    # Proactive quota headroom (design D13). None when the quota probe is off or
    # the provider is uncovered (reactive throttle-triangulation fallback).
    quota_headroom_pct: float | None = None
    quota_reset_at: datetime | None = None
    quota_source: str | None = None
    refreshed_at: datetime | None = None
    stale: bool = False


class BudgetState(BaseModel):
    exploration_pct_used: float | None = None
    exploration_usd_used: float | None = None
    metered_usd_used: float | None = None


class RoutingDecision(BaseModel):
    decision_id: str
    created_at: datetime
    request: SelectModelRequest
    selected: Candidate
    alternatives: list[Candidate] = Field(default_factory=list)
    exploration: bool = False
    fallback: bool = False
    policy_version: str
    budget_state: BudgetState = Field(default_factory=BudgetState)
    outcome_ref: str | None = None


class UsageByModel(BaseModel):
    vendor: str
    model: str
    endpoint_kind: EndpointKind
    prompt_tokens: int = 0
    completion_tokens: int = 0
    actual_usd: float = 0.0
    counterfactual_usd: float = 0.0
    estimated_fraction: float = 0.0


class UsageAggregate(BaseModel):
    window: str
    by_model: list[UsageByModel] = Field(default_factory=list)
    net_savings_usd: float = 0.0
    net_savings_usd_excluding_estimates: float = 0.0
    exploration_usd_used: float = 0.0
    metered_ceiling_usd: float = 0.0
    metered_usd_used: float = 0.0


class FeedbackMetrics(BaseModel):
    success: bool | None = None
    quality_score: float | None = None
    cost_observed_usd: float | None = None
    latency_observed_seconds: float | None = None
    tokens_estimated: bool = False


class FeedbackEvent(BaseModel):
    source: FeedbackSource
    vendor: str
    model: str
    task_type: str
    metrics: FeedbackMetrics
    decision_id: str | None = None
    observed_at: datetime | None = None

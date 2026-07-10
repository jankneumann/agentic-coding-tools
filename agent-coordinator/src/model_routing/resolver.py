"""Pure selection-scoring core for the adaptive model router.

No DB, no network, no I/O — operates on plain candidate/posterior inputs so the
routing intelligence is fully unit-testable. The DB-backed catalog layer
(wp-db-catalog) maps ``model_catalog`` rows into ``CandidateInput``; the API/MCP
layer (wp-resolver 3.7–3.10) wraps ``score_and_rank`` + exploration selection.

Design decisions realized here:
- D3  — linear utility with named objective profiles; cost term is the
        success-adjusted observed cost-per-completed-task posterior, with
        per-Mtok price as the *prior* for unsampled pairs (rev2).
- D9  — quality blends benchmark prior with task-type posterior by a
        sample-size confidence weight (rev2).
- D10 — hard feasibility is applied BEFORE scoring; infeasible candidates are
        never ranked (Cedar policy files plug into ``feasibility_reason``).
- D13 — the ``resilience`` objective rewards proactive quota headroom (rev3).

All quality/headroom inputs are expected on a 0..1 scale; costs and latencies
are min-max normalized across the feasible candidate set at scoring time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# Sample size at which a task-type posterior is trusted enough to blend in /
# to use the observed cost-per-completed-task instead of the price prior.
DEFAULT_CONFIDENCE_K = 5.0
DEFAULT_COST_SAMPLE_THRESHOLD = 5.0
# Floor on success_rate so a near-zero-success model yields a large (not
# infinite) effective cost-per-completed-task.
_SUCCESS_FLOOR = 0.05

CostSource = Literal["posterior", "prior"]


@dataclass(frozen=True)
class Weights:
    """Objective-profile weights. Higher score = better candidate."""

    w_quality: float
    w_cost: float
    w_latency: float
    w_headroom: float = 0.0


# Named objective profiles (design D3). `resilience` is the only profile that
# materially weights quota headroom (design D13).
OBJECTIVE_PROFILES: dict[str, Weights] = {
    "quality-first": Weights(w_quality=1.0, w_cost=0.15, w_latency=0.05),
    "balanced": Weights(w_quality=0.6, w_cost=0.3, w_latency=0.1, w_headroom=0.05),
    "cost-first": Weights(w_quality=0.35, w_cost=0.6, w_latency=0.05),
    "resilience": Weights(w_quality=0.5, w_cost=0.2, w_latency=0.1, w_headroom=0.4),
}


@dataclass(frozen=True)
class Posterior:
    """Task-type feedback posterior for one (model, task_type)."""

    quality: float | None = None            # 0..1 observed quality
    cost_per_task_usd: float | None = None  # observed cost per completed task
    success_rate: float | None = None       # 0..1
    latency_seconds: float | None = None
    sample_size: float = 0.0


@dataclass(frozen=True)
class CandidateInput:
    """One routable candidate as seen by the scorer.

    Maps from a ``model_catalog`` row + its ``model_posteriors`` for the task
    type. ``modality_eligible`` folds in the Cedar hard-constraint verdict
    (design D10) — the scorer treats it as an opaque feasibility bit.
    """

    vendor: str
    model: str
    endpoint_kind: str
    benchmark_prior: float = 0.0            # 0..1 prior quality
    prompt_usd_per_mtok: float | None = None
    completion_usd_per_mtok: float | None = None
    p50_latency_ms: float | None = None
    quota_headroom_pct: float | None = None  # 0..100; None = unknown/uncovered
    available: bool = True
    modality_eligible: bool = True          # Cedar verdict (D10)
    exclusion_reason: str | None = None      # pre-computed hard-constraint reason
    posterior: Posterior = field(default_factory=Posterior)


@dataclass(frozen=True)
class ScoredCandidate:
    vendor: str
    model: str
    endpoint_kind: str
    score: float
    quality: float
    norm_cost: float
    norm_latency: float
    headroom: float
    cost_source: CostSource
    posterior_sample_size: float


def blend_quality(
    benchmark_prior: float,
    posterior: Posterior,
    confidence_k: float = DEFAULT_CONFIDENCE_K,
) -> float:
    """Blend benchmark prior with task-type posterior by sample-size confidence.

    confidence = n / (n + k); blended = c·posterior + (1-c)·prior. With no
    samples the prior dominates; as n grows the posterior takes over (D9).
    """
    if posterior.quality is None or posterior.sample_size <= 0:
        return benchmark_prior
    confidence = posterior.sample_size / (posterior.sample_size + confidence_k)
    return confidence * posterior.quality + (1.0 - confidence) * benchmark_prior


def effective_cost(
    cand: CandidateInput,
    cost_sample_threshold: float = DEFAULT_COST_SAMPLE_THRESHOLD,
) -> tuple[float, CostSource]:
    """Return (raw effective cost, source).

    Posterior path (D3, rev2): success-adjusted observed cost-per-completed-task
    = cost_per_task / max(success_rate, floor). Prior path: mean per-Mtok price.
    """
    post = cand.posterior
    if (
        post.cost_per_task_usd is not None
        and post.sample_size >= cost_sample_threshold
    ):
        sr = post.success_rate if post.success_rate is not None else 1.0
        return post.cost_per_task_usd / max(sr, _SUCCESS_FLOOR), "posterior"
    # Prior: mean of prompt/completion per-Mtok price (a proxy, not a per-task
    # cost — deliberately only used until the posterior clears the threshold).
    prices = [
        p
        for p in (cand.prompt_usd_per_mtok, cand.completion_usd_per_mtok)
        if p is not None
    ]
    prior = sum(prices) / len(prices) if prices else 0.0
    return prior, "prior"


def feasibility_reason(cand: CandidateInput) -> str | None:
    """Return a hard-constraint exclusion reason, or None if feasible (D10).

    Cedar policy verdicts arrive pre-computed on the candidate
    (``modality_eligible`` / ``exclusion_reason``); this also enforces
    availability and exhausted-quota (D13) as universal feasibility gates.
    """
    if cand.exclusion_reason:
        return cand.exclusion_reason
    if not cand.available:
        return "unavailable"
    if not cand.modality_eligible:
        return "cedar:modality-ineligible"
    if cand.quota_headroom_pct is not None and cand.quota_headroom_pct <= 0:
        return "quota:exhausted"
    return None


def _min_max_norm(values: list[float]) -> list[float]:
    """Normalize to 0..1 (0 = min). Flat sets map to all-zeros (no penalty)."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo <= 1e-12:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def _headroom_fraction(cand: CandidateInput) -> float:
    """0..1 headroom; unknown/uncovered treated as full (1.0) — no penalty."""
    if cand.quota_headroom_pct is None:
        return 1.0
    return max(0.0, min(1.0, cand.quota_headroom_pct / 100.0))


def score_and_rank(
    candidates: list[CandidateInput],
    profile: str = "balanced",
    weight_overrides: Weights | None = None,
    confidence_k: float = DEFAULT_CONFIDENCE_K,
    cost_sample_threshold: float = DEFAULT_COST_SAMPLE_THRESHOLD,
) -> tuple[list[ScoredCandidate], list[tuple[CandidateInput, str]]]:
    """Filter infeasible candidates, then rank the rest by linear utility.

    Returns (ranked_descending, excluded[(candidate, reason)]). Cost and latency
    are min-max normalized across the *feasible* set so the scale is relative to
    the actual choice at hand.
    """
    weights = weight_overrides or OBJECTIVE_PROFILES.get(
        profile, OBJECTIVE_PROFILES["balanced"]
    )

    feasible: list[CandidateInput] = []
    excluded: list[tuple[CandidateInput, str]] = []
    for c in candidates:
        reason = feasibility_reason(c)
        if reason:
            excluded.append((c, reason))
        else:
            feasible.append(c)
    if not feasible:
        return [], excluded

    qualities = [blend_quality(c.benchmark_prior, c.posterior, confidence_k) for c in feasible]
    cost_pairs = [effective_cost(c, cost_sample_threshold) for c in feasible]
    raw_costs = [cp[0] for cp in cost_pairs]
    cost_sources = [cp[1] for cp in cost_pairs]
    # Missing latency treated as neutral (median-ish 0.5 after norm) by using the
    # max observed so it is not rewarded; if all missing, norm yields zeros.
    observed_lat = [c.p50_latency_ms for c in feasible if c.p50_latency_ms is not None]
    lat_fallback = max(observed_lat) if observed_lat else 0.0
    raw_lat = [c.p50_latency_ms if c.p50_latency_ms is not None else lat_fallback for c in feasible]

    norm_costs = _min_max_norm(raw_costs)
    norm_lats = _min_max_norm(raw_lat)

    scored: list[ScoredCandidate] = []
    for c, q, nc, nl, src in zip(feasible, qualities, norm_costs, norm_lats, cost_sources):
        headroom = _headroom_fraction(c)
        score = (
            weights.w_quality * q
            - weights.w_cost * nc
            - weights.w_latency * nl
            + weights.w_headroom * headroom
        )
        scored.append(
            ScoredCandidate(
                vendor=c.vendor,
                model=c.model,
                endpoint_kind=c.endpoint_kind,
                score=score,
                quality=q,
                norm_cost=nc,
                norm_latency=nl,
                headroom=headroom,
                cost_source=src,
                posterior_sample_size=c.posterior.sample_size,
            )
        )
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored, excluded

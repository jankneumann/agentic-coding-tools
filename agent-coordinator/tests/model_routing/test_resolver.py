"""wp-resolver scoring core tests (tasks 3.1, 3.3, 3.5).

Pure unit tests — no DB, no network. Cover the three plan revisions:
rev2 cost-per-completed-task (D3), rev2 prior/posterior blend (D9), rev3 quota
headroom resilience (D13), plus hard-constraint feasibility (D10) and the
dual-ceiling exploration budget (D6).
"""

from __future__ import annotations

import random

import pytest

from src.model_routing.exploration import ExplorationBudget, choose
from src.model_routing.resolver import (
    OBJECTIVE_PROFILES,
    CandidateInput,
    Posterior,
    Weights,
    blend_quality,
    effective_cost,
    feasibility_reason,
    score_and_rank,
)

# ── D9: prior/posterior blend by confidence ──────────────────────────────────

def test_blend_uses_prior_with_no_samples():
    assert blend_quality(0.8, Posterior()) == 0.8


def test_blend_shifts_toward_posterior_as_samples_grow():
    low = blend_quality(0.2, Posterior(quality=0.9, sample_size=1))
    high = blend_quality(0.2, Posterior(quality=0.9, sample_size=100))
    assert 0.2 < low < high < 0.9  # more samples → closer to posterior


# ── D3 (rev2): cost term = success-adjusted cost-per-completed-task ───────────

def test_effective_cost_prior_path_uses_mean_price():
    c = CandidateInput(
        vendor="x", model="m", endpoint_kind="openrouter",
        prompt_usd_per_mtok=2.0, completion_usd_per_mtok=4.0,
    )
    cost, source = effective_cost(c)
    assert source == "prior"
    assert cost == pytest.approx(3.0)


def test_effective_cost_posterior_prices_in_retries():
    # 80% success at $1.60/task → effective $2.00/task.
    c = CandidateInput(
        vendor="x", model="m", endpoint_kind="openrouter",
        posterior=Posterior(cost_per_task_usd=1.60, success_rate=0.8, sample_size=10),
    )
    cost, source = effective_cost(c)
    assert source == "posterior"
    assert cost == pytest.approx(2.0)


def test_cheaper_token_price_but_worse_cost_per_task_ranks_more_expensive():
    """model-routing.4 — the Databricks Sonnet/Opus inversion.

    A (cheap per token, low success) vs B (dearer per token, high success).
    Under cost-first the success-adjusted posterior must make B win on cost.
    """
    a = CandidateInput(
        vendor="a", model="cheap-token", endpoint_kind="openrouter",
        benchmark_prior=0.7,
        posterior=Posterior(cost_per_task_usd=2.09, success_rate=0.81, sample_size=20),
    )
    b = CandidateInput(
        vendor="b", model="dear-token", endpoint_kind="openrouter",
        benchmark_prior=0.7,
        posterior=Posterior(cost_per_task_usd=1.94, success_rate=0.87, sample_size=20),
    )
    ranked, _ = score_and_rank([a, b], profile="cost-first")
    assert ranked[0].model == "dear-token"
    assert all(s.cost_source == "posterior" for s in ranked)


def test_objective_profile_changes_the_winner():
    """A: high quality, expensive.  B: mid quality, cheap."""
    a = CandidateInput(vendor="a", model="premium", endpoint_kind="vendor-sdk",
                       benchmark_prior=0.95, prompt_usd_per_mtok=15, completion_usd_per_mtok=75)
    b = CandidateInput(vendor="b", model="economy", endpoint_kind="local",
                       benchmark_prior=0.65, prompt_usd_per_mtok=0.1, completion_usd_per_mtok=0.1)
    q_first, _ = score_and_rank([a, b], profile="quality-first")
    c_first, _ = score_and_rank([a, b], profile="cost-first")
    assert q_first[0].model == "premium"
    assert c_first[0].model == "economy"


# ── D10: hard feasibility applied before scoring ─────────────────────────────

def test_ineligible_candidate_excluded_before_scoring():
    eligible = CandidateInput(vendor="codex", model="gpt", endpoint_kind="vendor-cli",
                              benchmark_prior=0.6)
    ineligible = CandidateInput(vendor="claude", model="fable", endpoint_kind="vendor-cli",
                                benchmark_prior=0.99, modality_eligible=False)
    ranked, excluded = score_and_rank([eligible, ineligible], profile="quality-first")
    assert [s.model for s in ranked] == ["gpt"]
    assert excluded[0][1] == "cedar:modality-ineligible"


def test_exhausted_quota_is_infeasible():
    assert feasibility_reason(
        CandidateInput(vendor="v", model="m", endpoint_kind="vendor-cli", quota_headroom_pct=0)
    ) == "quota:exhausted"


def test_unavailable_local_endpoint_excluded():
    assert feasibility_reason(
        CandidateInput(vendor="v", model="m", endpoint_kind="local", available=False)
    ) == "unavailable"


# ── D13 (rev3): resilience objective rewards quota headroom ───────────────────

def test_resilience_downranks_near_cap_provider():
    full = CandidateInput(vendor="a", model="has-headroom", endpoint_kind="vendor-cli",
                          benchmark_prior=0.7, quota_headroom_pct=90)
    near_cap = CandidateInput(vendor="b", model="near-cap", endpoint_kind="vendor-cli",
                              benchmark_prior=0.7, quota_headroom_pct=3)
    resilience, _ = score_and_rank([near_cap, full], profile="resilience")
    quality, _ = score_and_rank([near_cap, full], profile="quality-first")
    assert resilience[0].model == "has-headroom"
    # Under quality-first (w_headroom=0) the tie isn't broken by headroom.
    assert quality[0].headroom in (0.9, 0.03)


# ── D6: exploration dual-ceiling budget ──────────────────────────────────────

def _ranked_pair():
    a = CandidateInput(vendor="a", model="top", endpoint_kind="local", benchmark_prior=0.9)
    b = CandidateInput(vendor="b", model="alt", endpoint_kind="local", benchmark_prior=0.5)
    ranked, _ = score_and_rank([a, b], profile="quality-first")
    assert ranked[0].model == "top"
    return ranked


def test_exploration_disabled_returns_top():
    sel = choose(_ranked_pair(), allow_exploration=False)
    assert sel is not None and not sel.exploration and sel.selected.model == "top"


def test_premium_ineligible_never_explores():
    sel = choose(_ranked_pair(), premium_ineligible=True, epsilon=1.0)
    assert not sel.exploration and sel.selected.model == "top"


def test_pct_ceiling_exhausted_forces_exploitation():
    budget = ExplorationBudget(pct_used=0.10, pct_cap=0.10)
    sel = choose(_ranked_pair(), budget=budget, epsilon=1.0)
    assert not sel.exploration and sel.reason == "exploit:budget-exhausted"


def test_usd_ceiling_exhausted_forces_exploitation():
    budget = ExplorationBudget(pct_cap=1.0, usd_used=50.0, usd_cap=50.0)
    sel = choose(_ranked_pair(), budget=budget, epsilon=1.0)
    assert not sel.exploration


def test_exploration_within_budget_picks_alternative():
    budget = ExplorationBudget(pct_used=0.0, pct_cap=1.0)
    sel = choose(_ranked_pair(), budget=budget, epsilon=1.0, rng=random.Random(0))
    assert sel.exploration and sel.selected.model == "alt"
    assert sel.reason == "explore:epsilon"


def test_empty_candidate_set_returns_none():
    assert choose([]) is None


def test_all_profiles_have_weights():
    for name in ("quality-first", "balanced", "cost-first", "resilience"):
        assert isinstance(OBJECTIVE_PROFILES[name], Weights)

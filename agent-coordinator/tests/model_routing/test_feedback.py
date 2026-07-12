"""wp-feedback aggregation tests (tasks 5.1, 5.3).

Pure unit tests — no DB. Cover D9 source weighting (deterministic > LLM-judged),
exponential decay, sample-size accumulation, and the roadmap-record normalizers.
"""

from __future__ import annotations

import pytest

from src.model_routing.feedback import (
    SOURCE_WEIGHTS,
    FeedbackObservation,
    aggregate,
    normalize_vendor_notes,
    normalize_vendor_switch,
)


def _obs(model, source, value, metric="quality", age=0.0):
    return FeedbackObservation(
        model_id=model, task_type="implementer/high", metric=metric,
        value=value, source=source, age_days=age,
    )


# ── D9: source weighting ─────────────────────────────────────────────────────

def test_deterministic_sources_outweigh_llm_judged():
    assert SOURCE_WEIGHTS["validation"] > SOURCE_WEIGHTS["gen-eval"]
    assert SOURCE_WEIGHTS["vendor-switch"] > SOURCE_WEIGHTS["gen-eval"]
    assert SOURCE_WEIGHTS["gen-eval"] > SOURCE_WEIGHTS["procedural-memory"]
    assert SOURCE_WEIGHTS["procedural-memory"] > SOURCE_WEIGHTS["transcript-triage"]


def test_deterministic_failure_outweighs_favorable_llm_score():
    """model-routing.9 — a held-out validation failure must pull the posterior
    below a favorable gen-eval (LLM-judged) score."""
    obs = [
        _obs("m", "validation", 0.0),   # deterministic failure, weight 1.0
        _obs("m", "gen-eval", 0.9),     # favorable judged score, weight 0.7
    ]
    post = aggregate(obs)[("m", "implementer/high", "quality")]
    assert post.value < 0.5           # deterministic failure dominates
    assert post.value < 0.9           # below the judged score
    assert post.value == pytest.approx((0.0 * 1.0 + 0.9 * 0.7) / 1.7)


def test_weighted_mean_and_sample_size():
    post = aggregate([
        _obs("m", "validation", 1.0),
        _obs("m", "validation", 1.0),
    ])[("m", "implementer/high", "quality")]
    assert post.value == pytest.approx(1.0)
    assert post.sample_size == pytest.approx(2.0)   # 2 × weight 1.0
    assert post.n_observations == 2


# ── D9: exponential decay ────────────────────────────────────────────────────

def test_decay_halves_weight_at_one_half_life():
    fresh = aggregate([_obs("m", "validation", 1.0, age=0.0)], half_life_days=30)
    aged = aggregate([_obs("m", "validation", 1.0, age=30.0)], half_life_days=30)
    fresh_ss = fresh[("m", "implementer/high", "quality")].sample_size
    aged_ss = aged[("m", "implementer/high", "quality")].sample_size
    assert aged_ss == pytest.approx(fresh_ss * 0.5)


def test_recent_observation_dominates_stale_one():
    """A recent low score outweighs a stale high score of equal source."""
    post = aggregate([
        _obs("m", "validation", 1.0, age=90.0),   # very stale
        _obs("m", "validation", 0.2, age=0.0),    # fresh
    ], half_life_days=30)[("m", "implementer/high", "quality")]
    assert post.value < 0.5


def test_empty_observations_yield_empty():
    assert aggregate([]) == {}


# ── task 5.3: roadmap-record normalizers ─────────────────────────────────────

def test_normalize_vendor_switch_uses_observed_deltas():
    rec = {
        "from_vendor": "claude", "to_vendor": "codex",
        "expected_cost_delta_usd": -0.5, "observed_cost_delta_usd": -0.3,
        "observed_latency_delta_seconds": 4.0,
    }
    obs = normalize_vendor_switch(rec, task_type="implementer/high")
    by_metric = {o.metric: o for o in obs}
    assert by_metric["cost_delta_usd"].value == -0.3   # observed, not expected
    assert by_metric["cost_delta_usd"].model_id == "codex"
    assert by_metric["cost_delta_usd"].source == "vendor-switch"
    assert by_metric["latency_delta_seconds"].value == 4.0


def test_normalize_vendor_switch_without_vendor_is_empty():
    assert normalize_vendor_switch({"observed_cost_delta_usd": -0.3}, "t") == []


def test_normalize_vendor_notes_capability_gaps_lower_quality():
    clean = normalize_vendor_notes({"vendor": "codex", "capability_gaps": []}, "t")
    gappy = normalize_vendor_notes(
        {"vendor": "codex", "capability_gaps": ["g1", "g2", "g3"]}, "t"
    )
    q_clean = next(o.value for o in clean if o.metric == "quality")
    q_gappy = next(o.value for o in gappy if o.metric == "quality")
    assert q_clean == 1.0
    assert q_gappy < q_clean


def test_normalize_vendor_notes_maps_cost_and_latency():
    obs = normalize_vendor_notes(
        {"vendor": "gemini", "cost_observed_usd": 0.42, "latency_observed_seconds": 12.0},
        task_type="runner/low",
    )
    metrics = {o.metric: o.value for o in obs}
    assert metrics["cost_per_task_usd"] == 0.42
    assert metrics["latency_seconds"] == 12.0
    assert all(o.model_id == "gemini" for o in obs)


def test_normalizers_feed_aggregate_end_to_end():
    """Observations from both roadmap sources aggregate for the same model."""
    obs = normalize_vendor_notes(
        {"vendor": "codex", "cost_observed_usd": 0.5}, "implementer/high"
    ) + normalize_vendor_switch(
        {"to_vendor": "codex", "observed_cost_delta_usd": -0.1}, "implementer/high"
    )
    post = aggregate(obs)
    assert ("codex", "implementer/high", "cost_per_task_usd") in post
    assert ("codex", "implementer/high", "cost_delta_usd") in post

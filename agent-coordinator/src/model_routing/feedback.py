"""Feedback posterior aggregation (design D9).

Pure aggregation core — folds weighted, time-decayed feedback observations into
per-``(model_id, task_type, metric)`` posteriors that the resolver consumes via
``blend_quality`` / ``effective_cost``. No DB or network: the coordinator job
(wp-feedback wiring) reads observations from episodic memory / learning-logs and
persists the returned estimates into ``model_posteriors``.

Source weighting (rev2, from the Databricks benchmark insight): deterministic
verification outcomes outrank LLM-judged scores, which outrank coarse counters
and inferred signals. LLM judging "rewards sounding right over being right", so
held-out-test / CI / vendor-switch outcomes carry full weight and gen-eval's
semantic-judge output is discounted.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

# Metrics bounded to [0, 1]; and metrics that must be non-negative (delta metrics may
# legitimately be negative, so they are NOT range-checked beyond finiteness).
_UNIT_INTERVAL_METRICS = frozenset({"quality", "success_rate"})
_NON_NEGATIVE_METRICS = frozenset({"cost_per_task_usd", "latency_seconds"})


def _observation_value_is_sane(metric: str, value: float) -> bool:
    """Reject non-finite or out-of-range feedback values before aggregation."""
    if not math.isfinite(value):
        return False
    if metric in _UNIT_INTERVAL_METRICS and not (0.0 <= value <= 1.0):
        return False
    if metric in _NON_NEGATIVE_METRICS and value < 0.0:
        return False
    return True

# Deterministic verification (1.0) > LLM-judged (0.7) > coarse (0.5) > inferred
# (0.3). Keys match the FeedbackEvent.source contract enum (design D9).
SOURCE_WEIGHTS: dict[str, float] = {
    "validation": 1.0,        # held-out tests / CI — deterministic
    "vendor-switch": 1.0,     # observed expected-vs-observed deltas — deterministic
    "gen-eval": 0.7,          # includes a semantic (LLM) judge; discounted
    "procedural-memory": 0.5,  # coarse success/failure counters
    "transcript-triage": 0.3,  # inferred struggle signals
}
DEFAULT_HALF_LIFE_DAYS = 30.0


@dataclass(frozen=True)
class FeedbackObservation:
    """One normalized feedback datum for a (model, task_type, metric)."""

    model_id: str
    task_type: str
    metric: str          # quality | success_rate | cost_per_task_usd | latency_seconds
    value: float
    source: str
    age_days: float = 0.0
    tokens_estimated: bool = False


@dataclass(frozen=True)
class PosteriorEstimate:
    """Aggregated posterior: decayed weighted mean + effective sample size."""

    value: float
    sample_size: float   # sum of decayed source weights → resolver confidence input
    n_observations: int


def _decayed_weight(source: str, age_days: float, half_life_days: float) -> float:
    base = SOURCE_WEIGHTS.get(source, 0.3)
    if half_life_days <= 0:
        return base
    return float(base * (0.5 ** (age_days / half_life_days)))


def aggregate(
    observations: list[FeedbackObservation],
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> dict[tuple[str, str, str], PosteriorEstimate]:
    """Fold observations into per-(model, task_type, metric) posteriors.

    Weighted mean ``Σ(w·v)/Σw`` with ``w`` = source weight × exponential decay;
    ``sample_size`` = ``Σw`` (effective decayed samples), which drives the
    resolver's prior/posterior confidence blend.
    """
    num: dict[tuple[str, str, str], float] = defaultdict(float)
    den: dict[tuple[str, str, str], float] = defaultdict(float)
    counts: dict[tuple[str, str, str], int] = defaultdict(int)

    for o in observations:
        if not _observation_value_is_sane(o.metric, o.value):
            # Reject malformed/hostile inputs before they poison the posteriors that
            # route future work: non-finite (NaN/inf), bounded metrics outside 0..1,
            # or negative cost/latency.
            continue
        w = _decayed_weight(o.source, o.age_days, half_life_days)
        if w <= 0:
            continue
        key = (o.model_id, o.task_type, o.metric)
        num[key] += w * o.value
        den[key] += w
        counts[key] += 1

    return {
        key: PosteriorEstimate(
            value=num[key] / den[key],
            sample_size=den[key],
            n_observations=counts[key],
        )
        for key in den
    }


# ── Normalizers: roadmap-workspace records → observations (task 5.3) ──────────

def normalize_vendor_switch(
    record: dict[str, Any], task_type: str, age_days: float = 0.0
) -> list[FeedbackObservation]:
    """Map a ``VendorSwitch`` record to observations for its ``to_vendor``.

    Uses observed (not expected) deltas — the realized signal (deterministic,
    weight 1.0). Cost/latency deltas are recorded as calibration-error metrics.
    """
    to_vendor = record.get("to_vendor")
    if not to_vendor:
        return []
    out: list[FeedbackObservation] = []
    obs_cost = record.get("observed_cost_delta_usd")
    if obs_cost is not None:
        out.append(FeedbackObservation(
            model_id=to_vendor, task_type=task_type, metric="cost_delta_usd",
            value=float(obs_cost), source="vendor-switch", age_days=age_days,
        ))
    obs_lat = record.get("observed_latency_delta_seconds")
    if obs_lat is not None:
        out.append(FeedbackObservation(
            model_id=to_vendor, task_type=task_type, metric="latency_delta_seconds",
            value=float(obs_lat), source="vendor-switch", age_days=age_days,
        ))
    return out


def normalize_vendor_notes(
    record: dict[str, Any], task_type: str, age_days: float = 0.0
) -> list[FeedbackObservation]:
    """Map a learning-log ``vendor_notes`` object to observations.

    ``capability_gaps`` presence lowers the observed quality signal; observed
    cost/latency feed the corresponding metrics.
    """
    vendor = record.get("vendor")
    if not vendor:
        return []
    out: list[FeedbackObservation] = []
    cost = record.get("cost_observed_usd")
    if cost is not None:
        out.append(FeedbackObservation(
            model_id=vendor, task_type=task_type, metric="cost_per_task_usd",
            value=float(cost), source="validation", age_days=age_days,
        ))
    lat = record.get("latency_observed_seconds")
    if lat is not None:
        out.append(FeedbackObservation(
            model_id=vendor, task_type=task_type, metric="latency_seconds",
            value=float(lat), source="validation", age_days=age_days,
        ))
    gaps = record.get("capability_gaps") or []
    # A capability gap is a quality signal: 1.0 clean, lower as gaps accrue.
    quality = 1.0 / (1.0 + len(gaps))
    out.append(FeedbackObservation(
        model_id=vendor, task_type=task_type, metric="quality",
        value=quality, source="validation", age_days=age_days,
    ))
    return out

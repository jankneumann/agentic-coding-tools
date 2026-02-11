"""Ablation runner for coordination mechanism evaluation.

Iterates over toggle combinations to measure individual
mechanism contributions. Supports full and fractional factorial designs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from itertools import product as itertools_product
from typing import Any

from .config import AblationFlags
from .metrics import AggregatedMetrics, TrialMetrics, compute_effect_size

logger = logging.getLogger(__name__)


@dataclass
class AblationComparison:
    """Comparison of a mechanism's contribution vs baseline."""

    mechanism: str
    baseline_label: str
    ablated_label: str
    wall_clock_delta: AggregatedMetrics = field(default_factory=AggregatedMetrics)
    success_rate_delta: float = 0.0
    test_pass_rate_delta: float = 0.0
    effect_size: float = 0.0
    interpretation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mechanism": self.mechanism,
            "baseline_label": self.baseline_label,
            "ablated_label": self.ablated_label,
            "wall_clock_delta": self.wall_clock_delta.to_dict(),
            "success_rate_delta": round(self.success_rate_delta, 4),
            "test_pass_rate_delta": round(self.test_pass_rate_delta, 4),
            "effect_size": round(self.effect_size, 4),
            "interpretation": self.interpretation,
        }


def generate_ablation_configs(
    fractional: bool = True,
) -> list[AblationFlags]:
    """Generate ablation configurations.

    Args:
        fractional: If True, generate 8 key configs (fractional factorial).
                    If False, generate all 32 configs (full factorial).

    Returns:
        List of AblationFlags configurations.
    """
    if not fractional:
        # Full factorial: all 2^5 = 32 combinations
        configs = []
        mechanisms = ["locking", "memory", "handoffs", "parallelization", "work_queue"]
        for combo in itertools_product([True, False], repeat=5):
            flags = dict(zip(mechanisms, combo))
            configs.append(AblationFlags.from_dict(flags))
        return configs

    # Fractional factorial: 8 key configurations
    return [
        AblationFlags.all_on(),                                    # Baseline: all on
        AblationFlags.all_off(),                                   # All off
        AblationFlags(locking=False),                              # Ablate locking
        AblationFlags(memory=False),                               # Ablate memory
        AblationFlags(handoffs=False),                             # Ablate handoffs
        AblationFlags(parallelization=False),                      # Ablate parallelization
        AblationFlags(work_queue=False),                           # Ablate work queue
        AblationFlags(locking=False, memory=False, handoffs=False),  # Only parallel + queue
    ]


def compare_ablations(
    trial_metrics: list[TrialMetrics],
    baseline_label: str = "all-on",
) -> list[AblationComparison]:
    """Compare ablation results against baseline.

    Computes per-mechanism contribution by measuring the delta
    between baseline (all mechanisms on) and each ablated config.

    Args:
        trial_metrics: Aggregated metrics from evaluation run.
        baseline_label: Label of the baseline configuration.

    Returns:
        List of AblationComparison per mechanism.
    """
    # Group by ablation label
    by_label: dict[str, list[TrialMetrics]] = {}
    for tm in trial_metrics:
        by_label.setdefault(tm.ablation_label, []).append(tm)

    baseline_metrics = by_label.get(baseline_label, [])
    if not baseline_metrics:
        logger.warning("No baseline metrics found for label: %s", baseline_label)
        return []

    comparisons = []
    for label, metrics in by_label.items():
        if label == baseline_label:
            continue

        # Identify which mechanism was toggled off
        mechanism = infer_mechanism(label)

        # Compute deltas
        baseline_wall_clocks = [tm.wall_clock.mean for tm in baseline_metrics]
        ablated_wall_clocks = [tm.wall_clock.mean for tm in metrics]

        baseline_success = (
            sum(tm.success_rate for tm in baseline_metrics) / len(baseline_metrics)
            if baseline_metrics else 0.0
        )
        ablated_success = (
            sum(tm.success_rate for tm in metrics) / len(metrics)
            if metrics else 0.0
        )

        baseline_pass_rate = (
            sum(tm.test_pass_rate.mean for tm in baseline_metrics) / len(baseline_metrics)
            if baseline_metrics else 0.0
        )
        ablated_pass_rate = (
            sum(tm.test_pass_rate.mean for tm in metrics) / len(metrics)
            if metrics else 0.0
        )

        effect = compute_effect_size(baseline_wall_clocks, ablated_wall_clocks)

        comparisons.append(AblationComparison(
            mechanism=mechanism,
            baseline_label=baseline_label,
            ablated_label=label,
            wall_clock_delta=AggregatedMetrics.from_values(
                [b - a for b, a in zip(baseline_wall_clocks, ablated_wall_clocks)]
                if len(baseline_wall_clocks) == len(ablated_wall_clocks)
                else []
            ),
            success_rate_delta=baseline_success - ablated_success,
            test_pass_rate_delta=baseline_pass_rate - ablated_pass_rate,
            effect_size=effect,
            interpretation=interpret_effect_size(effect),
        ))

    return comparisons


def infer_mechanism(label: str) -> str:
    """Infer which mechanism was ablated from the config label."""
    if label == "all-off":
        return "all"
    if label.startswith("only-"):
        remaining = label[5:]
        all_mechs = {"locking", "memory", "handoffs", "parallelization", "work_queue"}
        on_mechs = set(remaining.split("+"))
        off_mechs = all_mechs - on_mechs
        return "+".join(sorted(off_mechs))
    return label


def interpret_effect_size(d: float) -> str:
    """Interpret Cohen's d effect size."""
    abs_d = abs(d)
    if abs_d < 0.2:
        return "negligible"
    elif abs_d < 0.5:
        return "small"
    elif abs_d < 0.8:
        return "medium"
    else:
        return "large"

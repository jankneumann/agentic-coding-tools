"""Tests for ablation support."""

import pytest

from evaluation.ablation import (
    AblationComparison,
    compare_ablations,
    generate_ablation_configs,
)
from evaluation.metrics import AggregatedMetrics, TrialMetrics


class TestGenerateAblationConfigs:
    def test_fractional(self):
        configs = generate_ablation_configs(fractional=True)
        assert len(configs) == 8
        # First should be all-on
        assert configs[0].label() == "all-on"
        # Second should be all-off
        assert configs[1].label() == "all-off"

    def test_full_factorial(self):
        configs = generate_ablation_configs(fractional=False)
        assert len(configs) == 32  # 2^5

    def test_fractional_includes_single_ablations(self):
        configs = generate_ablation_configs(fractional=True)
        labels = [c.label() for c in configs]
        # Should have individual mechanism ablations
        assert any("locking" not in lab and "only-" in lab for lab in labels)


class TestCompareAblations:
    def test_basic_comparison(self):
        trial_metrics = [
            TrialMetrics(
                task_id="t1", backend_name="b1", ablation_label="all-on",
                num_trials=3, success_rate=1.0,
                wall_clock=AggregatedMetrics.from_values([10.0, 11.0, 12.0]),
                test_pass_rate=AggregatedMetrics.from_values([0.9, 0.9, 0.9]),
            ),
            TrialMetrics(
                task_id="t1", backend_name="b1",
                ablation_label="only-memory+handoffs+parallelization+work_queue",
                num_trials=3, success_rate=0.8,
                wall_clock=AggregatedMetrics.from_values([15.0, 16.0, 14.0]),
                test_pass_rate=AggregatedMetrics.from_values([0.7, 0.7, 0.7]),
            ),
        ]

        comparisons = compare_ablations(trial_metrics)
        assert len(comparisons) == 1
        assert comparisons[0].success_rate_delta == pytest.approx(0.2)

    def test_no_baseline(self):
        trial_metrics = [
            TrialMetrics(
                task_id="t1", backend_name="b1", ablation_label="custom",
                num_trials=1, success_rate=1.0,
                wall_clock=AggregatedMetrics.from_values([10.0]),
                test_pass_rate=AggregatedMetrics.from_values([0.9]),
            ),
        ]

        comparisons = compare_ablations(trial_metrics)
        assert len(comparisons) == 0

    def test_comparison_to_dict(self):
        comp = AblationComparison(
            mechanism="locking",
            baseline_label="all-on",
            ablated_label="no-locking",
            success_rate_delta=0.1,
            effect_size=0.5,
            interpretation="medium",
        )
        d = comp.to_dict()
        assert d["mechanism"] == "locking"
        assert d["effect_size"] == 0.5

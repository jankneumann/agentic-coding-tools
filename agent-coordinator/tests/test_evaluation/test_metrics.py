"""Tests for metrics collection and aggregation."""

import pytest

from evaluation.metrics import (
    AggregatedMetrics,
    MetricsCollector,
    TaskMetrics,
    TokenUsage,
    TrialMetrics,
    compute_effect_size,
)


class TestTokenUsage:
    def test_addition(self):
        a = TokenUsage(
            input_tokens=100, output_tokens=50, total_tokens=150,
            estimated_cost_usd=0.01,
        )
        b = TokenUsage(
            input_tokens=200, output_tokens=100, total_tokens=300,
            estimated_cost_usd=0.02,
        )
        result = a + b
        assert result.input_tokens == 300
        assert result.output_tokens == 150
        assert result.total_tokens == 450
        assert result.estimated_cost_usd == pytest.approx(0.03)


class TestAggregatedMetrics:
    def test_empty(self):
        agg = AggregatedMetrics.from_values([])
        assert agg.count == 0
        assert agg.mean == 0.0

    def test_single_value(self):
        agg = AggregatedMetrics.from_values([5.0])
        assert agg.count == 1
        assert agg.mean == 5.0
        assert agg.median == 5.0
        assert agg.std_dev == 0.0

    def test_multiple_values(self):
        values = [10.0, 20.0, 30.0]
        agg = AggregatedMetrics.from_values(values)
        assert agg.count == 3
        assert agg.mean == 20.0
        assert agg.median == 20.0
        assert agg.std_dev > 0
        assert agg.ci_lower < agg.mean
        assert agg.ci_upper > agg.mean

    def test_to_dict(self):
        agg = AggregatedMetrics.from_values([1.0, 2.0, 3.0])
        d = agg.to_dict()
        assert "count" in d
        assert "mean" in d
        assert "ci_95_lower" in d
        assert "ci_95_upper" in d


class TestMetricsCollector:
    def test_start_and_finish_task(self):
        collector = MetricsCollector()
        metrics = collector.start_task("task-1", 1, "claude_code", "all-on")
        assert metrics.task_id == "task-1"

        result = collector.finish_task()
        assert result is not None
        assert result.task_id == "task-1"

    def test_time_operation(self):
        collector = MetricsCollector()
        collector.start_task("task-1", 1, "claude_code", "all-on")

        with collector.time_operation("lock_acquire", file="test.py"):
            pass  # Simulated operation

        result = collector.finish_task()
        assert result is not None
        assert len(result.timings) == 1
        assert result.timings[0].operation == "lock_acquire"
        assert result.timings[0].duration_seconds >= 0

    def test_record_tokens(self):
        collector = MetricsCollector()
        collector.start_task("task-1", 1, "claude_code", "all-on")
        collector.record_tokens(TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150))
        collector.record_tokens(TokenUsage(input_tokens=200, output_tokens=100, total_tokens=300))

        result = collector.finish_task()
        assert result is not None
        assert result.token_usage.total_tokens == 450

    def test_record_correctness(self):
        collector = MetricsCollector()
        collector.start_task("task-1", 1, "claude_code", "all-on")
        collector.record_correctness(tests_total=10, tests_passed=8)

        result = collector.finish_task()
        assert result is not None
        assert result.correctness.test_pass_rate == pytest.approx(0.8)

    def test_record_lock_events(self):
        collector = MetricsCollector()
        collector.start_task("task-1", 1, "claude_code", "all-on")
        collector.record_lock_event(contention=False)
        collector.record_lock_event(contention=True)
        collector.record_lock_event(contention=False)

        result = collector.finish_task()
        assert result is not None
        assert result.coordination.lock_acquisitions == 3
        assert result.coordination.lock_contentions == 1
        assert result.coordination.lock_contention_rate == pytest.approx(1.0 / 3.0)

    def test_record_memory_events(self):
        collector = MetricsCollector()
        collector.start_task("task-1", 1, "claude_code", "all-on")
        collector.record_memory_event(hit=True)
        collector.record_memory_event(hit=False)

        result = collector.finish_task()
        assert result is not None
        assert result.coordination.memory_reads == 2
        assert result.coordination.memory_hits == 1
        assert result.coordination.memory_hit_rate == pytest.approx(0.5)

    def test_record_parallelization(self):
        collector = MetricsCollector()
        collector.start_task("task-1", 1, "claude_code", "all-on")
        collector.record_parallelization(
            sequential_time=30.0,
            parallel_time=10.0,
            num_agents=3,
            merge_conflicts=1,
            total_subtasks=5,
        )

        result = collector.finish_task()
        assert result is not None
        assert result.parallelization.speedup_factor == pytest.approx(3.0)
        assert result.parallelization.amdahl_efficiency == pytest.approx(1.0)
        assert result.parallelization.merge_conflict_rate == pytest.approx(0.2)

    def test_coordination_overhead(self):
        import time

        collector = MetricsCollector()
        metrics = collector.start_task("task-1", 1, "claude_code", "all-on")
        metrics.wall_clock_seconds = 10.0

        # Simulate coordination timing
        metrics.timings.append(
            __import__("evaluation.metrics", fromlist=["TimingMetric"]).TimingMetric(
                operation="lock_acquire",
                duration_seconds=2.0,
                timestamp=time.time(),
            )
        )
        metrics.timings.append(
            __import__("evaluation.metrics", fromlist=["TimingMetric"]).TimingMetric(
                operation="memory_read",
                duration_seconds=1.0,
                timestamp=time.time(),
            )
        )

        result = collector.finish_task()
        assert result is not None
        assert result.coordination_overhead_pct == pytest.approx(30.0)

    def test_get_trial_metrics(self):
        collector = MetricsCollector()

        # Two trials for same task
        for trial in range(1, 3):
            m = collector.start_task("task-1", trial, "claude_code", "all-on")
            m.wall_clock_seconds = 10.0 + trial
            m.success = True
            collector.finish_task()

        trials = collector.get_trial_metrics()
        assert len(trials) == 1
        assert trials[0].num_trials == 2
        assert trials[0].success_rate == 1.0

    def test_clear(self):
        collector = MetricsCollector()
        collector.start_task("task-1", 1, "claude_code", "all-on")
        collector.finish_task()
        assert len(collector.get_all_metrics()) == 1

        collector.clear()
        assert len(collector.get_all_metrics()) == 0


class TestEffectSize:
    def test_identical_groups(self):
        d = compute_effect_size([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        assert d == pytest.approx(0.0)

    def test_large_difference(self):
        d = compute_effect_size([10.0, 11.0, 12.0], [1.0, 2.0, 3.0])
        assert abs(d) > 0.8  # Large effect

    def test_empty_groups(self):
        assert compute_effect_size([], [1.0, 2.0]) == 0.0
        assert compute_effect_size([1.0], [2.0]) == 0.0  # n < 2


class TestTrialMetrics:
    def test_from_task_metrics(self):
        metrics_list = []
        for i in range(3):
            m = TaskMetrics(
                task_id="task-1",
                trial_num=i + 1,
                backend_name="claude_code",
                ablation_label="all-on",
                wall_clock_seconds=10.0 + i,
                success=i < 2,  # 2 out of 3 succeed
            )
            m.token_usage = TokenUsage(total_tokens=100 * (i + 1))
            m.correctness.test_pass_rate = 0.8 + i * 0.05
            metrics_list.append(m)

        trial = TrialMetrics.from_task_metrics(metrics_list)
        assert trial.num_trials == 3
        assert trial.success_rate == pytest.approx(2 / 3)
        assert trial.wall_clock.mean == pytest.approx(11.0)

    def test_to_dict(self):
        trial = TrialMetrics(
            task_id="task-1",
            backend_name="claude_code",
            ablation_label="all-on",
        )
        d = trial.to_dict()
        assert d["task_id"] == "task-1"
        assert "wall_clock" in d
        assert "success_rate" in d

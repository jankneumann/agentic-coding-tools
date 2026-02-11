"""Metrics collection and aggregation for evaluation runs.

Captures timing, token usage, correctness, coordination overhead,
and parallelization metrics. Provides statistical aggregation
across trials with confidence intervals and effect sizes.
"""

from __future__ import annotations

import math
import statistics
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TimingMetric:
    """A single timing measurement."""

    operation: str  # e.g. "lock_acquire", "memory_read", "task_execute"
    duration_seconds: float
    timestamp: float  # time.time() when measurement started
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenUsage:
    """Token usage for a single API call."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            estimated_cost_usd=self.estimated_cost_usd + other.estimated_cost_usd,
        )


@dataclass
class CorrectnessMetrics:
    """Correctness measurements for a task execution."""

    tests_total: int = 0
    tests_passed: int = 0
    test_pass_rate: float = 0.0
    patch_match_ratio: float = 0.0  # Similarity to golden patch (0.0 - 1.0)
    spec_compliance_score: float = 0.0  # Spec compliance (0.0 - 1.0)


@dataclass
class CoordinationMetrics:
    """Metrics about coordination mechanism usage."""

    lock_acquisitions: int = 0
    lock_contentions: int = 0
    lock_contention_rate: float = 0.0
    memory_reads: int = 0
    memory_hits: int = 0
    memory_hit_rate: float = 0.0
    handoff_count: int = 0
    handoff_continuity_score: float = 0.0
    dead_agent_recoveries: int = 0
    dead_agent_recovery_time_seconds: float = 0.0

    def compute_rates(self) -> None:
        """Compute derived rates from raw counts."""
        if self.lock_acquisitions > 0:
            self.lock_contention_rate = self.lock_contentions / self.lock_acquisitions
        if self.memory_reads > 0:
            self.memory_hit_rate = self.memory_hits / self.memory_reads


@dataclass
class ParallelizationMetrics:
    """Metrics about parallelization performance."""

    sequential_time_seconds: float = 0.0
    parallel_time_seconds: float = 0.0
    speedup_factor: float = 1.0  # parallel/sequential (>1 means faster)
    amdahl_efficiency: float = 0.0  # Speedup / number of parallel agents
    merge_conflicts: int = 0
    merge_conflict_rate: float = 0.0
    num_parallel_agents: int = 1


@dataclass
class TaskMetrics:
    """Complete metrics for a single task execution."""

    task_id: str
    trial_num: int
    backend_name: str
    ablation_label: str
    wall_clock_seconds: float = 0.0
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    correctness: CorrectnessMetrics = field(default_factory=CorrectnessMetrics)
    coordination: CoordinationMetrics = field(default_factory=CoordinationMetrics)
    parallelization: ParallelizationMetrics = field(
        default_factory=ParallelizationMetrics
    )
    coordination_overhead_pct: float = 0.0  # Time in coordination vs productive work
    timings: list[TimingMetric] = field(default_factory=list)
    success: bool = False
    output: str = ""  # Agent's produced output (patch, code, etc.)
    error: str | None = None

    def compute_coordination_overhead(self) -> None:
        """Compute coordination overhead from timing measurements."""
        coord_ops = {"lock_acquire", "lock_release", "memory_read", "memory_write",
                     "handoff_write", "handoff_read", "queue_claim", "queue_complete"}
        coord_time = sum(
            t.duration_seconds for t in self.timings if t.operation in coord_ops
        )
        if self.wall_clock_seconds > 0:
            self.coordination_overhead_pct = (coord_time / self.wall_clock_seconds) * 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "trial_num": self.trial_num,
            "backend_name": self.backend_name,
            "ablation_label": self.ablation_label,
            "wall_clock_seconds": self.wall_clock_seconds,
            "token_usage": {
                "input_tokens": self.token_usage.input_tokens,
                "output_tokens": self.token_usage.output_tokens,
                "total_tokens": self.token_usage.total_tokens,
                "estimated_cost_usd": self.token_usage.estimated_cost_usd,
            },
            "correctness": {
                "tests_total": self.correctness.tests_total,
                "tests_passed": self.correctness.tests_passed,
                "test_pass_rate": self.correctness.test_pass_rate,
                "patch_match_ratio": self.correctness.patch_match_ratio,
                "spec_compliance_score": self.correctness.spec_compliance_score,
            },
            "coordination": {
                "lock_contention_rate": self.coordination.lock_contention_rate,
                "memory_hit_rate": self.coordination.memory_hit_rate,
                "handoff_continuity_score": self.coordination.handoff_continuity_score,
            },
            "parallelization": {
                "speedup_factor": self.parallelization.speedup_factor,
                "amdahl_efficiency": self.parallelization.amdahl_efficiency,
                "merge_conflict_rate": self.parallelization.merge_conflict_rate,
            },
            "coordination_overhead_pct": self.coordination_overhead_pct,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class AggregatedMetrics:
    """Statistical aggregation of metrics across multiple trials."""

    count: int = 0
    mean: float = 0.0
    median: float = 0.0
    std_dev: float = 0.0
    ci_lower: float = 0.0  # 95% confidence interval lower bound
    ci_upper: float = 0.0  # 95% confidence interval upper bound

    @classmethod
    def from_values(cls, values: list[float]) -> AggregatedMetrics:
        """Compute aggregated statistics from a list of values."""
        if not values:
            return cls()
        n = len(values)
        mean = statistics.mean(values)
        median = statistics.median(values)
        std_dev = statistics.stdev(values) if n > 1 else 0.0

        # 95% CI using t-distribution approximation
        if n > 1:
            se = std_dev / math.sqrt(n)
            # Use 1.96 for large n, approximate with 2.0 for small n
            t_val = 2.0 if n < 30 else 1.96
            ci_lower = mean - t_val * se
            ci_upper = mean + t_val * se
        else:
            ci_lower = mean
            ci_upper = mean

        return cls(
            count=n,
            mean=mean,
            median=median,
            std_dev=std_dev,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "mean": round(self.mean, 4),
            "median": round(self.median, 4),
            "std_dev": round(self.std_dev, 4),
            "ci_95_lower": round(self.ci_lower, 4),
            "ci_95_upper": round(self.ci_upper, 4),
        }


@dataclass
class TrialMetrics:
    """Metrics aggregated across trials for a specific configuration."""

    task_id: str
    backend_name: str
    ablation_label: str
    num_trials: int = 0
    wall_clock: AggregatedMetrics = field(default_factory=AggregatedMetrics)
    total_tokens: AggregatedMetrics = field(default_factory=AggregatedMetrics)
    cost_usd: AggregatedMetrics = field(default_factory=AggregatedMetrics)
    test_pass_rate: AggregatedMetrics = field(default_factory=AggregatedMetrics)
    coordination_overhead: AggregatedMetrics = field(default_factory=AggregatedMetrics)
    speedup_factor: AggregatedMetrics = field(default_factory=AggregatedMetrics)
    success_rate: float = 0.0

    @classmethod
    def from_task_metrics(cls, metrics_list: list[TaskMetrics]) -> TrialMetrics:
        """Aggregate a list of TaskMetrics from multiple trials."""
        if not metrics_list:
            return cls(task_id="", backend_name="", ablation_label="")

        first = metrics_list[0]
        n = len(metrics_list)
        successes = sum(1 for m in metrics_list if m.success)

        return cls(
            task_id=first.task_id,
            backend_name=first.backend_name,
            ablation_label=first.ablation_label,
            num_trials=n,
            wall_clock=AggregatedMetrics.from_values(
                [m.wall_clock_seconds for m in metrics_list]
            ),
            total_tokens=AggregatedMetrics.from_values(
                [float(m.token_usage.total_tokens) for m in metrics_list]
            ),
            cost_usd=AggregatedMetrics.from_values(
                [m.token_usage.estimated_cost_usd for m in metrics_list]
            ),
            test_pass_rate=AggregatedMetrics.from_values(
                [m.correctness.test_pass_rate for m in metrics_list]
            ),
            coordination_overhead=AggregatedMetrics.from_values(
                [m.coordination_overhead_pct for m in metrics_list]
            ),
            speedup_factor=AggregatedMetrics.from_values(
                [m.parallelization.speedup_factor for m in metrics_list]
            ),
            success_rate=successes / n if n > 0 else 0.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "backend_name": self.backend_name,
            "ablation_label": self.ablation_label,
            "num_trials": self.num_trials,
            "success_rate": round(self.success_rate, 4),
            "wall_clock": self.wall_clock.to_dict(),
            "total_tokens": self.total_tokens.to_dict(),
            "cost_usd": self.cost_usd.to_dict(),
            "test_pass_rate": self.test_pass_rate.to_dict(),
            "coordination_overhead": self.coordination_overhead.to_dict(),
            "speedup_factor": self.speedup_factor.to_dict(),
        }


def compute_effect_size(group_a: list[float], group_b: list[float]) -> float:
    """Compute Cohen's d effect size between two groups.

    Returns:
        Cohen's d: Small (~0.2), Medium (~0.5), Large (~0.8)
    """
    if not group_a or not group_b:
        return 0.0
    mean_a = statistics.mean(group_a)
    mean_b = statistics.mean(group_b)
    n_a, n_b = len(group_a), len(group_b)

    if n_a < 2 or n_b < 2:
        return 0.0

    var_a = statistics.variance(group_a)
    var_b = statistics.variance(group_b)
    pooled_std = math.sqrt(((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2))

    if pooled_std == 0:
        return 0.0
    return (mean_a - mean_b) / pooled_std


class MetricsCollector:
    """Collects metrics during evaluation runs.

    Provides context managers for timing coordination operations
    and methods for recording token usage and correctness scores.
    """

    def __init__(self) -> None:
        self._current_metrics: TaskMetrics | None = None
        self._all_metrics: list[TaskMetrics] = []

    def start_task(
        self,
        task_id: str,
        trial_num: int,
        backend_name: str,
        ablation_label: str,
    ) -> TaskMetrics:
        """Begin collecting metrics for a task execution."""
        self._current_metrics = TaskMetrics(
            task_id=task_id,
            trial_num=trial_num,
            backend_name=backend_name,
            ablation_label=ablation_label,
        )
        return self._current_metrics

    def finish_task(self) -> TaskMetrics | None:
        """Finalize and store metrics for the current task."""
        if self._current_metrics is None:
            return None
        self._current_metrics.compute_coordination_overhead()
        self._current_metrics.coordination.compute_rates()
        self._all_metrics.append(self._current_metrics)
        result = self._current_metrics
        self._current_metrics = None
        return result

    @contextmanager
    def time_operation(
        self, operation: str, **metadata: Any
    ) -> Generator[TimingMetric, None, None]:
        """Context manager to time a coordination operation.

        Usage:
            with collector.time_operation("lock_acquire", file="src/main.py"):
                await lock_service.acquire(...)
        """
        start = time.time()
        metric = TimingMetric(
            operation=operation,
            duration_seconds=0.0,
            timestamp=start,
            metadata=dict(metadata),
        )
        try:
            yield metric
        finally:
            metric.duration_seconds = time.time() - start
            if self._current_metrics is not None:
                self._current_metrics.timings.append(metric)

    def record_tokens(self, usage: TokenUsage) -> None:
        """Record token usage for the current task."""
        if self._current_metrics is not None:
            self._current_metrics.token_usage = (
                self._current_metrics.token_usage + usage
            )

    def record_correctness(
        self,
        tests_total: int,
        tests_passed: int,
        patch_match_ratio: float = 0.0,
        spec_compliance_score: float = 0.0,
    ) -> None:
        """Record correctness metrics for the current task."""
        if self._current_metrics is not None:
            rate = tests_passed / tests_total if tests_total > 0 else 0.0
            self._current_metrics.correctness = CorrectnessMetrics(
                tests_total=tests_total,
                tests_passed=tests_passed,
                test_pass_rate=rate,
                patch_match_ratio=patch_match_ratio,
                spec_compliance_score=spec_compliance_score,
            )

    def record_lock_event(self, contention: bool = False) -> None:
        """Record a lock acquisition event."""
        if self._current_metrics is not None:
            self._current_metrics.coordination.lock_acquisitions += 1
            if contention:
                self._current_metrics.coordination.lock_contentions += 1

    def record_memory_event(self, hit: bool = True) -> None:
        """Record a memory read event."""
        if self._current_metrics is not None:
            self._current_metrics.coordination.memory_reads += 1
            if hit:
                self._current_metrics.coordination.memory_hits += 1

    def record_parallelization(
        self,
        sequential_time: float,
        parallel_time: float,
        num_agents: int,
        merge_conflicts: int = 0,
        total_subtasks: int = 1,
    ) -> None:
        """Record parallelization metrics."""
        if self._current_metrics is not None:
            speedup = sequential_time / parallel_time if parallel_time > 0 else 1.0
            efficiency = speedup / num_agents if num_agents > 0 else 0.0
            conflict_rate = merge_conflicts / total_subtasks if total_subtasks > 0 else 0.0
            self._current_metrics.parallelization = ParallelizationMetrics(
                sequential_time_seconds=sequential_time,
                parallel_time_seconds=parallel_time,
                speedup_factor=speedup,
                amdahl_efficiency=efficiency,
                merge_conflicts=merge_conflicts,
                merge_conflict_rate=conflict_rate,
                num_parallel_agents=num_agents,
            )

    def get_all_metrics(self) -> list[TaskMetrics]:
        """Get all collected task metrics."""
        return list(self._all_metrics)

    def get_trial_metrics(self) -> list[TrialMetrics]:
        """Aggregate metrics by (task_id, backend, ablation) across trials."""
        groups: dict[tuple[str, str, str], list[TaskMetrics]] = {}
        for m in self._all_metrics:
            key = (m.task_id, m.backend_name, m.ablation_label)
            groups.setdefault(key, []).append(m)

        return [TrialMetrics.from_task_metrics(ms) for ms in groups.values()]

    def clear(self) -> None:
        """Clear all collected metrics."""
        self._current_metrics = None
        self._all_metrics.clear()

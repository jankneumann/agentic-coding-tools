"""gen-eval scenario-level metrics.

This module contains exactly one public symbol -- ``GenEvalMetrics`` --
the per-scenario record consumed by ``gen_eval.reports``.

Surgically extracted from ``agent-coordinator/evaluation/metrics.py``
(per design decision D3). The other 10 metric classes
(``TimingMetric``, ``TokenUsage``, ``CorrectnessMetrics``,
``CoordinationMetrics``, ``SafetyMetrics``, ``ParallelizationMetrics``,
``TaskMetrics``, ``AggregatedMetrics``, ``TrialMetrics``,
``MetricsCollector``) and ``compute_effect_size`` are coordinator-domain
and stay in the coordinator. They are consumed only by
``agent-coordinator/evaluation/ablation.py``,
``agent-coordinator/evaluation/reports/generator.py``, and four
coordinator test files.

Adding any other PUBLIC symbol here is a scope violation and will fail
the surface test ``tests/test_metrics_surface.py``. To keep the public
surface minimal, all stdlib helpers are imported under leading-underscore
aliases.

Spec scenario: gen-eval-framework.module-discovery-and-import-boundary
Design decision: D3
"""

from __future__ import annotations as _annotations

from dataclasses import dataclass as _dataclass
from typing import Any as _Any


@_dataclass
class GenEvalMetrics:
    """Metrics for a single gen-eval scenario evaluation.

    Captures per-scenario timing, verdict, and backend information
    for integration with the MetricsCollector pipeline.
    """

    scenario_id: str
    interface: str
    verdict: str  # pass/fail/error
    duration_seconds: float
    category: str
    backend_used: str  # template/cli/sdk

    def to_dict(self) -> dict[str, _Any]:
        return {
            "scenario_id": self.scenario_id,
            "interface": self.interface,
            "verdict": self.verdict,
            "duration_seconds": self.duration_seconds,
            "category": self.category,
            "backend_used": self.backend_used,
        }


__all__ = ["GenEvalMetrics"]

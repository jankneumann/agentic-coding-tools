"""Evaluation framework for agent coordination benchmarking.

Provides scenario-driven benchmarking infrastructure to measure:
- Parallelization ROI (Task() vs sequential execution)
- Agent backend comparison (Claude Code, Codex, Gemini/Jules)
- Coordination mechanism value (locking, memory, handoffs, queue)
- Memory effectiveness across session boundaries
- Scaling behavior with varying agent counts
"""

from .config import AblationFlags, AgentBackendConfig, EvalConfig
from .harness import EvalHarness
from .metrics import MetricsCollector, TaskMetrics, TrialMetrics

__all__ = [
    "AblationFlags",
    "AgentBackendConfig",
    "EvalConfig",
    "EvalHarness",
    "MetricsCollector",
    "TaskMetrics",
    "TrialMetrics",
]

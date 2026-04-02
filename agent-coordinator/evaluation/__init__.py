"""Evaluation framework for agent coordination benchmarking.

Provides scenario-driven benchmarking infrastructure to measure:
- Parallelization ROI (Task() vs sequential execution)
- Agent backend comparison (Claude Code, Codex, Gemini/Jules)
- Coordination mechanism value (locking, memory, handoffs, queue)
- Memory effectiveness across session boundaries
- Scaling behavior with varying agent counts
"""

# Lazy import for gen_eval subpackage — import the module itself
# so consumers can do ``from evaluation import gen_eval`` or
# ``from evaluation.gen_eval import ...``.
from . import gen_eval as gen_eval  # noqa: E402
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
    "gen_eval",
]

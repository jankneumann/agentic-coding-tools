"""Task suite for evaluation benchmarking.

Provides a registry of reproducible coding tasks organized
by coordination complexity tier.
"""

from .registry import EvalTask, TaskRegistry

__all__ = ["EvalTask", "TaskRegistry"]

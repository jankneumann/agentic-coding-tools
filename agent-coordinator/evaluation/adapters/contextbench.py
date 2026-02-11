"""Context-Bench adapter.

Loads Letta Context-Bench tasks for evaluating
long-horizon context management and memory effectiveness.
Maps to the agent-coordinator's episodic and working memory subsystems.
"""

from __future__ import annotations

from typing import Any

from ..config import TaskSource, TaskTier
from ..tasks.registry import EvalTask, Subtask, TaskRegistry


class ContextBenchAdapter:
    """Adapter for Letta Context-Bench evaluation tasks.

    Loads multi-step context management tasks and maps them
    to evaluate memory subsystem effectiveness.
    """

    def __init__(self, registry: TaskRegistry) -> None:
        self._registry = registry

    def load_tasks(
        self,
        max_tasks: int | None = None,
    ) -> list[EvalTask]:
        """Load Context-Bench tasks and register them.

        Args:
            max_tasks: Maximum number of tasks to load.

        Returns:
            List of loaded EvalTask instances.
        """
        raw_tasks = self._fetch_tasks()

        if max_tasks and len(raw_tasks) > max_tasks:
            raw_tasks = raw_tasks[:max_tasks]

        tasks = []
        for raw in raw_tasks:
            task = self._convert_task(raw)
            self._registry.register(task)
            tasks.append(task)

        return tasks

    def _fetch_tasks(self) -> list[dict[str, Any]]:
        """Fetch Context-Bench tasks.

        Tries to load from the Letta benchmark dataset.
        Falls back to an empty list if unavailable.
        """
        try:
            from datasets import load_dataset
            ds = load_dataset("letta-ai/context-bench", split="test")
            return list(ds)
        except ImportError:
            return []
        except Exception:
            return []

    def _convert_task(self, raw: dict[str, Any]) -> EvalTask:
        """Convert a Context-Bench task to internal EvalTask format."""
        task_id = raw.get("id", raw.get("task_id", "unknown"))

        # Context-Bench tasks are multi-step memory challenges
        # They map to Tier 2 (parallelizable subtasks within a session)
        steps = raw.get("steps", [])
        subtasks = []
        for i, step in enumerate(steps):
            subtasks.append(Subtask(
                id=f"step-{i}",
                description=step if isinstance(step, str) else str(step),
                depends_on=[f"step-{i - 1}"] if i > 0 else [],
            ))

        return EvalTask(
            id=f"contextbench-{task_id}",
            tier=TaskTier.TIER2,
            source=TaskSource.CONTEXTBENCH,
            description=raw.get("description", raw.get("prompt", "")),
            difficulty=raw.get("difficulty", "medium"),
            subtasks=subtasks,
            tags=["contextbench", "memory"],
            metadata={
                "category": raw.get("category", ""),
                "expected_answer": raw.get("expected_answer", ""),
                "num_steps": len(steps),
            },
        )

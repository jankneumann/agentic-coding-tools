"""MultiAgentBench/MARBLE adapter.

Loads coordination scenarios from MultiAgentBench and maps
topology configurations to the agent-coordinator's Task()
parallel execution patterns.
"""

from __future__ import annotations

from typing import Any

from ..config import TaskSource, TaskTier
from ..tasks.registry import EvalTask, Subtask, TaskRegistry


class MARBLEAdapter:
    """Adapter for MultiAgentBench/MARBLE coordination scenarios.

    Maps multi-agent coordination topologies (star, chain, tree, graph)
    to evaluation tasks that test our Task() orchestration patterns.
    """

    def __init__(self, registry: TaskRegistry) -> None:
        self._registry = registry

    def load_tasks(
        self,
        max_tasks: int | None = None,
        topology_filter: str | None = None,
    ) -> list[EvalTask]:
        """Load MARBLE tasks and register them.

        Args:
            max_tasks: Maximum number of tasks to load.
            topology_filter: Filter by topology type (star, chain, tree, graph).

        Returns:
            List of loaded EvalTask instances.
        """
        raw_tasks = self._fetch_tasks()

        if topology_filter:
            raw_tasks = [
                t for t in raw_tasks
                if t.get("topology", "") == topology_filter
            ]

        if max_tasks and len(raw_tasks) > max_tasks:
            raw_tasks = raw_tasks[:max_tasks]

        tasks = []
        for raw in raw_tasks:
            task = self._convert_task(raw)
            self._registry.register(task)
            tasks.append(task)

        return tasks

    def _fetch_tasks(self) -> list[dict[str, Any]]:
        """Fetch MARBLE benchmark tasks.

        Tries to load from the MARBLE dataset.
        Falls back to an empty list if unavailable.
        """
        try:
            from datasets import load_dataset
            ds = load_dataset("MultiAgentBench/MARBLE", split="test")
            return list(ds)
        except ImportError:
            return []
        except Exception:
            return []

    def _convert_task(self, raw: dict[str, Any]) -> EvalTask:
        """Convert a MARBLE task to internal EvalTask format."""
        task_id = raw.get("id", raw.get("task_id", "unknown"))
        topology = raw.get("topology", "star")

        # Map topology to tier
        # star = parallelizable (Tier 2), chain/tree/graph = coordinated (Tier 3)
        tier = TaskTier.TIER2 if topology == "star" else TaskTier.TIER3

        # Extract agent roles as subtasks
        agents = raw.get("agents", [])
        subtasks = []
        for i, agent in enumerate(agents):
            agent_desc = agent if isinstance(agent, str) else agent.get("role", f"agent-{i}")
            deps = agent.get("depends_on", []) if isinstance(agent, dict) else []
            subtasks.append(Subtask(
                id=f"agent-{i}",
                description=agent_desc,
                depends_on=deps,
            ))

        return EvalTask(
            id=f"marble-{task_id}",
            tier=tier,
            source=TaskSource.MARBLE,
            description=raw.get("description", raw.get("scenario", "")),
            difficulty=raw.get("difficulty", "hard"),
            subtasks=subtasks,
            tags=["marble", f"topology-{topology}"],
            metadata={
                "topology": topology,
                "num_agents": len(agents),
                "milestones": raw.get("milestones", []),
            },
        )

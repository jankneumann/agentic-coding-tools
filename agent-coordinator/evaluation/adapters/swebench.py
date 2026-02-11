"""SWE-bench Verified adapter.

Loads task definitions from the HuggingFace dataset
'SWE-bench/SWE-bench_Verified' and converts them to
internal EvalTask format. Supports subset sampling.
"""

from __future__ import annotations

import random
from typing import Any

from ..config import TaskSource, TaskTier
from ..tasks.registry import EvalTask, TaskRegistry


class SWEBenchAdapter:
    """Adapter for SWE-bench Verified benchmark tasks.

    Loads tasks from HuggingFace datasets and registers them
    with the task registry in internal format.
    """

    DATASET_NAME = "princeton-nlp/SWE-bench_Verified"

    def __init__(self, registry: TaskRegistry, seed: int = 42) -> None:
        self._registry = registry
        self._seed = seed

    def load_tasks(
        self,
        max_tasks: int | None = None,
        difficulty_filter: str | None = None,
    ) -> list[EvalTask]:
        """Load SWE-bench tasks and register them.

        Args:
            max_tasks: Maximum number of tasks to load (random sample).
            difficulty_filter: Filter by difficulty if metadata available.

        Returns:
            List of loaded EvalTask instances.
        """
        raw_tasks = self._fetch_dataset()

        if difficulty_filter:
            raw_tasks = [
                t for t in raw_tasks
                if t.get("difficulty", "medium") == difficulty_filter
            ]

        if max_tasks and len(raw_tasks) > max_tasks:
            rng = random.Random(self._seed)
            raw_tasks = rng.sample(raw_tasks, max_tasks)

        tasks = []
        for raw in raw_tasks:
            task = self._convert_task(raw)
            self._registry.register(task)
            tasks.append(task)

        return tasks

    def _fetch_dataset(self) -> list[dict[str, Any]]:
        """Fetch the SWE-bench dataset.

        Tries to use the `datasets` library (HuggingFace).
        Falls back to an empty list if not installed.
        """
        try:
            from datasets import load_dataset
            ds = load_dataset(self.DATASET_NAME, split="test")
            return list(ds)
        except ImportError:
            return []
        except Exception:
            return []

    def _convert_task(self, raw: dict[str, Any]) -> EvalTask:
        """Convert a SWE-bench task to internal EvalTask format."""
        instance_id = raw.get("instance_id", "unknown")
        repo = raw.get("repo", "")
        base_commit = raw.get("base_commit", "")
        patch = raw.get("patch", "")
        test_patch = raw.get("test_patch", "")

        # Extract affected files from patch header
        affected_files: list[str] = []
        if patch:
            for line in patch.split("\n"):
                if line.startswith("diff --git"):
                    parts = line.split(" b/")
                    if len(parts) > 1:
                        affected_files.append(parts[1].strip())

        # Determine tier based on number of affected files
        if len(affected_files) <= 1:
            tier = TaskTier.TIER1
        elif len(affected_files) <= 3:
            tier = TaskTier.TIER2
        else:
            tier = TaskTier.TIER3

        return EvalTask(
            id=f"swebench-{instance_id}",
            tier=tier,
            source=TaskSource.SWEBENCH,
            description=raw.get("problem_statement", ""),
            difficulty="medium",
            repo_url=f"https://github.com/{repo}" if repo else None,
            base_commit=base_commit,
            affected_files=affected_files,
            golden_patch=patch,
            test_command=raw.get("test_cmd", ""),
            tags=["swebench", repo.split("/")[-1] if "/" in repo else repo],
            metadata={
                "instance_id": instance_id,
                "test_patch": test_patch,
                "created_at": raw.get("created_at", ""),
                "version": raw.get("version", ""),
            },
        )

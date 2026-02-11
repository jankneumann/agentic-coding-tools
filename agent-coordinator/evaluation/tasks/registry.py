"""Task registry for discovering and loading evaluation tasks.

Tasks are defined as YAML files with metadata including:
id, tier, source, description, difficulty, parallelizable_subtasks,
affected_files, golden_patch, and test_command.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..config import TaskSource, TaskTier

# Default task directory relative to this file
_DEFAULT_TASKS_DIR = Path(__file__).parent


@dataclass
class Subtask:
    """A subtask within a parallelizable or coordinated task."""

    id: str
    description: str
    affected_files: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)  # subtask IDs


@dataclass
class EvalTask:
    """A single evaluation task with all metadata for execution and scoring."""

    id: str
    tier: TaskTier
    source: TaskSource
    description: str
    difficulty: str  # "easy", "medium", "hard"
    repo_url: str | None = None  # Source repo for external tasks
    base_commit: str | None = None  # Commit to start from
    affected_files: list[str] = field(default_factory=list)
    golden_patch: str | None = None  # Expected diff for correctness
    test_command: str | None = None  # Command to run tests
    subtasks: list[Subtask] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    estimated_tokens: int = 0  # Estimated token usage
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def parallelizable_subtask_count(self) -> int:
        """Count subtasks that can run in parallel (no dependencies on other subtasks)."""
        return sum(1 for st in self.subtasks if not st.depends_on)

    @classmethod
    def from_yaml(cls, path: str | Path) -> EvalTask:
        """Load a task from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalTask:
        subtasks = []
        for st_data in data.get("subtasks", []):
            subtasks.append(Subtask(
                id=st_data["id"],
                description=st_data["description"],
                affected_files=st_data.get("affected_files", []),
                depends_on=st_data.get("depends_on", []),
            ))

        return cls(
            id=data["id"],
            tier=TaskTier(data["tier"]),
            source=TaskSource(data.get("source", "curated")),
            description=data["description"],
            difficulty=data.get("difficulty", "medium"),
            repo_url=data.get("repo_url"),
            base_commit=data.get("base_commit"),
            affected_files=data.get("affected_files", []),
            golden_patch=data.get("golden_patch"),
            test_command=data.get("test_command"),
            subtasks=subtasks,
            tags=data.get("tags", []),
            estimated_tokens=data.get("estimated_tokens", 0),
            metadata=data.get("metadata", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tier": self.tier.value,
            "source": self.source.value,
            "description": self.description,
            "difficulty": self.difficulty,
            "repo_url": self.repo_url,
            "base_commit": self.base_commit,
            "affected_files": self.affected_files,
            "golden_patch": self.golden_patch,
            "test_command": self.test_command,
            "subtasks": [
                {
                    "id": st.id,
                    "description": st.description,
                    "affected_files": st.affected_files,
                    "depends_on": st.depends_on,
                }
                for st in self.subtasks
            ],
            "tags": self.tags,
            "estimated_tokens": self.estimated_tokens,
            "metadata": self.metadata,
        }


class TaskRegistry:
    """Registry for discovering and loading evaluation tasks.

    Scans the tasks directory for YAML files and provides
    filtering by tier, source, and tags.
    """

    def __init__(self, tasks_dir: str | Path | None = None) -> None:
        self._tasks_dir = Path(tasks_dir) if tasks_dir else _DEFAULT_TASKS_DIR
        self._tasks: dict[str, EvalTask] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Lazy-load tasks from YAML files."""
        if self._loaded:
            return
        self._loaded = True
        for tier_dir in ["tier1", "tier2", "tier3"]:
            tier_path = self._tasks_dir / tier_dir
            if not tier_path.exists():
                continue
            for yaml_file in sorted(tier_path.glob("*.yaml")):
                task = EvalTask.from_yaml(yaml_file)
                self._tasks[task.id] = task
            for yml_file in sorted(tier_path.glob("*.yml")):
                task = EvalTask.from_yaml(yml_file)
                self._tasks[task.id] = task

    def register(self, task: EvalTask) -> None:
        """Register a task programmatically (e.g. from adapters)."""
        self._tasks[task.id] = task

    def get(self, task_id: str) -> EvalTask | None:
        """Get a specific task by ID."""
        self._ensure_loaded()
        return self._tasks.get(task_id)

    def list_tasks(
        self,
        tiers: list[TaskTier] | None = None,
        source: TaskSource | None = None,
        tags: list[str] | None = None,
        max_tasks: int | None = None,
    ) -> list[EvalTask]:
        """List tasks matching filters."""
        self._ensure_loaded()
        tasks = list(self._tasks.values())

        if tiers:
            tasks = [t for t in tasks if t.tier in tiers]
        if source:
            tasks = [t for t in tasks if t.source == source]
        if tags:
            tag_set = set(tags)
            tasks = [t for t in tasks if tag_set.intersection(t.tags)]

        # Sort by tier then ID for deterministic ordering
        tasks.sort(key=lambda t: (t.tier.value, t.id))

        if max_tasks is not None:
            tasks = tasks[:max_tasks]

        return tasks

    def count(self) -> int:
        """Total number of registered tasks."""
        self._ensure_loaded()
        return len(self._tasks)

    def clear(self) -> None:
        """Clear all registered tasks."""
        self._tasks.clear()
        self._loaded = False

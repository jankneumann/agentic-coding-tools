"""Tests for task registry."""

import yaml

from evaluation.config import TaskSource, TaskTier
from evaluation.tasks.registry import EvalTask, Subtask, TaskRegistry


class TestEvalTask:
    def test_from_dict(self):
        data = {
            "id": "test-1",
            "tier": 1,
            "source": "curated",
            "description": "Fix a bug",
            "difficulty": "easy",
            "affected_files": ["src/main.py"],
            "tags": ["bug-fix"],
        }
        task = EvalTask.from_dict(data)
        assert task.id == "test-1"
        assert task.tier == TaskTier.TIER1
        assert task.source == TaskSource.CURATED
        assert task.difficulty == "easy"

    def test_from_yaml(self, tmp_path):
        task_data = {
            "id": "yaml-test-1",
            "tier": 2,
            "description": "Add a feature",
            "affected_files": ["src/feature.py", "tests/test_feature.py"],
            "subtasks": [
                {"id": "impl", "description": "Implement feature",
                 "affected_files": ["src/feature.py"]},
                {"id": "test", "description": "Write tests",
                 "affected_files": ["tests/test_feature.py"]},
            ],
        }
        yaml_path = tmp_path / "task.yaml"
        yaml_path.write_text(yaml.dump(task_data))

        task = EvalTask.from_yaml(yaml_path)
        assert task.id == "yaml-test-1"
        assert task.tier == TaskTier.TIER2
        assert len(task.subtasks) == 2

    def test_parallelizable_subtask_count(self):
        task = EvalTask(
            id="test",
            tier=TaskTier.TIER2,
            source=TaskSource.CURATED,
            description="Test",
            difficulty="medium",
            subtasks=[
                Subtask(id="a", description="A"),
                Subtask(id="b", description="B"),
                Subtask(id="c", description="C", depends_on=["a"]),
            ],
        )
        # a and b have no deps, c depends on a
        assert task.parallelizable_subtask_count == 2

    def test_to_dict_roundtrip(self):
        task = EvalTask(
            id="roundtrip",
            tier=TaskTier.TIER1,
            source=TaskSource.CURATED,
            description="Round trip test",
            difficulty="easy",
            tags=["test"],
        )
        d = task.to_dict()
        restored = EvalTask.from_dict(d)
        assert restored.id == task.id
        assert restored.tier == task.tier


class TestTaskRegistry:
    def test_register_and_get(self, tmp_path):
        registry = TaskRegistry(tasks_dir=tmp_path)
        task = EvalTask(
            id="reg-1",
            tier=TaskTier.TIER1,
            source=TaskSource.CURATED,
            description="Test",
            difficulty="easy",
        )
        registry.register(task)
        assert registry.get("reg-1") is not None
        assert registry.get("nonexistent") is None

    def test_list_by_tier(self, tmp_path):
        registry = TaskRegistry(tasks_dir=tmp_path)
        t1 = EvalTask(id="t1", tier=TaskTier.TIER1, source=TaskSource.CURATED,
                       description="T1", difficulty="easy")
        t2 = EvalTask(id="t2", tier=TaskTier.TIER2, source=TaskSource.CURATED,
                       description="T2", difficulty="medium")
        registry.register(t1)
        registry.register(t2)

        tier1_tasks = registry.list_tasks(tiers=[TaskTier.TIER1])
        assert len(tier1_tasks) == 1
        assert tier1_tasks[0].id == "t1"

    def test_list_by_source(self, tmp_path):
        registry = TaskRegistry(tasks_dir=tmp_path)
        curated = EvalTask(id="c1", tier=TaskTier.TIER1, source=TaskSource.CURATED,
                           description="Curated", difficulty="easy")
        external = EvalTask(id="s1", tier=TaskTier.TIER1, source=TaskSource.SWEBENCH,
                            description="SWE-bench", difficulty="medium")
        registry.register(curated)
        registry.register(external)

        swebench_tasks = registry.list_tasks(source=TaskSource.SWEBENCH)
        assert len(swebench_tasks) == 1
        assert swebench_tasks[0].id == "s1"

    def test_list_with_max_tasks(self, tmp_path):
        registry = TaskRegistry(tasks_dir=tmp_path)
        for i in range(5):
            registry.register(EvalTask(
                id=f"task-{i}", tier=TaskTier.TIER1,
                source=TaskSource.CURATED, description=f"Task {i}",
                difficulty="easy",
            ))

        tasks = registry.list_tasks(max_tasks=3)
        assert len(tasks) == 3

    def test_list_by_tags(self, tmp_path):
        registry = TaskRegistry(tasks_dir=tmp_path)
        registry.register(EvalTask(
            id="tagged", tier=TaskTier.TIER1, source=TaskSource.CURATED,
            description="Tagged", difficulty="easy", tags=["bug-fix", "python"],
        ))
        registry.register(EvalTask(
            id="untagged", tier=TaskTier.TIER1, source=TaskSource.CURATED,
            description="Untagged", difficulty="easy", tags=["refactor"],
        ))

        results = registry.list_tasks(tags=["bug-fix"])
        assert len(results) == 1
        assert results[0].id == "tagged"

    def test_load_from_yaml_dir(self, tmp_path):
        # Create tier1 directory with a task
        tier1_dir = tmp_path / "tier1"
        tier1_dir.mkdir()
        task_data = {
            "id": "yaml-loaded",
            "tier": 1,
            "description": "From YAML",
            "difficulty": "easy",
        }
        (tier1_dir / "task.yaml").write_text(yaml.dump(task_data))

        registry = TaskRegistry(tasks_dir=tmp_path)
        tasks = registry.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].id == "yaml-loaded"

    def test_count(self, tmp_path):
        registry = TaskRegistry(tasks_dir=tmp_path)
        assert registry.count() == 0
        registry.register(EvalTask(
            id="t1", tier=TaskTier.TIER1, source=TaskSource.CURATED,
            description="T1", difficulty="easy",
        ))
        assert registry.count() == 1

    def test_clear(self, tmp_path):
        registry = TaskRegistry(tasks_dir=tmp_path)
        registry.register(EvalTask(
            id="t1", tier=TaskTier.TIER1, source=TaskSource.CURATED,
            description="T1", difficulty="easy",
        ))
        registry.clear()
        assert registry.count() == 0

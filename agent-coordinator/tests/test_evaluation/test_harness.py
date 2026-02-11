"""Tests for evaluation harness."""

from pathlib import Path

import pytest

from evaluation.backends.base import BackendResult
from evaluation.config import AblationFlags, EvalConfig, TaskSource, TaskTier
from evaluation.harness import EvalHarness, EvalResult
from evaluation.metrics import TokenUsage
from evaluation.tasks.registry import EvalTask, TaskRegistry


class MockBackend:
    """Mock agent backend for testing."""

    def __init__(self, name: str = "mock", success: bool = True):
        self._name = name
        self._success = success

    @property
    def name(self) -> str:
        return self._name

    async def execute_task(self, task_description, affected_files,
                           working_dir, ablation, timeout_seconds=300):
        return BackendResult(
            success=self._success,
            output="mock output",
            wall_clock_seconds=5.0,
            token_usage=TokenUsage(
                input_tokens=100, output_tokens=50,
                total_tokens=150, estimated_cost_usd=0.005,
            ),
            tests_total=3,
            tests_passed=3 if self._success else 1,
        )

    async def health_check(self):
        return True


@pytest.fixture
def registry_with_tasks(tmp_path):
    """Task registry with pre-loaded tasks (isolated from real task YAMLs)."""
    registry = TaskRegistry(tasks_dir=tmp_path)
    for i in range(3):
        registry.register(EvalTask(
            id=f"test-{i}",
            tier=TaskTier.TIER1,
            source=TaskSource.CURATED,
            description=f"Test task {i}",
            difficulty="easy",
            affected_files=[f"src/test_{i}.py"],
        ))
    return registry


class TestEvalHarness:
    @pytest.mark.asyncio
    async def test_run_basic(self, tmp_path, registry_with_tasks):
        config = EvalConfig(
            tiers=[TaskTier.TIER1],
            num_trials=1,
            output_dir=tmp_path,
        )
        backend = MockBackend()
        harness = EvalHarness(
            config=config,
            registry=registry_with_tasks,
            backends=[backend],
        )

        result = await harness.run()

        assert isinstance(result, EvalResult)
        assert result.total_tasks == 3
        assert result.overall_success_rate == 1.0
        assert len(result.task_metrics) == 3

    @pytest.mark.asyncio
    async def test_run_multiple_trials(self, tmp_path, registry_with_tasks):
        config = EvalConfig(
            tiers=[TaskTier.TIER1],
            num_trials=3,
            output_dir=tmp_path,
        )
        backend = MockBackend()
        harness = EvalHarness(
            config=config,
            registry=registry_with_tasks,
            backends=[backend],
        )

        result = await harness.run()

        # 3 tasks × 3 trials = 9 task metrics
        assert len(result.task_metrics) == 9
        # 3 trial aggregations (one per task)
        assert len(result.trial_metrics) == 3

    @pytest.mark.asyncio
    async def test_run_multiple_backends(self, tmp_path, registry_with_tasks):
        config = EvalConfig(
            tiers=[TaskTier.TIER1],
            num_trials=1,
            output_dir=tmp_path,
        )
        backends = [MockBackend("backend-a"), MockBackend("backend-b")]
        harness = EvalHarness(
            config=config,
            registry=registry_with_tasks,
            backends=backends,
        )

        result = await harness.run()

        # 3 tasks × 2 backends = 6 task metrics
        assert len(result.task_metrics) == 6

    @pytest.mark.asyncio
    async def test_run_with_ablation(self, tmp_path, registry_with_tasks):
        config = EvalConfig(
            tiers=[TaskTier.TIER1],
            num_trials=1,
            ablation_configs=[
                AblationFlags.all_on(),
                AblationFlags(locking=False),
            ],
            output_dir=tmp_path,
        )
        backend = MockBackend()
        harness = EvalHarness(
            config=config,
            registry=registry_with_tasks,
            backends=[backend],
        )

        result = await harness.run()

        # 3 tasks × 2 ablation configs = 6 task metrics
        assert len(result.task_metrics) == 6

    @pytest.mark.asyncio
    async def test_run_with_task_ids(self, tmp_path, registry_with_tasks):
        config = EvalConfig(
            task_ids=["test-0", "test-2"],
            num_trials=1,
            output_dir=tmp_path,
        )
        backend = MockBackend()
        harness = EvalHarness(
            config=config,
            registry=registry_with_tasks,
            backends=[backend],
        )

        result = await harness.run()
        assert result.total_tasks == 2

    @pytest.mark.asyncio
    async def test_run_no_tasks(self, tmp_path):
        config = EvalConfig(
            tiers=[TaskTier.TIER3],
            num_trials=1,
            output_dir=tmp_path,
        )
        registry = TaskRegistry(tasks_dir=tmp_path)
        harness = EvalHarness(
            config=config,
            registry=registry,
            backends=[MockBackend()],
        )

        result = await harness.run()
        assert result.total_tasks == 0

    @pytest.mark.asyncio
    async def test_run_no_backends(self, tmp_path, registry_with_tasks):
        config = EvalConfig(
            tiers=[TaskTier.TIER1],
            num_trials=1,
            output_dir=tmp_path,
        )
        harness = EvalHarness(
            config=config,
            registry=registry_with_tasks,
            backends=[],
        )

        result = await harness.run()
        assert len(result.task_metrics) == 0

    @pytest.mark.asyncio
    async def test_run_generates_reports(self, tmp_path, registry_with_tasks):
        config = EvalConfig(
            tiers=[TaskTier.TIER1],
            num_trials=1,
            output_dir=tmp_path,
        )
        backend = MockBackend()
        harness = EvalHarness(
            config=config,
            registry=registry_with_tasks,
            backends=[backend],
        )

        result = await harness.run()
        assert result.markdown_report is not None
        assert result.json_report is not None
        assert Path(result.markdown_report).exists()
        assert Path(result.json_report).exists()

    @pytest.mark.asyncio
    async def test_run_handles_backend_failure(self, tmp_path, registry_with_tasks):
        config = EvalConfig(
            tiers=[TaskTier.TIER1],
            num_trials=1,
            output_dir=tmp_path,
        )
        backend = MockBackend(success=False)
        harness = EvalHarness(
            config=config,
            registry=registry_with_tasks,
            backends=[backend],
        )

        result = await harness.run()
        assert result.overall_success_rate == 0.0


class TestEvalResult:
    def test_empty_result(self):
        result = EvalResult(run_id="empty")
        assert result.total_tasks == 0
        assert result.overall_success_rate == 0.0

    def test_success_rate(self):
        from evaluation.metrics import TaskMetrics
        result = EvalResult(
            run_id="test",
            task_metrics=[
                TaskMetrics(task_id="t1", trial_num=1, backend_name="b",
                           ablation_label="a", success=True),
                TaskMetrics(task_id="t2", trial_num=1, backend_name="b",
                           ablation_label="a", success=False),
            ],
        )
        assert result.overall_success_rate == pytest.approx(0.5)

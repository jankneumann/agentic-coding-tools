"""Pytest fixtures for evaluation framework tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from .backends.base import BackendResult
from .config import AblationFlags, AgentBackendConfig, EvalConfig, TaskTier
from .metrics import MetricsCollector, TokenUsage
from .tasks.registry import EvalTask, TaskRegistry


@pytest.fixture
def sample_eval_config() -> EvalConfig:
    """Minimal evaluation config for testing."""
    return EvalConfig(
        tiers=[TaskTier.TIER1],
        num_trials=2,
        temperature=0.0,
        output_dir=Path("/tmp/eval-test-reports"),
    )


@pytest.fixture
def sample_ablation_flags() -> AblationFlags:
    """Default ablation flags (all on)."""
    return AblationFlags.all_on()


@pytest.fixture
def sample_backend_config() -> AgentBackendConfig:
    """Sample backend configuration."""
    return AgentBackendConfig(
        name="test_backend",
        command="echo",
        args=["test"],
        timeout_seconds=10,
    )


@pytest.fixture
def metrics_collector() -> MetricsCollector:
    """Fresh metrics collector for testing."""
    return MetricsCollector()


@pytest.fixture
def task_registry(tmp_path: Path) -> TaskRegistry:
    """Task registry with temp directory."""
    return TaskRegistry(tasks_dir=tmp_path)


@pytest.fixture
def sample_task() -> EvalTask:
    """Sample Tier 1 evaluation task."""
    from .config import TaskSource
    return EvalTask(
        id="test-task-1",
        tier=TaskTier.TIER1,
        source=TaskSource.CURATED,
        description="Fix a bug in the test module",
        difficulty="easy",
        affected_files=["src/test.py"],
        test_command="pytest tests/test_test.py -v",
        tags=["bug-fix", "test"],
    )


@pytest.fixture
def sample_backend_result() -> BackendResult:
    """Sample successful backend result."""
    return BackendResult(
        success=True,
        output="diff --git a/src/test.py b/src/test.py\n+fixed line\n",
        wall_clock_seconds=15.3,
        token_usage=TokenUsage(
            input_tokens=500,
            output_tokens=200,
            total_tokens=700,
            estimated_cost_usd=0.01,
        ),
        tests_total=5,
        tests_passed=5,
    )

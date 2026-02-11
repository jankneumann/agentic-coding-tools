"""Evaluation harness for orchestrating benchmark runs.

Loads configuration, selects tasks, runs trials across
agent backends and ablation configurations, collects metrics,
and generates reports.
"""

from __future__ import annotations

import logging
import time
import uuid
from itertools import product
from typing import Any

from .backends.base import AgentBackend, BackendResult
from .config import AblationFlags, EvalConfig
from .consensus import ConsensusEvaluator, ConsensusResult
from .metrics import MetricsCollector, TaskMetrics, TrialMetrics
from .reports.generator import ReportGenerator
from .tasks.registry import EvalTask, TaskRegistry

logger = logging.getLogger(__name__)


class EvalHarness:
    """Orchestrates evaluation runs.

    Flow: load config -> select tasks -> run trials -> collect metrics -> report.
    """

    def __init__(
        self,
        config: EvalConfig,
        registry: TaskRegistry | None = None,
        backends: list[AgentBackend] | None = None,
        collector: MetricsCollector | None = None,
        consensus_evaluator: ConsensusEvaluator | None = None,
    ) -> None:
        self._config = config
        self._registry = registry or TaskRegistry()
        self._backends = backends or []
        self._collector = collector or MetricsCollector()
        self._consensus = consensus_evaluator
        self._run_id = config.run_id or f"eval-{uuid.uuid4().hex[:8]}"

    @property
    def run_id(self) -> str:
        return self._run_id

    async def run(self, working_dir: str = ".") -> EvalResult:
        """Execute the full evaluation pipeline.

        Args:
            working_dir: Base directory for task execution.

        Returns:
            EvalResult with all metrics and report paths.
        """
        logger.info("Starting evaluation run: %s", self._run_id)

        # 1. Select tasks
        tasks = self._select_tasks()
        logger.info("Selected %d tasks", len(tasks))

        if not tasks:
            logger.warning("No tasks matched the configuration")
            return EvalResult(run_id=self._run_id)

        if not self._backends:
            logger.warning("No backends configured")
            return EvalResult(run_id=self._run_id)

        # 2. Run trials
        self._collector.clear()
        consensus_results: list[ConsensusResult] = []

        for task, backend, ablation in product(
            tasks, self._backends, self._config.ablation_configs
        ):
            for trial in range(self._config.num_trials):
                logger.info(
                    "Running: task=%s backend=%s ablation=%s trial=%d/%d",
                    task.id, backend.name, ablation.label(),
                    trial + 1, self._config.num_trials,
                )

                metrics = await self._run_trial(
                    task=task,
                    backend=backend,
                    ablation=ablation,
                    trial_num=trial + 1,
                    working_dir=working_dir,
                )

                # Consensus evaluation (on last trial only, to save cost)
                if (
                    self._config.enable_consensus_eval
                    and self._consensus
                    and trial == self._config.num_trials - 1
                    and metrics.success
                ):
                    cr = await self._consensus.evaluate(
                        task_id=task.id,
                        task_description=task.description,
                        task_output=metrics.error or "",
                        golden_patch=task.golden_patch,
                    )
                    consensus_results.append(cr)

        # 3. Aggregate metrics
        all_metrics = self._collector.get_all_metrics()
        trial_metrics = self._collector.get_trial_metrics()

        # 4. Generate reports
        reporter = ReportGenerator(self._config.output_dir)
        config_summary = self._build_config_summary(tasks)

        md_path, json_path = reporter.generate(
            task_metrics=all_metrics,
            trial_metrics=trial_metrics,
            run_id=self._run_id,
            config_summary=config_summary,
            consensus_results=[cr.to_dict() for cr in consensus_results],
        )

        logger.info("Reports generated: %s, %s", md_path, json_path)

        return EvalResult(
            run_id=self._run_id,
            task_metrics=all_metrics,
            trial_metrics=trial_metrics,
            consensus_results=consensus_results,
            markdown_report=md_path,
            json_report=json_path,
        )

    async def _run_trial(
        self,
        task: EvalTask,
        backend: AgentBackend,
        ablation: AblationFlags,
        trial_num: int,
        working_dir: str,
    ) -> TaskMetrics:
        """Run a single trial of a task with a backend and ablation config."""
        metrics = self._collector.start_task(
            task_id=task.id,
            trial_num=trial_num,
            backend_name=backend.name,
            ablation_label=ablation.label(),
        )

        start = time.time()
        try:
            result: BackendResult = await backend.execute_task(
                task_description=task.description,
                affected_files=task.affected_files,
                working_dir=working_dir,
                ablation=ablation,
                timeout_seconds=300,
            )

            metrics.wall_clock_seconds = time.time() - start
            metrics.success = result.success
            metrics.token_usage = result.token_usage
            metrics.error = result.error

            # Record correctness if tests were run
            if result.tests_total > 0:
                self._collector.record_correctness(
                    tests_total=result.tests_total,
                    tests_passed=result.tests_passed,
                )

        except Exception as e:
            metrics.wall_clock_seconds = time.time() - start
            metrics.success = False
            metrics.error = str(e)
            logger.exception("Trial failed: %s", e)

        self._collector.finish_task()
        return metrics

    def _select_tasks(self) -> list[EvalTask]:
        """Select tasks based on configuration."""
        if self._config.task_ids:
            tasks = []
            for tid in self._config.task_ids:
                task = self._registry.get(tid)
                if task:
                    tasks.append(task)
            return tasks

        from .config import TaskSource
        return self._registry.list_tasks(
            tiers=self._config.tiers,
            source=(
                self._config.task_source
                if self._config.task_source != TaskSource.CURATED
                else None
            ),
            max_tasks=self._config.max_tasks,
        )

    def _build_config_summary(self, tasks: list[EvalTask]) -> dict[str, Any]:
        """Build a summary dict of the run configuration."""
        return {
            "run_id": self._run_id,
            "num_tasks": len(tasks),
            "tiers": [t.value for t in self._config.tiers],
            "backends": [b.name for b in self._backends],
            "ablation_configs": [a.label() for a in self._config.ablation_configs],
            "num_trials": self._config.num_trials,
            "temperature": self._config.temperature,
            "consensus_eval": self._config.enable_consensus_eval,
        }


class EvalResult:
    """Result of a complete evaluation run."""

    def __init__(
        self,
        run_id: str,
        task_metrics: list[TaskMetrics] | None = None,
        trial_metrics: list[TrialMetrics] | None = None,
        consensus_results: list[ConsensusResult] | None = None,
        markdown_report: Any = None,
        json_report: Any = None,
    ) -> None:
        self.run_id = run_id
        self.task_metrics = task_metrics or []
        self.trial_metrics = trial_metrics or []
        self.consensus_results = consensus_results or []
        self.markdown_report = markdown_report
        self.json_report = json_report

    @property
    def total_tasks(self) -> int:
        return len(set(m.task_id for m in self.task_metrics))

    @property
    def overall_success_rate(self) -> float:
        if not self.task_metrics:
            return 0.0
        return sum(1 for m in self.task_metrics if m.success) / len(self.task_metrics)

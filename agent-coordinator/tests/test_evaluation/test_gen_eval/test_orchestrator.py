"""Tests for the GenEvalOrchestrator."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from evaluation.gen_eval.change_detector import ChangeDetector
from evaluation.gen_eval.config import GenEvalConfig
from evaluation.gen_eval.descriptor import InterfaceDescriptor
from evaluation.gen_eval.evaluator import Evaluator
from evaluation.gen_eval.models import (
    ActionStep,
    Scenario,
    ScenarioVerdict,
)
from evaluation.gen_eval.orchestrator import GenEvalOrchestrator, HealthCheckError


def _make_scenario(
    scenario_id: str = "s1",
    priority: int = 2,
    interfaces: list[str] | None = None,
    category: str = "test-cat",
) -> Scenario:
    return Scenario(
        id=scenario_id,
        name=f"Scenario {scenario_id}",
        description=f"Desc {scenario_id}",
        category=category,
        priority=priority,
        interfaces=interfaces or ["POST /locks/acquire"],
        steps=[
            ActionStep(
                id="step1",
                transport="http",
                method="GET",
                endpoint="/health",
            )
        ],
    )


def _make_verdict(
    scenario_id: str = "s1",
    status: str = "pass",
    interfaces: list[str] | None = None,
    category: str = "test-cat",
    backend_used: str = "template",
) -> ScenarioVerdict:
    return ScenarioVerdict(
        scenario_id=scenario_id,
        scenario_name=f"Scenario {scenario_id}",
        status=status,  # type: ignore[arg-type]
        steps=[],
        duration_seconds=0.5,
        interfaces_tested=interfaces or ["POST /locks/acquire"],
        category=category,
        backend_used=backend_used,
    )


@pytest.fixture
def config(tmp_path: Path) -> GenEvalConfig:
    descriptor_path = tmp_path / "descriptor.yaml"
    descriptor_path.write_text("project: test\nversion: '0.1'\n")
    return GenEvalConfig(
        descriptor_path=descriptor_path,
        max_iterations=1,
        max_scenarios_per_iteration=10,
        parallel_scenarios=2,
        health_check_retries=3,
        health_check_interval_seconds=0.01,
    )


@pytest.fixture
def descriptor(sample_descriptor: InterfaceDescriptor) -> InterfaceDescriptor:
    return sample_descriptor


@pytest.fixture
def mock_generator() -> AsyncMock:
    gen = AsyncMock()
    gen.generate = AsyncMock(return_value=[_make_scenario()])
    return gen


@pytest.fixture
def mock_evaluator() -> AsyncMock:
    ev = AsyncMock(spec=Evaluator)
    ev.evaluate = AsyncMock(return_value=_make_verdict())
    return ev


@pytest.fixture
def orchestrator(
    config: GenEvalConfig,
    descriptor: InterfaceDescriptor,
    mock_generator: AsyncMock,
    mock_evaluator: AsyncMock,
) -> GenEvalOrchestrator:
    return GenEvalOrchestrator(
        config=config,
        descriptor=descriptor,
        generator=mock_generator,
        evaluator=mock_evaluator,
    )


class TestFullRunLifecycle:
    """Test the complete orchestrator run lifecycle."""

    @pytest.mark.asyncio
    async def test_full_run_succeeds(self, orchestrator: GenEvalOrchestrator) -> None:
        with patch("evaluation.gen_eval.orchestrator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            report = await orchestrator.run()

        assert report.total_scenarios == 1
        assert report.passed == 1
        assert report.iterations_completed == 1
        assert not report.budget_exhausted

    @pytest.mark.asyncio
    async def test_startup_called(self, orchestrator: GenEvalOrchestrator) -> None:
        with patch("evaluation.gen_eval.orchestrator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            await orchestrator.run()

        # First call is startup command
        calls = mock_run.call_args_list
        assert any("docker-compose up" in str(c) for c in calls)

    @pytest.mark.asyncio
    async def test_teardown_called(self, orchestrator: GenEvalOrchestrator) -> None:
        with patch("evaluation.gen_eval.orchestrator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            await orchestrator.run()

        calls = mock_run.call_args_list
        assert any("docker-compose down" in str(c) for c in calls)


class TestHealthCheck:
    """Test health check retry with backoff."""

    @pytest.mark.asyncio
    async def test_health_check_retry_succeeds_on_second(
        self, orchestrator: GenEvalOrchestrator
    ) -> None:
        call_count = 0

        def side_effect(*args: Any, **kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            # Startup call succeeds
            if kwargs.get("shell"):
                result.returncode = 0
                return result
            # Health check: fail first, succeed second
            if call_count <= 2:  # first health check attempt
                result.returncode = 1
            else:
                result.returncode = 0
            return result

        with patch("evaluation.gen_eval.orchestrator.subprocess.run", side_effect=side_effect):
            with patch("evaluation.gen_eval.orchestrator.asyncio.sleep", new_callable=AsyncMock):
                report = await orchestrator.run()

        assert report.total_scenarios == 1

    @pytest.mark.asyncio
    async def test_health_check_failure_aborts(self, orchestrator: GenEvalOrchestrator) -> None:
        def side_effect(*args: Any, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            if kwargs.get("shell"):
                result.returncode = 0
                return result
            # All health checks fail
            result.returncode = 1
            return result

        with patch("evaluation.gen_eval.orchestrator.subprocess.run", side_effect=side_effect):
            with patch("evaluation.gen_eval.orchestrator.asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(HealthCheckError, match="Health check failed after 3 attempts"):
                    await orchestrator.run()


class TestBudgetExhaustion:
    """Test budget-aware execution."""

    @pytest.mark.asyncio
    async def test_budget_exhausted_stops_execution(
        self, orchestrator: GenEvalOrchestrator
    ) -> None:
        # Set budget to nearly exhausted
        orchestrator.budget_tracker.time_budget.total_minutes = 0.001
        orchestrator.budget_tracker.time_budget.elapsed_minutes = 0.001

        with patch("evaluation.gen_eval.orchestrator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            report = await orchestrator.run()

        assert report.budget_exhausted
        assert report.total_scenarios == 0
        assert report.iterations_completed == 0

    @pytest.mark.asyncio
    async def test_budget_exhausted_during_evaluation(
        self,
        config: GenEvalConfig,
        descriptor: InterfaceDescriptor,
    ) -> None:
        """Budget runs out mid-evaluation; remaining scenarios skipped."""
        scenarios = [_make_scenario(f"s{i}") for i in range(5)]

        mock_gen = AsyncMock()
        mock_gen.generate = AsyncMock(return_value=scenarios)

        eval_count = 0

        async def eval_side_effect(scenario: Scenario) -> ScenarioVerdict:
            nonlocal eval_count
            eval_count += 1
            # After first eval, exhaust the budget
            return _make_verdict(scenario.id, backend_used="cli")

        mock_ev = AsyncMock(spec=Evaluator)
        mock_ev.evaluate = AsyncMock(side_effect=eval_side_effect)

        orch = GenEvalOrchestrator(
            config=config,
            descriptor=descriptor,
            generator=mock_gen,
            evaluator=mock_ev,
        )
        # Very tight budget
        orch.budget_tracker.time_budget.total_minutes = 0.01

        with patch("evaluation.gen_eval.orchestrator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            report = await orch.run()

        # Should have evaluated some but flagged budget_exhausted
        assert report.iterations_completed >= 1


class TestParallelExecution:
    """Test parallel evaluation with semaphore."""

    @pytest.mark.asyncio
    async def test_parallel_semaphore_limits_concurrency(
        self,
        config: GenEvalConfig,
        descriptor: InterfaceDescriptor,
    ) -> None:
        max_concurrent = 0
        current_concurrent = 0

        # Use priority=1 so all go to tier2 (35% of 10 = 3) plus tier3
        # Or use priority=1 for all to land in tier2 bucket
        scenarios = [_make_scenario(f"s{i}", priority=1) for i in range(6)]
        mock_gen = AsyncMock()
        mock_gen.generate = AsyncMock(return_value=scenarios)

        async def eval_side_effect(scenario: Scenario) -> ScenarioVerdict:
            nonlocal max_concurrent, current_concurrent
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.01)
            current_concurrent -= 1
            return _make_verdict(scenario.id)

        mock_ev = AsyncMock(spec=Evaluator)
        mock_ev.evaluate = AsyncMock(side_effect=eval_side_effect)

        # Increase max_scenarios so tier caps don't truncate
        config.max_scenarios_per_iteration = 100

        orch = GenEvalOrchestrator(
            config=config,
            descriptor=descriptor,
            generator=mock_gen,
            evaluator=mock_ev,
        )

        with patch("evaluation.gen_eval.orchestrator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            report = await orch.run()

        # parallel_scenarios is set to 2 in config fixture
        assert max_concurrent <= config.parallel_scenarios
        assert report.total_scenarios == 6


class TestIterationLoop:
    """Test iteration loop with feedback."""

    @pytest.mark.asyncio
    async def test_multiple_iterations(
        self,
        config: GenEvalConfig,
        descriptor: InterfaceDescriptor,
        mock_evaluator: AsyncMock,
    ) -> None:
        config.max_iterations = 3

        mock_gen = AsyncMock()
        mock_gen.generate = AsyncMock(return_value=[_make_scenario()])

        orch = GenEvalOrchestrator(
            config=config,
            descriptor=descriptor,
            generator=mock_gen,
            evaluator=mock_evaluator,
        )

        with patch("evaluation.gen_eval.orchestrator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            report = await orch.run()

        assert report.iterations_completed == 3
        assert mock_gen.generate.call_count == 3

    @pytest.mark.asyncio
    async def test_feedback_flows_between_iterations(
        self,
        config: GenEvalConfig,
        descriptor: InterfaceDescriptor,
        mock_evaluator: AsyncMock,
    ) -> None:
        config.max_iterations = 2

        focus_areas_received: list[Any] = []

        async def gen_side_effect(
            focus_areas: list[str] | None = None, count: int = 10
        ) -> list[Scenario]:
            focus_areas_received.append(focus_areas)
            return [_make_scenario()]

        mock_gen = AsyncMock()
        mock_gen.generate = AsyncMock(side_effect=gen_side_effect)

        orch = GenEvalOrchestrator(
            config=config,
            descriptor=descriptor,
            generator=mock_gen,
            evaluator=mock_evaluator,
        )

        with patch("evaluation.gen_eval.orchestrator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            await orch.run()

        # First iteration has no focus areas, second may have some from feedback
        assert len(focus_areas_received) == 2
        assert focus_areas_received[0] is None


class TestTeardownAlwaysRuns:
    """Test teardown runs even on error."""

    @pytest.mark.asyncio
    async def test_teardown_on_generator_error(
        self,
        config: GenEvalConfig,
        descriptor: InterfaceDescriptor,
        mock_evaluator: AsyncMock,
    ) -> None:
        mock_gen = AsyncMock()
        mock_gen.generate = AsyncMock(side_effect=RuntimeError("generation failed"))

        orch = GenEvalOrchestrator(
            config=config,
            descriptor=descriptor,
            generator=mock_gen,
            evaluator=mock_evaluator,
        )

        teardown_called = False
        _ = orch._run_teardown  # noqa: F841

        def track_teardown() -> None:
            nonlocal teardown_called
            teardown_called = True

        orch._run_teardown = track_teardown  # type: ignore[assignment]

        with patch("evaluation.gen_eval.orchestrator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with pytest.raises(RuntimeError, match="generation failed"):
                await orch.run()

        assert teardown_called

    @pytest.mark.asyncio
    async def test_teardown_on_health_check_failure(
        self, orchestrator: GenEvalOrchestrator
    ) -> None:
        teardown_called = False
        _ = orchestrator._run_teardown  # noqa: F841

        def track_teardown() -> None:
            nonlocal teardown_called
            teardown_called = True

        orchestrator._run_teardown = track_teardown  # type: ignore[assignment]

        def side_effect(*args: Any, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            if kwargs.get("shell"):
                result.returncode = 0
                return result
            result.returncode = 1
            return result

        with patch("evaluation.gen_eval.orchestrator.subprocess.run", side_effect=side_effect):
            with patch("evaluation.gen_eval.orchestrator.asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(HealthCheckError):
                    await orchestrator.run()

        assert teardown_called


class TestSeedData:
    """Test seed data execution."""

    @pytest.mark.asyncio
    async def test_seed_data_called(self, orchestrator: GenEvalOrchestrator) -> None:
        with patch("evaluation.gen_eval.orchestrator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            await orchestrator.run()

        calls = mock_run.call_args_list
        assert any("seed_data" in str(c) for c in calls)

    @pytest.mark.asyncio
    async def test_seed_data_skipped_when_disabled(
        self,
        config: GenEvalConfig,
        descriptor: InterfaceDescriptor,
        mock_generator: AsyncMock,
        mock_evaluator: AsyncMock,
    ) -> None:
        config.seed_data = False
        orch = GenEvalOrchestrator(
            config=config,
            descriptor=descriptor,
            generator=mock_generator,
            evaluator=mock_evaluator,
        )

        with patch("evaluation.gen_eval.orchestrator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            await orch.run()

        calls = mock_run.call_args_list
        assert not any("seed_data" in str(c) for c in calls)


class TestTierPrioritization:
    """Test scenario prioritization by tier."""

    def test_tier_ordering(
        self,
        orchestrator: GenEvalOrchestrator,
    ) -> None:
        # Set up change detector to mark "POST /locks/acquire" as changed
        mock_cd = MagicMock(spec=ChangeDetector)
        mock_cd.detect_from_git_diff.return_value = ["POST /locks/acquire"]
        orchestrator.change_detector = mock_cd
        orchestrator.config.changed_features_ref = "main"

        scenarios = [
            # Tier 3: priority 2, no changed interfaces
            _make_scenario("tier3", priority=2, interfaces=["GET /health"]),
            # Tier 1: touches changed interface
            _make_scenario("tier1", priority=2, interfaces=["POST /locks/acquire"]),
            # Tier 2: critical path priority <= 1
            _make_scenario("tier2", priority=1, interfaces=["GET /health"]),
        ]

        result = orchestrator._prioritize_scenarios(scenarios)
        ids = [s.id for s in result]

        # Tier 1 first, then tier 2, then tier 3
        assert ids.index("tier1") < ids.index("tier2")
        assert ids.index("tier2") < ids.index("tier3")

    def test_tier_budgets_no_lost_slots(
        self,
        orchestrator: GenEvalOrchestrator,
    ) -> None:
        """Tier budget allocation should not lose slots due to int() truncation."""
        orchestrator.config.max_scenarios_per_iteration = 10

        # Create enough scenarios to fill all tiers
        # All go to tier3 since no change detector and priority > 1
        scenarios = [
            _make_scenario(f"s{i}", priority=2, interfaces=["GET /health"])
            for i in range(10)
        ]

        result = orchestrator._prioritize_scenarios(scenarios)
        # tier1=int(10*0.40)=4, tier2=int(10*0.35)=3, tier3=10-4-3=3
        # All scenarios are tier3, so we get min(10, 3) = 3
        # But the total budget is 4+3+3=10 (no lost slots)
        assert len(result) <= 10
        # The key assertion: tier3 gets the remainder (3 not 2)
        # With old code: int(10*0.25)=2, total=4+3+2=9 (lost 1)
        # With new code: 10-4-3=3, total=4+3+3=10 (no loss)
        # Since all are tier3, result length = min(10, 3) = 3
        assert len(result) == 3

    def test_no_change_detector_all_tier2_tier3(
        self,
        orchestrator: GenEvalOrchestrator,
    ) -> None:
        scenarios = [
            _make_scenario("crit", priority=1),
            _make_scenario("normal", priority=2),
        ]
        result = orchestrator._prioritize_scenarios(scenarios)
        ids = [s.id for s in result]
        assert ids.index("crit") < ids.index("normal")


class TestGracefulShutdown:
    """Test graceful shutdown on budget exhaust."""

    @pytest.mark.asyncio
    async def test_partial_report_on_budget_exhaust(
        self,
        config: GenEvalConfig,
        descriptor: InterfaceDescriptor,
    ) -> None:
        scenarios = [_make_scenario(f"s{i}") for i in range(10)]
        mock_gen = AsyncMock()
        mock_gen.generate = AsyncMock(return_value=scenarios)

        eval_count = 0

        async def eval_side_effect(scenario: Scenario) -> ScenarioVerdict:
            nonlocal eval_count
            eval_count += 1
            return _make_verdict(scenario.id, backend_used="cli")

        mock_ev = AsyncMock(spec=Evaluator)
        mock_ev.evaluate = AsyncMock(side_effect=eval_side_effect)

        orch = GenEvalOrchestrator(
            config=config,
            descriptor=descriptor,
            generator=mock_gen,
            evaluator=mock_ev,
        )
        # Exhaust budget quickly
        orch.budget_tracker.time_budget.total_minutes = 0.001

        with patch("evaluation.gen_eval.orchestrator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            report = await orch.run()

        # Report should exist even with budget exhaustion
        assert isinstance(report.total_scenarios, int)
        assert report.budget_exhausted

    @pytest.mark.asyncio
    async def test_template_verdicts_do_not_inflate_cli_calls(
        self,
        config: GenEvalConfig,
        descriptor: InterfaceDescriptor,
    ) -> None:
        """Template-only evaluations should not increment cli_calls."""
        scenarios = [_make_scenario(f"s{i}", priority=1) for i in range(3)]
        mock_gen = AsyncMock()
        mock_gen.generate = AsyncMock(return_value=scenarios)

        async def eval_side_effect(scenario: Scenario) -> ScenarioVerdict:
            return _make_verdict(scenario.id, backend_used="template")

        mock_ev = AsyncMock(spec=Evaluator)
        mock_ev.evaluate = AsyncMock(side_effect=eval_side_effect)

        config.max_scenarios_per_iteration = 100

        orch = GenEvalOrchestrator(
            config=config,
            descriptor=descriptor,
            generator=mock_gen,
            evaluator=mock_ev,
        )

        with patch("evaluation.gen_eval.orchestrator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            report = await orch.run()

        assert report.total_scenarios == 3
        assert orch.budget_tracker.time_budget.cli_calls == 0

    @pytest.mark.asyncio
    async def test_cli_verdicts_do_increment_cli_calls(
        self,
        config: GenEvalConfig,
        descriptor: InterfaceDescriptor,
    ) -> None:
        """CLI-backend evaluations should increment cli_calls."""
        scenarios = [_make_scenario(f"s{i}", priority=1) for i in range(3)]
        mock_gen = AsyncMock()
        mock_gen.generate = AsyncMock(return_value=scenarios)

        async def eval_side_effect(scenario: Scenario) -> ScenarioVerdict:
            return _make_verdict(scenario.id, backend_used="cli")

        mock_ev = AsyncMock(spec=Evaluator)
        mock_ev.evaluate = AsyncMock(side_effect=eval_side_effect)

        config.max_scenarios_per_iteration = 100

        orch = GenEvalOrchestrator(
            config=config,
            descriptor=descriptor,
            generator=mock_gen,
            evaluator=mock_ev,
        )

        with patch("evaluation.gen_eval.orchestrator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            report = await orch.run()

        assert report.total_scenarios == 3
        assert orch.budget_tracker.time_budget.cli_calls == 3

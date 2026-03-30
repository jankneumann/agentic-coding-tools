"""Tests for gen-eval configuration models."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from evaluation.gen_eval.config import (
    BudgetConfig,
    BudgetTracker,
    GenEvalConfig,
    SDKBudget,
    TimeBudget,
)


class TestTimeBudget:
    def test_defaults(self) -> None:
        budget = TimeBudget()
        assert budget.total_minutes == 60.0
        assert budget.elapsed_minutes == 0.0
        assert budget.remaining_minutes == 60.0
        assert budget.can_continue()

    def test_record_call(self) -> None:
        budget = TimeBudget(total_minutes=10.0)
        budget.record_call("generation", 120.0)  # 2 minutes
        assert budget.cli_calls == 1
        assert budget.generation_minutes == 2.0
        assert budget.remaining_minutes == 8.0

    def test_exhausted(self) -> None:
        budget = TimeBudget(total_minutes=1.0)
        budget.record_call("generation", 61.0)  # > 1 minute
        assert not budget.can_continue()

    def test_max_cli_calls(self) -> None:
        budget = TimeBudget(total_minutes=60.0, max_cli_calls=3)
        for _ in range(3):
            budget.record_call("generation", 1.0)
        assert not budget.can_continue()

    def test_evaluation_tracking(self) -> None:
        budget = TimeBudget(total_minutes=10.0)
        budget.record_call("evaluation", 60.0)
        assert budget.evaluation_minutes == 1.0
        assert budget.generation_minutes == 0.0

    def test_remaining_includes_running_wallclock(self) -> None:
        """remaining_minutes accounts for time elapsed since start()."""
        budget = TimeBudget(total_minutes=10.0)
        budget.start()
        # Simulate passage of time by backdating _start_time
        budget._start_time = budget._start_time - 300.0  # type: ignore[operator]  # 5 minutes ago
        assert budget.remaining_minutes == pytest.approx(5.0, abs=0.1)

    def test_record_call_no_double_count_when_timer_running(self) -> None:
        """record_call should not add to elapsed_minutes when wall-clock is running."""
        budget = TimeBudget(total_minutes=10.0)
        budget.start()
        budget.record_call("generation", 120.0)  # 2 minutes
        # elapsed_minutes should NOT increase while timer is running
        assert budget.elapsed_minutes == 0.0
        assert budget.cli_calls == 1
        assert budget.generation_minutes == 2.0

    def test_record_call_adds_elapsed_when_timer_stopped(self) -> None:
        """record_call adds to elapsed_minutes when no wall-clock is running."""
        budget = TimeBudget(total_minutes=10.0)
        # No start() called
        budget.record_call("generation", 120.0)  # 2 minutes
        assert budget.elapsed_minutes == 2.0
        assert budget.remaining_minutes == 8.0


class TestSDKBudget:
    def test_defaults(self) -> None:
        budget = SDKBudget()
        assert budget.budget_usd == 5.0
        assert budget.remaining_usd == 5.0

    def test_can_afford(self) -> None:
        budget = SDKBudget(budget_usd=1.0)
        assert budget.can_afford(0.5)
        assert budget.can_afford(1.0)
        assert not budget.can_afford(1.01)

    def test_record(self) -> None:
        budget = SDKBudget(budget_usd=5.0)
        budget.record("generation", 1.5)
        assert budget.spent_usd == 1.5
        assert budget.generation_spent == 1.5
        assert budget.remaining_usd == 3.5

    def test_exhausted(self) -> None:
        budget = SDKBudget(budget_usd=1.0)
        budget.record("generation", 1.0)
        assert not budget.can_afford(0.01)


class TestBudgetConfig:
    def test_defaults(self) -> None:
        config = BudgetConfig()
        assert config.tier1_pct + config.tier2_pct + config.tier3_pct == 1.0

    def test_custom(self) -> None:
        config = BudgetConfig(total_usd=10.0, tier1_pct=0.5, tier2_pct=0.3, tier3_pct=0.2)
        assert config.total_usd == 10.0
        assert config.tier1_pct == 0.5


class TestBudgetTracker:
    def test_cli_mode(self) -> None:
        tracker = BudgetTracker(mode="cli", time_budget=TimeBudget(total_minutes=10.0))
        assert tracker.can_continue()
        tracker.time_budget.record_call("generation", 601.0)
        assert not tracker.can_continue()

    def test_sdk_mode(self) -> None:
        tracker = BudgetTracker(mode="sdk", sdk_budget=SDKBudget(budget_usd=1.0))
        assert tracker.can_continue()
        tracker.sdk_budget.record("generation", 1.0)  # type: ignore[union-attr]
        assert not tracker.can_continue()

    def test_no_budget_allows_continue(self) -> None:
        tracker = BudgetTracker(mode="sdk", sdk_budget=None)
        assert tracker.can_continue()


class TestGenEvalConfig:
    def test_defaults(self, tmp_path: Path) -> None:
        p = tmp_path / "d.yaml"
        p.write_text("")
        config = GenEvalConfig(descriptor_path=p)
        assert config.mode == "template-only"
        assert config.cli_command == "claude"
        assert config.max_iterations == 1
        assert config.parallel_scenarios == 5

    def test_from_yaml(self, tmp_path: Path) -> None:
        data = {
            "descriptor_path": str(tmp_path / "desc.yaml"),
            "mode": "cli-augmented",
            "time_budget_minutes": 30.0,
            "max_iterations": 3,
        }
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump(data))
        (tmp_path / "desc.yaml").write_text("")
        config = GenEvalConfig.from_yaml(config_path)
        assert config.mode == "cli-augmented"
        assert config.time_budget_minutes == 30.0
        assert config.max_iterations == 3

    def test_from_dict(self, tmp_path: Path) -> None:
        p = tmp_path / "d.yaml"
        p.write_text("")
        config = GenEvalConfig.from_dict({"descriptor_path": str(p), "mode": "sdk-only"})
        assert config.mode == "sdk-only"

    def test_build_budget_tracker_template(self, tmp_path: Path) -> None:
        p = tmp_path / "d.yaml"
        p.write_text("")
        config = GenEvalConfig(descriptor_path=p, mode="template-only")
        tracker = config.build_budget_tracker()
        assert tracker.mode == "cli"
        assert tracker.sdk_budget is None

    def test_build_budget_tracker_cli(self, tmp_path: Path) -> None:
        p = tmp_path / "d.yaml"
        p.write_text("")
        config = GenEvalConfig(
            descriptor_path=p,
            mode="cli-augmented",
            time_budget_minutes=30.0,
            sdk_budget_usd=10.0,
        )
        tracker = config.build_budget_tracker()
        assert tracker.mode == "cli"
        assert tracker.time_budget.total_minutes == 30.0
        assert tracker.sdk_budget is not None
        assert tracker.sdk_budget.budget_usd == 10.0

    def test_build_budget_tracker_sdk(self, tmp_path: Path) -> None:
        p = tmp_path / "d.yaml"
        p.write_text("")
        config = GenEvalConfig(
            descriptor_path=p,
            mode="sdk-only",
            sdk_budget_usd=20.0,
        )
        tracker = config.build_budget_tracker()
        assert tracker.mode == "sdk"
        assert tracker.sdk_budget is not None
        assert tracker.sdk_budget.budget_usd == 20.0

    def test_rate_limit_patterns(self, tmp_path: Path) -> None:
        p = tmp_path / "d.yaml"
        p.write_text("")
        config = GenEvalConfig(descriptor_path=p)
        assert "rate limit" in config.rate_limit_patterns
        assert "too many requests" in config.rate_limit_patterns

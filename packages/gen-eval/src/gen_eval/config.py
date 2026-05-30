"""Configuration for generator-evaluator runs.

Defines GenEvalConfig (top-level run configuration), BudgetConfig (cost allocation),
TimeBudget (CLI wall-clock tracking), SDKBudget (per-token USD tracking), and
BudgetTracker (unified budget management).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


class TimeBudget(BaseModel):
    """Time-based budget for CLI-powered evaluation (subscription-covered).

    Tracks wall-clock minutes consumed by CLI calls. Since CLI usage
    is covered by subscription plans, the budget is time-based rather
    than cost-based.
    """

    total_minutes: float = 60.0
    elapsed_minutes: float = 0.0
    cli_calls: int = 0
    max_cli_calls: int | None = None
    generation_minutes: float = 0.0
    evaluation_minutes: float = 0.0
    _start_time: float | None = None

    model_config = {"arbitrary_types_allowed": True}

    def start(self) -> None:
        """Start the wall-clock timer."""
        self._start_time = time.monotonic()

    def stop(self) -> None:
        """Stop the timer and update elapsed."""
        if self._start_time is not None:
            elapsed = (time.monotonic() - self._start_time) / 60.0
            self.elapsed_minutes += elapsed
            self._start_time = None

    def can_continue(self) -> bool:
        """Check if budget allows more work."""
        if self.max_cli_calls is not None and self.cli_calls >= self.max_cli_calls:
            return False
        return self.remaining_minutes > 0

    def record_call(self, category: str, duration_seconds: float) -> None:
        """Record a CLI call with its duration."""
        self.cli_calls += 1
        minutes = duration_seconds / 60.0
        if self._start_time is None:
            # No wall-clock running, track elapsed manually
            self.elapsed_minutes += minutes
        if category == "generation":
            self.generation_minutes += minutes
        elif category == "evaluation":
            self.evaluation_minutes += minutes

    @property
    def remaining_minutes(self) -> float:
        """Minutes remaining in the budget."""
        elapsed = self.elapsed_minutes
        if self._start_time is not None:
            elapsed += (time.monotonic() - self._start_time) / 60.0
        return max(0.0, self.total_minutes - elapsed)


class SDKBudget(BaseModel):
    """USD budget for SDK-based execution (sdk-only mode or adaptive fallback).

    Tracks per-token API costs when using direct SDK calls instead of
    subscription-covered CLI tools.
    """

    budget_usd: float = 5.0
    spent_usd: float = 0.0
    generation_spent: float = 0.0
    evaluation_spent: float = 0.0

    def can_afford(self, estimated_cost: float) -> bool:
        """Check if budget can afford estimated cost."""
        return (
            self.spent_usd < self.budget_usd
            and (self.spent_usd + estimated_cost) <= self.budget_usd
        )

    def record(self, category: str, cost_usd: float) -> None:
        """Record a spend event."""
        self.spent_usd += cost_usd
        if category == "generation":
            self.generation_spent += cost_usd
        elif category == "evaluation":
            self.evaluation_spent += cost_usd

    @property
    def remaining_usd(self) -> float:
        """USD remaining in the budget."""
        return max(0.0, self.budget_usd - self.spent_usd)


class BudgetConfig(BaseModel):
    """Budget allocation percentages for a gen-eval run."""

    total_usd: float = 5.0
    generation_pct: float = 0.4
    evaluation_pct: float = 0.6
    tier1_pct: float = 0.40  # Changed features
    tier2_pct: float = 0.35  # Critical paths
    tier3_pct: float = 0.25  # Full surface


class BudgetTracker(BaseModel):
    """Unified budget tracker supporting CLI (time) and SDK (cost) modes.

    In cli-augmented mode, tracks wall-clock time since CLI usage is
    subscription-covered. In sdk-only mode, tracks USD spend. The
    adaptive backend may use both simultaneously when CLI falls back
    to SDK.
    """

    mode: Literal["cli", "sdk"] = "cli"
    time_budget: TimeBudget = Field(default_factory=TimeBudget)
    sdk_budget: SDKBudget | None = None

    def can_continue(self) -> bool:
        """Check if any budget allows continued execution."""
        if self.mode == "cli":
            return self.time_budget.can_continue()
        if self.sdk_budget is not None:
            return self.sdk_budget.can_afford(0.0)
        return True


class GenEvalConfig(BaseModel):
    """Configuration for a gen-eval run.

    Supports three modes:
    - template-only: No LLM, instant, zero cost
    - cli-augmented: Uses CLI tools (subscription-covered) with SDK fallback
    - sdk-only: Direct API calls (per-token cost), for CI without CLI access
    """

    descriptor_path: Path
    mode: Literal["template-only", "cli-augmented", "sdk-only"] = "template-only"
    # CLI backend config
    cli_command: str = "claude"
    cli_args: list[str] = Field(default_factory=lambda: ["--print"])
    # SDK backend config
    sdk_provider: str = "anthropic"
    sdk_model: str = "claude-sonnet-4-6"
    sdk_api_key_env: str = "ANTHROPIC_API_KEY"
    # Budget
    time_budget_minutes: float = 60.0
    sdk_budget_usd: float | None = None
    # Adaptive behavior
    auto_fallback_to_sdk: bool = True
    rate_limit_patterns: list[str] = Field(
        default_factory=lambda: ["rate limit", "too many requests", "quota exceeded"]
    )
    # Execution
    max_iterations: int = 1
    max_scenarios_per_iteration: int = 50
    max_expansions: int = 100
    parallel_scenarios: int = 5
    step_timeout_seconds: int = 30
    changed_features_ref: str | None = None
    openspec_change_id: str | None = None
    use_coordinator: bool = False
    report_format: Literal["markdown", "json", "both"] = "both"
    fail_threshold: float = 0.95
    seed_data: bool = True
    no_services: bool = False
    categories: list[str] | None = None
    verbose: bool = False
    # Health check
    health_check_retries: int = 5
    health_check_interval_seconds: float = 2.0

    @classmethod
    def from_yaml(cls, path: Path) -> GenEvalConfig:
        """Load config from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Expected YAML mapping in {path}, got {type(data).__name__}")
        return cls(**data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GenEvalConfig:
        """Create config from a dictionary (e.g., CLI args)."""
        return cls(**data)

    def build_budget_tracker(self) -> BudgetTracker:
        """Create a BudgetTracker matching this config's mode."""
        if self.mode == "sdk-only":
            return BudgetTracker(
                mode="sdk",
                sdk_budget=SDKBudget(budget_usd=self.sdk_budget_usd or 5.0),
            )
        time_budget = TimeBudget(total_minutes=self.time_budget_minutes)
        sdk_budget = None
        if self.mode == "cli-augmented" and self.auto_fallback_to_sdk:
            sdk_budget = SDKBudget(budget_usd=self.sdk_budget_usd or 5.0)
        return BudgetTracker(
            mode="cli",
            time_budget=time_budget,
            sdk_budget=sdk_budget,
        )

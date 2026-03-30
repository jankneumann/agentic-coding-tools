"""Core data models for scenarios, verdicts, and generator protocol.

These models form the contract between generators, evaluators, and the
orchestrator. Scenarios are the unit of test generation, verdicts are
the unit of evaluation output.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field


class ExpectBlock(BaseModel):
    """Expected outcomes for a step.

    Supports HTTP status codes, CLI exit codes, response body assertions
    (via JSONPath), database row counts/values, error message matching,
    and non-emptiness checks.
    """

    status: int | None = None
    exit_code: int | None = None
    body: dict[str, Any] | None = None
    rows: int | None = None
    row: dict[str, Any] | None = None
    error_contains: str | None = None
    not_empty: bool | None = None


class ActionStep(BaseModel):
    """A single step in a scenario.

    Each step targets a specific transport (http, mcp, cli, db, wait)
    and optionally captures response values for use in subsequent steps.
    """

    id: str
    transport: Literal["http", "mcp", "cli", "db", "wait"]
    # HTTP
    method: str | None = None
    endpoint: str | None = None
    body: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    # MCP
    tool: str | None = None
    params: dict[str, Any] | None = None
    # CLI
    command: str | None = None
    args: list[str] | None = None
    # DB (state verification)
    sql: str | None = None
    # Wait
    seconds: float | None = None
    # Expectations
    expect: ExpectBlock | None = None
    # Variable capture: JSONPath expression → variable name
    capture: dict[str, str] | None = None
    # Per-step timeout override
    timeout_seconds: int | None = None
    # LLM judgment opt-in
    use_llm_judgment: bool = False


class Scenario(BaseModel):
    """A complete test scenario.

    An ordered sequence of action steps with expected outcomes,
    category/priority metadata for budget allocation, and optional
    cleanup steps that always execute.
    """

    id: str
    name: str
    description: str
    category: str
    priority: int = 2
    interfaces: list[str]
    steps: list[ActionStep]
    cleanup: list[ActionStep] | None = None
    tags: list[str] = Field(default_factory=list)
    generated_by: Literal["template", "llm"] = "template"
    # Template parameterization
    parameters: dict[str, list[Any]] | None = None


class StepVerdict(BaseModel):
    """Result of executing one step."""

    step_id: str
    transport: str
    status: Literal["pass", "fail", "error", "skip"]
    actual: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] | None = None
    diff: dict[str, Any] | None = None
    duration_ms: float = 0.0
    error_message: str | None = None
    is_cleanup: bool = False
    captured_vars: dict[str, Any] | None = None


class ScenarioVerdict(BaseModel):
    """Result of evaluating one scenario."""

    scenario_id: str
    scenario_name: str
    status: Literal["pass", "fail", "error", "skip"]
    steps: list[StepVerdict]
    duration_seconds: float = 0.0
    interfaces_tested: list[str] = Field(default_factory=list)
    failure_summary: str | None = None
    cleanup_warnings: list[str] = Field(default_factory=list)
    category: str = ""
    backend_used: str = "template"


class EvalFeedback(BaseModel):
    """Structured feedback from evaluation to guide next generation."""

    iteration: int
    failing_interfaces: list[str] = Field(default_factory=list)
    under_tested_categories: list[str] = Field(default_factory=list)
    near_miss_scenarios: list[str] = Field(default_factory=list)
    suggested_focus: list[str] = Field(default_factory=list)
    coverage_summary: dict[str, float] = Field(default_factory=dict)


class ScenarioGenerator(Protocol):
    """Protocol for scenario generators.

    All generators (template, CLI, SDK, hybrid) implement this protocol,
    enabling the orchestrator to use them interchangeably.
    """

    async def generate(
        self,
        focus_areas: list[str] | None = None,
        count: int = 10,
    ) -> list[Scenario]: ...

"""Core data models for scenarios, verdicts, and generator protocol.

These models form the contract between generators, evaluators, and the
orchestrator. Scenarios are the unit of test generation, verdicts are
the unit of evaluation output.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, model_validator


class ExpectBlock(BaseModel):
    """Expected outcomes for a step.

    Supports HTTP status codes, CLI exit codes, response body assertions
    (via JSONPath), database row counts/values, error message matching,
    non-emptiness checks, and extended assertion types (D1).
    """

    status: int | None = None
    exit_code: int | None = None
    body: dict[str, Any] | None = None
    rows: int | None = None
    row: dict[str, Any] | None = None
    error_contains: str | None = None
    not_empty: bool | None = None
    # Extended assertion types (D1)
    body_contains: dict[str, Any] | None = None
    body_excludes: dict[str, Any] | None = None
    status_one_of: list[int] | None = None
    rows_gte: int | None = None
    rows_lte: int | None = None
    array_contains: list[dict[str, Any]] | None = None

    @model_validator(mode="after")
    def _check_status_mutual_exclusion(self) -> ExpectBlock:
        if self.status is not None and self.status_one_of is not None:
            raise ValueError("'status' and 'status_one_of' are mutually exclusive")
        return self


class SideEffectStep(BaseModel):
    """A single side-effect verification step (D2).

    Used within SideEffectsBlock to declare expected (verify) or
    prohibited (prohibit) side effects of an action step. Side-effect
    steps are read-only (D10): HTTP restricts to GET/HEAD only.
    """

    id: str
    transport: Literal["http", "mcp", "cli", "db"]
    mode: Literal["verify", "prohibit"] = "verify"
    # HTTP (read-only: GET/HEAD only per D10)
    method: str | None = None
    endpoint: str | None = None
    headers: dict[str, str] | None = None
    # MCP
    tool: str | None = None
    params: dict[str, Any] | None = None
    # CLI
    command: str | None = None
    args: list[str] | None = None
    # DB
    sql: str | None = None
    # Expectations
    expect: ExpectBlock | None = None
    # Per-step timeout override
    timeout_seconds: int | None = None

    @model_validator(mode="after")
    def _enforce_read_only_http(self) -> SideEffectStep:
        """D10: Side-effect steps are read-only for HTTP transport."""
        if self.transport == "http" and self.method and self.method.upper() not in ("GET", "HEAD"):
            raise ValueError(
                f"Side-effect steps are read-only: HTTP method must be GET or HEAD, "
                f"got '{self.method}'"
            )
        return self


class SideEffectsBlock(BaseModel):
    """Declarative side-effect verification for an action step (D2).

    Co-located with the producing step for self-documenting scenarios.
    """

    verify: list[SideEffectStep] = Field(default_factory=list)
    prohibit: list[SideEffectStep] = Field(default_factory=list)


class SideEffectVerdict(BaseModel):
    """Result of a single side-effect verification step."""

    step_id: str
    mode: Literal["verify", "prohibit"]
    status: Literal["pass", "fail", "error", "skip"]
    diff: dict[str, Any] | None = None
    error_message: str | None = None
    duration_ms: float = 0.0


class SemanticBlock(BaseModel):
    """Semantic evaluation configuration for an action step (D4).

    When present, the evaluator invokes LLM-as-judge after structural
    assertions pass. Verdicts are additive: they enhance but never
    override structural verdicts.
    """

    judge: bool = True
    criteria: str = ""
    min_confidence: float = 0.7


class SemanticVerdict(BaseModel):
    """Result of semantic (LLM-as-judge) evaluation."""

    status: Literal["pass", "fail", "skip"]
    confidence: float = 0.0
    reasoning: str = ""
    error_message: str | None = None


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
    # LLM judgment opt-in (deprecated — use semantic block)
    use_llm_judgment: bool = False
    # Side-effect verification (D2)
    side_effects: SideEffectsBlock | None = None
    # Semantic evaluation (D4)
    semantic: SemanticBlock | None = None


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
    # Side-effect sub-verdicts
    side_effect_verdicts: list[dict[str, Any]] | None = None
    # Semantic evaluation result
    semantic_verdict: SemanticVerdict | None = None


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

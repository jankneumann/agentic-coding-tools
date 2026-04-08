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
    and non-emptiness checks.

    Extended assertions (D1):
    - body_contains: recursive subset matching on response body
    - body_excludes: negative assertion — body must NOT contain these
    - status_one_of: accept any of several HTTP status codes
    - rows_gte / rows_lte: row count range assertions
    - array_contains: assert a JSON array has an element matching criteria
    """

    status: int | None = None
    exit_code: int | None = None
    body: dict[str, Any] | None = None
    rows: int | None = None
    row: dict[str, Any] | None = None
    error_contains: str | None = None
    not_empty: bool | None = None
    # Extended assertion types
    body_contains: dict[str, Any] | None = None
    body_excludes: dict[str, Any] | None = None
    status_one_of: list[int] | None = None
    rows_gte: int | None = None
    rows_lte: int | None = None
    array_contains: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _status_mutual_exclusion(self) -> ExpectBlock:
        if self.status is not None and self.status_one_of is not None:
            msg = "status and status_one_of are mutually exclusive"
            raise ValueError(msg)
        return self


class SideEffectStep(BaseModel):
    """A verification step within a side_effects block.

    Uses the same transport/query model as ActionStep but scoped to
    verifying that a side effect did (or did not) occur.
    """

    id: str
    transport: Literal["http", "mcp", "cli", "db", "wait"]
    method: str | None = None
    endpoint: str | None = None
    body: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    tool: str | None = None
    params: dict[str, Any] | None = None
    command: str | None = None
    args: list[str] | None = None
    sql: str | None = None
    seconds: float | None = None
    expect: ExpectBlock | None = None
    capture: dict[str, str] | None = None
    timeout_seconds: int | None = None


class SideEffectsBlock(BaseModel):
    """Declarative side-effect verification for an action step (D2).

    verify: steps that MUST succeed (expected side effects occurred).
    prohibit: steps whose expectations MUST NOT match (prohibited
              side effects did not occur). Uses inverse matching (D3).
    """

    verify: list[SideEffectStep] = Field(default_factory=list)
    prohibit: list[SideEffectStep] = Field(default_factory=list)


class SemanticBlock(BaseModel):
    """LLM-as-judge semantic evaluation configuration (D4).

    When judge=True, the evaluator invokes the LLM to assess whether
    the response meets the natural-language criteria. Semantic verdicts
    are additive — they enhance but never override structural verdicts.
    """

    judge: bool = False
    criteria: str = ""
    min_confidence: float = 0.7
    fields: list[str] = Field(default_factory=list)


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


class SideEffectVerdict(BaseModel):
    """Result of a single side-effect verification step."""

    step_id: str
    mode: Literal["verify", "prohibit"]
    status: Literal["pass", "fail", "error", "skip"]
    actual: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] | None = None
    diff: dict[str, Any] | None = None
    error_message: str | None = None


class SemanticVerdict(BaseModel):
    """Result of LLM-as-judge semantic evaluation."""

    status: Literal["pass", "fail", "skip"]
    confidence: float = 0.0
    reasoning: str = ""


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
    side_effect_verdicts: list[SideEffectVerdict] = Field(default_factory=list)
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

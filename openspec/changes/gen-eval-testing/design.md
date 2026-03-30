# Design: Generator-Evaluator Testing Framework

**Change ID**: `gen-eval-testing`
**Date**: 2026-03-30

## Component Design

### 1. Interface Descriptor (`descriptor.py`)

The interface descriptor is the project-specific input that tells the framework what to test. It's a YAML file parsed into a typed Pydantic model.

#### Data Model

```python
class ServiceDescriptor(BaseModel):
    """A single testable service within a project."""
    name: str
    type: Literal["http", "mcp", "cli", "browser"]
    # HTTP-specific
    base_url: str | None = None
    openapi_spec: Path | None = None
    auth: AuthConfig | None = None
    # MCP-specific
    transport: Literal["stdio", "sse"] | None = None
    mcp_url: str | None = None
    tools_manifest: Path | None = None
    # CLI-specific
    command: str | None = None
    cli_schema: Path | None = None
    json_flag: str | None = None
    # Browser-specific
    launch_url: str | None = None

class StateVerifier(BaseModel):
    """A state backend for verification (not interaction)."""
    name: str
    type: Literal["postgres", "sqlite", "filesystem", "redis"]
    dsn_env: str | None = None
    tables: list[str] = []

class StartupConfig(BaseModel):
    """How to start/stop services for evaluation."""
    command: str                         # e.g., "docker-compose up -d"
    health_check: str                    # URL or command to verify readiness
    health_timeout_seconds: int = 60
    teardown: str                        # e.g., "docker-compose down -v"
    seed_command: str | None = None      # Optional data seeding

class InterfaceDescriptor(BaseModel):
    """Top-level project descriptor."""
    project: str
    version: str
    services: list[ServiceDescriptor]
    state_verifiers: list[StateVerifier] = []
    startup: StartupConfig
    scenario_dirs: list[Path] = []       # Template scenario locations
    budget_defaults: BudgetConfig | None = None
```

#### Discovery Mode

For projects without a full descriptor, the framework can auto-discover:
- HTTP endpoints from OpenAPI spec or by probing common paths
- MCP tools via the MCP protocol's `tools/list` method
- CLI commands by parsing `--help` output recursively

### 2. Generator (`generator.py`)

The generator produces `Scenario` objects — ordered sequences of interface actions with expected outcomes.

#### Scenario Data Model

```python
class ActionStep(BaseModel):
    """A single step in a scenario."""
    id: str
    transport: Literal["http", "mcp", "cli", "browser", "db", "wait"]
    # HTTP
    method: str | None = None       # GET, POST, etc.
    endpoint: str | None = None
    body: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    # MCP
    tool: str | None = None
    params: dict[str, Any] | None = None
    # CLI
    command: str | None = None
    args: list[str] | None = None
    # DB (for state verification)
    sql: str | None = None
    # Wait
    seconds: float | None = None
    # Expectations
    expect: ExpectBlock | None = None
    # Parameters for templating
    capture: dict[str, str] | None = None  # JSONPath → variable name

class ExpectBlock(BaseModel):
    """Expected outcomes for a step."""
    status: int | None = None              # HTTP status code
    exit_code: int | None = None           # CLI exit code
    body: dict[str, Any] | None = None     # Response body assertions (JSONPath)
    rows: int | None = None                # DB row count
    row: dict[str, Any] | None = None      # DB row assertions
    error_contains: str | None = None      # Error message substring
    not_empty: bool | None = None

class Scenario(BaseModel):
    """A complete test scenario."""
    id: str
    name: str
    description: str
    category: str                          # e.g., "lock-lifecycle", "auth-boundary"
    priority: int                          # 1=critical, 2=important, 3=coverage
    interfaces: list[str]                  # Which transports this exercises
    steps: list[ActionStep]
    cleanup: list[ActionStep] | None = None
    tags: list[str] = []
    generated_by: Literal["template", "llm"] = "template"
```

#### Module Organization

Generator code is organized into **separate files per strategy**, not one monolithic module:

| File | Class | Purpose |
|------|-------|---------|
| `generator.py` | `TemplateGenerator` | Load YAML templates, parameterize, validate |
| `cli_generator.py` | `CLIGenerator` | Generate scenarios via `claude --print` / `codex` |
| `sdk_generator.py` | `SDKGenerator` | Generate scenarios via Anthropic/OpenAI SDK |
| `hybrid_generator.py` | `HybridGenerator` | Compose template + CLI + SDK with adaptive fallback |

All generators implement a common `ScenarioGenerator` protocol:
```python
class ScenarioGenerator(Protocol):
    async def generate(self, focus_areas: list[str] | None = None,
                       count: int = 10) -> list[Scenario]: ...
```

#### Generation Modes

**Template Generation** (zero cost):
```python
class TemplateGenerator:
    """Load and parameterize YAML scenario templates."""

    def __init__(self, descriptor: InterfaceDescriptor) -> None: ...

    def generate(self,
                 categories: list[str] | None = None,
                 priority_max: int = 3,
                 changed_endpoints: list[str] | None = None
                 ) -> list[Scenario]: ...
```

Templates are YAML files with Jinja2-style parameterization:
```yaml
id: "lock-contention-{{ agent_a }}-{{ agent_b }}"
name: "Lock contention between {{ agent_a }} and {{ agent_b }}"
parameters:
  agent_a: ["claude-1", "codex-1"]
  agent_b: ["gemini-1", "codex-2"]
  file_path: ["src/main.py", "src/config.py"]
steps:
  - id: acquire_a
    transport: http
    method: POST
    endpoint: /locks/acquire
    body:
      file_path: "{{ file_path }}"
      agent_id: "{{ agent_a }}"
    expect:
      status: 200
      body:
        success: true
  - id: acquire_b_conflict
    transport: http
    method: POST
    endpoint: /locks/acquire
    body:
      file_path: "{{ file_path }}"
      agent_id: "{{ agent_b }}"
    expect:
      status: 200
      body:
        success: false
  # ... verify via MCP, release, verify again
```

**CLI-Augmented Generation** (subscription-covered):
```python
class CLIGenerator:
    """Use CLI tools (claude/codex) to generate novel edge-case scenarios.

    Runs claude --print or codex as a subprocess, leveraging subscription
    plans for zero marginal cost. Falls back to direct API calls only
    when explicitly configured (e.g., CI environments without CLI access).
    """

    def __init__(self,
                 descriptor: InterfaceDescriptor,
                 cli_backend: CLIBackend | None = None,  # claude, codex, etc.
                 api_client: Any | None = None,           # API fallback only
                 feedback: list[EvalFeedback] | None = None
                 ) -> None: ...

    async def generate(self,
                       focus_areas: list[str] | None = None,
                       count: int = 5,
                       time_budget: TimeBudget | None = None
                       ) -> list[Scenario]: ...
```

The CLI generator:
1. Builds a prompt containing the interface descriptor, template examples, and evaluator feedback
2. Executes via `claude --print` (or `codex`) as a subprocess — subscription-covered
3. Parses the CLI output as YAML Scenario objects
4. Validates against the Scenario schema before returning
5. Falls back to direct API call only if `api_fallback=True` and CLI is unavailable

```python
class LLMBackend(Protocol):
    """Protocol for LLM execution backends (CLI or SDK)."""
    async def run(self, prompt: str, system: str | None = None) -> str: ...
    async def is_available(self) -> bool: ...
    @property
    def name(self) -> str: ...
    @property
    def is_subscription_covered(self) -> bool: ...

class CLIBackend:
    """Subprocess wrapper for CLI-based LLM execution (subscription-covered)."""

    def __init__(self,
                 command: str = "claude",         # or "codex"
                 args: list[str] | None = None,   # e.g., ["--print"]
                 timeout_seconds: int = 120,
                 ) -> None: ...

    async def run(self, prompt: str, system: str | None = None) -> str:
        """Execute prompt via CLI and return output text."""
        ...

    async def is_available(self) -> bool:
        """Check if CLI tool is installed and accessible."""
        ...

    @property
    def is_subscription_covered(self) -> bool:
        return True

class SDKBackend:
    """Direct SDK-based LLM execution (per-token cost).

    Used as fallback when CLI is rate-limited, hits session/weekly caps,
    or when SDK-specific features are needed (structured outputs, tool use).
    """

    def __init__(self,
                 provider: Literal["anthropic", "openai"] = "anthropic",
                 model: str = "claude-sonnet-4-6",
                 api_key_env: str = "ANTHROPIC_API_KEY",
                 ) -> None: ...

    async def run(self, prompt: str, system: str | None = None) -> str:
        """Execute prompt via SDK and return output text."""
        ...

    async def is_available(self) -> bool:
        """Check if API key is configured."""
        ...

    @property
    def is_subscription_covered(self) -> bool:
        return False

class AdaptiveBackend:
    """Tries CLI first, falls back to SDK on rate limits or caps.

    Detects CLI rate limiting (exit codes, stderr patterns) and
    automatically switches to SDK. Tracks which backend served each
    request for cost reporting.
    """

    def __init__(self,
                 cli: CLIBackend,
                 sdk: SDKBackend | None = None,
                 ) -> None: ...

    async def run(self, prompt: str, system: str | None = None) -> str:
        """Try CLI first, fall back to SDK if rate-limited."""
        ...
```

The generator receives:
1. The interface descriptor (what endpoints/tools exist)
2. Template scenarios as examples of the expected format
3. Evaluator feedback from previous iterations (what failed, what's under-tested) — **`None` on first iteration**
4. Focus areas (changed endpoints, security boundaries, etc.)

It produces Scenario objects validated against the `Scenario` Pydantic model before execution. Invalid scenarios are logged and skipped.

### 3. Evaluator (`evaluator.py`)

The evaluator executes scenarios against live services and produces verdicts.

#### Evaluation Pipeline

```python
class ScenarioVerdict(BaseModel):
    """Result of evaluating one scenario."""
    scenario_id: str
    scenario_name: str
    status: Literal["pass", "fail", "error", "skip"]
    steps: list[StepVerdict]
    duration_seconds: float
    interfaces_tested: list[str]
    failure_summary: str | None = None

class StepVerdict(BaseModel):
    """Result of executing one step."""
    step_id: str
    transport: str
    status: Literal["pass", "fail", "error", "skip"]
    actual: dict[str, Any]            # What we got
    expected: dict[str, Any] | None   # What we expected
    diff: dict[str, Any] | None       # Specific mismatches
    duration_ms: float

class Evaluator:
    """Execute scenarios against live services and judge results."""

    def __init__(self,
                 descriptor: InterfaceDescriptor,
                 clients: TransportClientRegistry,
                 ) -> None: ...

    async def evaluate(self, scenario: Scenario) -> ScenarioVerdict: ...
    async def evaluate_batch(self, scenarios: list[Scenario]) -> list[ScenarioVerdict]: ...
```

#### Verification Strategies

1. **Schema verification** (programmatic, instant): Response matches expected JSON schema
2. **Assertion verification** (programmatic, instant): Specific field values match expectations
3. **State verification** (programmatic, instant): Database queries confirm expected state
4. **Cross-interface verification** (programmatic, instant): Same operation verified across transports
5. **CLI-powered LLM judgment** (subscription-covered): For ambiguous or complex semantic verification where programmatic checks are insufficient. Runs `claude --print` with the verdict context and asks for structured pass/fail judgment with reasoning. Falls back to API only when explicitly configured.

### 4. Transport Clients (`clients/`)

Pluggable client registry — each client knows how to execute an `ActionStep` for its transport.

```python
class TransportClient(Protocol):
    """Protocol for transport-specific execution."""
    async def execute(self, step: ActionStep, context: StepContext) -> StepResult: ...
    async def health_check(self) -> bool: ...
    async def cleanup(self) -> None: ...

class TransportClientRegistry:
    """Registry of available transport clients."""
    def register(self, transport: str, client: TransportClient) -> None: ...
    def get(self, transport: str) -> TransportClient: ...

# Implementations
class HttpClient(TransportClient):     # httpx-based, auth-aware
class McpClient(TransportClient):      # fastmcp SDK, stdio or SSE
class CliClient(TransportClient):      # subprocess with JSON parsing
class DbClient(TransportClient):       # asyncpg for state verification
class BrowserClient(TransportClient):  # Playwright (stub for now)
class WaitClient(TransportClient):     # asyncio.sleep for timing scenarios
```

#### Variable Capture and Interpolation

Steps can capture values from responses for use in later steps:

```yaml
- id: submit_task
  transport: http
  method: POST
  endpoint: /work/submit
  body: { task_type: "test", task_description: "Test task" }
  capture:
    task_id: "$.task_id"  # JSONPath capture

- id: claim_task
  transport: http
  method: POST
  endpoint: /work/claim
  body: { agent_id: "agent-1", agent_type: "claude_code" }
  expect:
    body:
      task_id: "{{ task_id }}"  # Use captured value
```

### 5. Orchestrator (`orchestrator.py`)

Manages the full gen-eval lifecycle.

```python
class GenEvalOrchestrator:
    """Top-level orchestrator for generator-evaluator runs."""

    def __init__(self,
                 config: GenEvalConfig,
                 descriptor: InterfaceDescriptor,
                 generator: ScenarioGenerator,  # Template or LLM or hybrid
                 evaluator: Evaluator,
                 ) -> None: ...

    async def run(self) -> GenEvalReport:
        """Execute the full gen-eval pipeline."""
        # 1. Start services (docker-compose up, health check)
        # 2. Seed data if configured
        # 3. Generate scenarios (template + LLM within budget)
        # 4. Prioritize (changed features first)
        # 5. Evaluate scenarios (execute + verify)
        # 6. Synthesize feedback
        # 7. If budget remains and iterations configured: loop to step 3
        # 8. Generate report
        # 9. Teardown services
```

#### Budget Tracking

The budget model is **time-based** for CLI execution (subscription-covered) with an optional USD cap for API fallback mode.

```python
class TimeBudget(BaseModel):
    """Time-based budget for CLI-powered evaluation (subscription-covered)."""
    total_minutes: float = 60.0          # Wall-clock limit
    elapsed_minutes: float = 0.0
    cli_calls: int = 0                   # Track rate limit pressure
    max_cli_calls: int | None = None     # Optional rate limit cap
    generation_minutes: float = 0.0
    evaluation_minutes: float = 0.0

    def can_continue(self) -> bool: ...
    def record_call(self, category: str, duration_seconds: float) -> None: ...
    @property
    def remaining_minutes(self) -> float: ...

class SDKBudget(BaseModel):
    """USD budget for SDK-based execution (sdk-only mode or adaptive fallback)."""
    budget_usd: float = 5.0
    spent_usd: float = 0.0
    generation_spent: float = 0.0
    evaluation_spent: float = 0.0

    def can_afford(self, estimated_cost: float) -> bool: ...
    def record(self, category: str, tokens: TokenUsage) -> None: ...

class BudgetTracker(BaseModel):
    """Unified budget tracker supporting CLI (time) and API (cost) modes."""
    mode: Literal["cli", "api"] = "cli"
    time_budget: TimeBudget = TimeBudget()
    sdk_budget: SDKBudget | None = None  # Used in sdk-only mode or adaptive fallback

    def can_continue(self) -> bool: ...
```

#### Changed-Feature Detection

```python
class ChangeDetector:
    """Detect which interfaces changed for targeted evaluation."""

    def detect_from_git_diff(self, base_ref: str = "main") -> list[str]:
        """Parse git diff to identify changed endpoints/tools/commands."""
        ...

    def detect_from_openspec(self, change_id: str) -> list[str]:
        """Read change-context.md to identify affected interfaces."""
        ...
```

### 6. Feedback Synthesis (`feedback.py`)

The feedback loop is what makes this more than just a test runner. After each evaluation round, the evaluator's findings are synthesized into structured guidance for the next round of generation.

```python
class EvalFeedback(BaseModel):
    """Structured feedback from evaluation to guide next generation."""
    iteration: int
    failing_interfaces: list[str]          # Endpoints/tools that failed
    under_tested_categories: list[str]     # Categories with low coverage
    near_miss_scenarios: list[str]         # Scenarios that barely passed
    suggested_focus: list[str]             # What to explore next
    coverage_summary: dict[str, float]     # Interface → coverage percentage

class FeedbackSynthesizer:
    """Synthesize evaluator verdicts into generator guidance."""

    def synthesize(self,
                   verdicts: list[ScenarioVerdict],
                   descriptor: InterfaceDescriptor,
                   previous_feedback: EvalFeedback | None = None
                   ) -> EvalFeedback: ...
```

### 7. Coordinator Integration

When the coordinator is available, the framework uses it for:

```python
class CoordinatorIntegration:
    """Optional coordinator integration for distributed evaluation."""

    async def distribute_scenarios(self, scenarios: list[Scenario]) -> list[str]:
        """Submit scenarios as work queue tasks for parallel evaluation."""
        ...

    async def store_findings(self, report: GenEvalReport) -> None:
        """Store evaluation findings in coordinator memory for trend analysis."""
        ...

    async def recall_previous_findings(self, project: str) -> list[EvalFeedback]:
        """Recall findings from previous runs to inform generation."""
        ...
```

### 8. Configuration (`config.py`)

```python
class BudgetConfig(BaseModel):
    """Cost budget for a gen-eval run."""
    total_usd: float = 5.0
    generation_pct: float = 0.4      # 40% for scenario generation
    evaluation_pct: float = 0.6      # 60% for evaluation judgment
    tier1_pct: float = 0.40          # Changed features
    tier2_pct: float = 0.35          # Critical paths
    tier3_pct: float = 0.25          # Full surface

class GenEvalConfig(BaseModel):
    """Configuration for a gen-eval run."""
    descriptor_path: Path
    mode: Literal["template-only", "cli-augmented", "sdk-only"] = "template-only"  # cli-augmented includes adaptive SDK fallback
    # CLI backend config (subscription-covered, preferred)
    cli_command: str = "claude"          # "claude" or "codex"
    cli_args: list[str] = ["--print"]   # Args for CLI invocation
    # SDK backend config (per-token, fallback or explicit)
    sdk_provider: str = "anthropic"      # "anthropic" or "openai"
    sdk_model: str = "claude-sonnet-4-6" # Model for SDK calls
    sdk_api_key_env: str = "ANTHROPIC_API_KEY"
    # Budget
    time_budget_minutes: float = 60.0    # Wall-clock limit for CLI mode
    sdk_budget_usd: float | None = None  # Cap for SDK calls (fallback or sdk-only)
    # Adaptive behavior (cli-augmented mode)
    auto_fallback_to_sdk: bool = True    # Fall back to SDK when CLI rate-limited
    # Execution
    max_iterations: int = 1              # Feedback loop iterations
    max_scenarios_per_iteration: int = 50
    parallel_scenarios: int = 5          # Concurrent scenario execution
    changed_features_ref: str | None = None  # Git ref for change detection
    openspec_change_id: str | None = None    # OpenSpec change for targeting
    use_coordinator: bool = False
    report_format: Literal["markdown", "json", "both"] = "both"
    fail_threshold: float = 0.95         # Minimum pass rate to succeed
    seed_data: bool = True
    verbose: bool = False
```

## Scenario Templates (Dogfood)

### Template Categories for Agent-Coordinator

| Category | Success | Failure/Edge | Total | Priority | Description |
|----------|---------|-------------|-------|----------|-------------|
| `lock-lifecycle` | 4 | 4 | 8 | 1 | Acquire, release, conflict, TTL expiry, cross-interface |
| `work-queue` | 5 | 5 | 10 | 1 | Submit, claim, complete, dependencies, priority, error |
| `memory-crud` | 3 | 3 | 6 | 2 | Store, query, relevance filtering, tag search, empty results |
| `guardrails` | 2 | 3 | 5 | 1 | Block destructive ops, allow safe ops, severity levels |
| `auth-boundary` | 3 | 5 | 8 | 1 | Valid key, missing key, invalid key, trust levels, policy denial |
| `handoffs` | 2 | 2 | 4 | 2 | Write/read handoff docs, agent filtering, empty handoffs |
| `audit-trail` | 2 | 2 | 4 | 2 | Operations produce entries, query filters, empty audit |
| `cross-interface` | 5 | 5 | 10 | 1 | Same operation verified across HTTP, MCP, CLI, DB |
| `multi-agent` | 3 | 5 | 8 | 1 | Concurrent agents, lock contention, work claiming races |
| `policy-engine` | 3 | 3 | 6 | 2 | Cedar policy check, native policy, validation, denial |
| `feature-registry` | 3 | 3 | 6 | 2 | Register, deregister, conflict analysis, duplicate |
| `merge-queue` | 3 | 3 | 6 | 2 | Enqueue, priority ordering, pre-merge checks, empty |
| **Total** | **38** | **43** | **81** | | |

> Each category includes both success-path and failure/edge-case scenarios to ensure REQ-SCN-06 compliance.

### Example Template: Multi-Agent Lock Contention

```yaml
id: multi-agent-lock-contention
name: "Two agents compete for the same lock"
category: multi-agent
priority: 1
interfaces: [http, mcp, db]
tags: [locks, contention, multi-agent]

steps:
  # Agent 1 acquires lock via HTTP
  - id: agent1_acquire
    transport: http
    method: POST
    endpoint: /locks/acquire
    body:
      file_path: "src/contended.py"
      agent_id: "agent-1"
      agent_type: "claude_code"
      reason: "Editing contended file"
    expect:
      status: 200
      body: { success: true }

  # Agent 2 tries to acquire same lock via MCP — should fail
  - id: agent2_acquire_fails
    transport: mcp
    tool: acquire_lock
    params:
      file_path: "src/contended.py"
      reason: "Also want to edit"
    expect:
      body: { success: false }

  # Verify lock state in database
  - id: verify_db_state
    transport: db
    sql: >
      SELECT agent_id, locked
      FROM file_locks
      WHERE file_path = 'src/contended.py'
    expect:
      rows: 1
      row: { agent_id: "agent-1", locked: true }

  # Agent 1 releases via CLI
  - id: agent1_release
    transport: cli
    command: "lock release --file-path src/contended.py --agent-id agent-1"
    expect:
      exit_code: 0

  # Agent 2 retries — should succeed now
  - id: agent2_acquire_succeeds
    transport: mcp
    tool: acquire_lock
    params:
      file_path: "src/contended.py"
      reason: "Retrying after release"
    expect:
      body: { success: true }

cleanup:
  - id: cleanup_lock
    transport: http
    method: POST
    endpoint: /locks/release
    body:
      file_path: "src/contended.py"
      agent_id: "agent-2"
```

## Entry Points

### CLI Entry Point

```bash
# Template-only run (instant, no LLM)
python -m evaluation.gen_eval \
  --descriptor evaluation/gen_eval/descriptors/agent-coordinator.yaml \
  --mode template-only

# CLI-augmented run using claude CLI (subscription-covered, $0 marginal cost)
python -m evaluation.gen_eval \
  --descriptor evaluation/gen_eval/descriptors/agent-coordinator.yaml \
  --mode cli-augmented \
  --cli-command claude \
  --time-budget 30 \
  --changed-features-ref main

# CLI-augmented comprehensive run with codex
python -m evaluation.gen_eval \
  --descriptor evaluation/gen_eval/descriptors/agent-coordinator.yaml \
  --mode cli-augmented \
  --cli-command codex \
  --time-budget 120 \
  --max-iterations 3

# SDK-only mode (explicit opt-in, per-token cost, for CI without CLI)
python -m evaluation.gen_eval \
  --descriptor evaluation/gen_eval/descriptors/agent-coordinator.yaml \
  --mode sdk-only \
  --sdk-budget 10.0
```

### Skill Entry Point

```
/gen-eval [--descriptor PATH] [--mode template-only|cli-augmented|sdk-only] [--cli claude|codex] [--time-budget MINUTES] [--change-id ID]
```

### validate-feature Integration

Added as an optional phase between smoke and E2E:
```
Phase: gen-eval (non-critical)
  Trigger: when gen-eval descriptor exists for the project
  Mode: template-only (CI) or hybrid (manual)
  Budget: $5 default, configurable
  Output: gen-eval verdict in validation report
```

## Testing Strategy

### Unit Tests (mock services)
- Descriptor parsing and validation
- Template loading and parameterization
- Scenario schema validation
- Budget tracking arithmetic
- Change detection from git diff
- Feedback synthesis logic

### Integration Tests (real services, deterministic)
- Template scenarios against docker-compose services
- Cross-interface consistency checks
- Variable capture and interpolation
- Cleanup step execution

### Framework Tests (meta: test the tester)
- Generator produces valid scenarios
- Evaluator correctly identifies pass/fail
- Orchestrator respects budget limits
- Feedback loop improves coverage across iterations

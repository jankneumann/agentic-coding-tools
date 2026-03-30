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

**LLM Generation** (uses budget):
```python
class LLMGenerator:
    """Use LLM to generate novel edge-case scenarios."""

    def __init__(self,
                 descriptor: InterfaceDescriptor,
                 model: str = "claude-sonnet-4-6",
                 feedback: list[EvalFeedback] | None = None
                 ) -> None: ...

    async def generate(self,
                       focus_areas: list[str] | None = None,
                       count: int = 5,
                       budget: BudgetTracker | None = None
                       ) -> list[Scenario]: ...
```

The LLM generator receives:
1. The interface descriptor (what endpoints/tools exist)
2. Template scenarios as examples of the expected format
3. Evaluator feedback from previous iterations (what failed, what's under-tested)
4. Focus areas (changed endpoints, security boundaries, etc.)

It produces Scenario objects validated against the schema before execution.

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

1. **Schema verification** (programmatic, free): Response matches expected JSON schema
2. **Assertion verification** (programmatic, free): Specific field values match expectations
3. **State verification** (programmatic, free): Database queries confirm expected state
4. **Cross-interface verification** (programmatic, free): Same operation verified across transports
5. **LLM judgment** (uses budget): For ambiguous or complex semantic verification where programmatic checks are insufficient

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

```python
class BudgetTracker:
    """Track LLM API costs against configured budget."""
    budget_usd: float
    spent_usd: float = 0.0
    generation_spent: float = 0.0
    evaluation_spent: float = 0.0

    def can_afford(self, estimated_cost: float) -> bool: ...
    def record(self, category: str, tokens: TokenUsage) -> None: ...
    @property
    def remaining(self) -> float: ...
    @property
    def utilization(self) -> float: ...
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
    mode: Literal["template-only", "hybrid", "llm-only"] = "template-only"
    budget: BudgetConfig = BudgetConfig()
    max_iterations: int = 1           # Feedback loop iterations
    max_scenarios_per_iteration: int = 50
    parallel_scenarios: int = 5       # Concurrent scenario execution
    changed_features_ref: str | None = None  # Git ref for change detection
    openspec_change_id: str | None = None    # OpenSpec change for targeting
    use_coordinator: bool = False
    report_format: Literal["markdown", "json", "both"] = "both"
    fail_threshold: float = 0.95     # Minimum pass rate to succeed
    seed_data: bool = True
    verbose: bool = False
```

## Scenario Templates (Dogfood)

### Template Categories for Agent-Coordinator

| Category | Count | Priority | Description |
|----------|-------|----------|-------------|
| `lock-lifecycle` | 8 | 1 | Acquire, release, conflict, TTL expiry, cross-interface |
| `work-queue` | 10 | 1 | Submit, claim, complete, dependencies, priority ordering |
| `memory-crud` | 6 | 2 | Store, query, relevance filtering, tag search |
| `guardrails` | 5 | 1 | Block destructive ops, allow safe ops, severity levels |
| `auth-boundary` | 8 | 1 | API key enforcement, missing auth, invalid auth, profile trust |
| `handoffs` | 4 | 2 | Write/read handoff docs, agent-specific filtering |
| `audit-trail` | 4 | 2 | All operations produce audit entries, queryable |
| `cross-interface` | 10 | 1 | Same operation verified across HTTP, MCP, CLI, DB |
| `multi-agent` | 8 | 1 | Concurrent agents, lock contention, work claiming races |
| `policy-engine` | 5 | 2 | Cedar policy check, native policy, policy validation |
| `feature-registry` | 6 | 2 | Register, deregister, conflict analysis |
| `merge-queue` | 6 | 2 | Enqueue, priority ordering, pre-merge checks |
| **Total** | **80** | | |

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
# Template-only run against dogfood descriptor
python -m evaluation.gen_eval \
  --descriptor evaluation/gen_eval/descriptors/agent-coordinator.yaml \
  --mode template-only

# Hybrid run with $20 budget targeting changed features
python -m evaluation.gen_eval \
  --descriptor evaluation/gen_eval/descriptors/agent-coordinator.yaml \
  --mode hybrid \
  --budget 20.0 \
  --changed-features-ref main

# Full comprehensive run
python -m evaluation.gen_eval \
  --descriptor evaluation/gen_eval/descriptors/agent-coordinator.yaml \
  --mode hybrid \
  --budget 50.0 \
  --max-iterations 3
```

### Skill Entry Point

```
/gen-eval [--descriptor PATH] [--mode template-only|hybrid] [--budget USD] [--change-id ID]
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

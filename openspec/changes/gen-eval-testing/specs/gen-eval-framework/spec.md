# Spec: Generator-Evaluator Testing Framework

**Change ID**: `gen-eval-testing`
**Capability**: `gen-eval-framework`

## Requirements

### Interface Descriptor (REQ-DESC)

- **REQ-DESC-01**: The framework MUST accept an interface descriptor (YAML) that declaratively describes a project's testable surface including HTTP endpoints, MCP tools, CLI commands, and state verifiers.
- **REQ-DESC-02**: The descriptor MUST include service startup/teardown configuration (command, health check URL/command, teardown command, health check timeout, and retry count).
- **REQ-DESC-03**: The framework MUST support auto-discovery of HTTP endpoints from OpenAPI specs, MCP tools from `tools/list`, and CLI commands from `--help` output.
- **REQ-DESC-04**: The descriptor format MUST be project-agnostic — no hardcoded references to agent-coordinator internals.

### Scenario Generation (REQ-GEN)

- **REQ-GEN-01**: The framework MUST support template-based scenario generation from YAML files with parameterization (Jinja2-style variable substitution and combinatorial expansion). Combinatorial expansion MUST be capped by a configurable `max_expansions` limit (default: 100) to prevent combinatorial explosion.
- **REQ-GEN-02**: The framework MUST support CLI-augmented scenario generation using subscription-covered CLI tools (`claude --print`, `codex`) that reads the interface descriptor and evaluator feedback to produce novel edge-case scenarios.
- **REQ-GEN-03**: Generated scenarios MUST be validated against the `Scenario` Pydantic model schema before execution. Invalid scenarios MUST be logged and skipped, not halt the run.
- **REQ-GEN-04**: The framework MUST support three generation modes: `template-only` (no LLM), `cli-augmented` (subscription-covered CLI tools, with adaptive SDK fallback), `sdk-only` (per-token, for CI without CLI access).
- **REQ-GEN-05**: The generator MUST accept focus areas (changed endpoints, categories) to produce targeted scenarios.
- **REQ-GEN-06**: The framework MUST default to CLI-based LLM execution (`claude --print`, `codex`) as the subscription-covered path.
- **REQ-GEN-07**: The framework MUST provide an `AdaptiveBackend` that detects CLI rate limiting by checking: (a) non-zero exit codes with stderr containing "rate limit", "too many requests", or "quota exceeded"; (b) HTTP 429 status in stderr; (c) configurable custom patterns via `rate_limit_patterns` in config. On detection, it MUST transparently fall back to SDK-based execution for remaining calls in the current iteration.
- **REQ-GEN-08**: SDK-based execution MUST be available as an explicit `sdk-only` mode for CI environments without CLI access, and as automatic fallback in `cli-augmented` mode when CLI is rate-limited. If both CLI and SDK fail, the framework MUST log the error and continue with template-only scenarios.

### Scenario Model (REQ-SCN)

- **REQ-SCN-01**: A scenario MUST be an ordered sequence of action steps, each targeting a specific transport (http, mcp, cli, db, wait). Steps MUST execute sequentially — step N completes before step N+1 begins — to preserve variable capture dependencies.
- **REQ-SCN-02**: Each step MUST support an expect block for asserting response status, body content (via JSONPath expressions), row counts, and error messages.
- **REQ-SCN-03**: Steps MUST support variable capture using JSONPath expressions (`$.field.path`) to extract values from responses, and Jinja2-style interpolation (`{{ var }}`) to inject captured values into subsequent steps. Invalid JSONPath expressions MUST produce a step-level error verdict, not crash the scenario.
- **REQ-SCN-04**: Scenarios MUST support cleanup steps that execute after the main steps regardless of pass/fail outcome. If a cleanup step fails, the failure MUST be recorded in the verdict as a warning but MUST NOT change the scenario's pass/fail status.
- **REQ-SCN-05**: Scenarios MUST have category, priority, and interface tags for filtering and budget allocation.
- **REQ-SCN-06**: Each scenario MUST include at least one failure/error-path step or be tagged `happy-path-only`. Template categories MUST include both success and failure scenarios (e.g., "lock acquire succeeds" AND "lock acquire fails when already held").
- **REQ-SCN-07**: Each step MUST have a configurable timeout (default: 30 seconds). Steps exceeding their timeout MUST produce an `error` verdict with "timeout" reason.

### Transport Clients (REQ-TRN)

- **REQ-TRN-01**: The framework MUST provide pluggable transport clients for HTTP (httpx), MCP (fastmcp SDK), CLI (subprocess), and database (asyncpg). Each client MUST implement the `TransportClient` protocol: `async execute(step, context) -> StepResult`, `async health_check() -> bool`, `async cleanup() -> None`.
- **REQ-TRN-02**: The HTTP client MUST support auth injection (API key headers) configured via the interface descriptor.
- **REQ-TRN-03**: The CLI client MUST parse JSON output (when `json_flag` is configured) and check exit codes.
- **REQ-TRN-04**: The database client MUST be read-only (SELECT queries only) — it verifies state, never mutates.
- **REQ-TRN-05**: Transport selection MUST be explicit per step via the `transport` field in the scenario YAML. There is no automatic transport inference.

### Evaluation (REQ-EVAL)

- **REQ-EVAL-01**: The evaluator MUST execute scenario steps sequentially through the transport client specified by each step's `transport` field and compare actual responses against expected values using programmatic assertion matching.
- **REQ-EVAL-02**: The evaluator MUST produce a structured `ScenarioVerdict` with per-step pass/fail/error status, actual vs expected values, diff details, and failure summaries.
- **REQ-EVAL-03**: The evaluator MUST support cross-interface consistency verification — the same state checked across multiple transports within one scenario. A cross-interface inconsistency (e.g., API returns `locked=true` but MCP returns `locked=false` for the same resource) MUST be reported as a `fail` with a structured diff showing both responses.
- **REQ-EVAL-04**: The evaluator MUST verify database state directly (not just API responses) when db steps are present in a scenario.
- **REQ-EVAL-05**: Evaluation MUST be independent — the evaluator has no access to the generator's intent, only the scenario spec and live service responses. Independence is enforced by the evaluator receiving only `Scenario` objects (not generator internals).
- **REQ-EVAL-06**: The evaluator MAY use CLI-powered LLM judgment (`claude --print`) for ambiguous verdict assessment where programmatic checks are insufficient. LLM judgment MUST be opt-in via a `use_llm_judgment: true` flag on the scenario or step, and MUST produce a structured `{verdict: pass|fail, confidence: float, reasoning: str}` response.

### Budget Management (REQ-BDG)

- **REQ-BDG-01**: In `cli-augmented` mode, the framework MUST enforce a configurable **time budget** (wall-clock minutes, default: 60) since CLI usage is subscription-covered with zero marginal cost.
- **REQ-BDG-02**: In `sdk-only` mode, the framework MUST enforce a configurable **USD budget cap** (default: $5) for per-token API calls.
- **REQ-BDG-03**: Template execution and programmatic evaluation MUST NOT count against any budget (they are instant and free).
- **REQ-BDG-04**: The framework MUST allocate scope progressively: changed features (tier 1, 40% of budget) → critical paths (tier 2, 35%) → full surface (tier 3, 25%). Percentages MUST be configurable.
- **REQ-BDG-05**: The framework MUST terminate gracefully when budget (time or USD) is exhausted: complete the current scenario, skip remaining scenarios, and produce a partial report with a `budget_exhausted: true` flag and the list of unevaluated scenarios.
- **REQ-BDG-06**: The framework MUST track and report: CLI calls made, wall-clock time consumed, and (in SDK mode) USD cost per generation/evaluation. When `AdaptiveBackend` is active, the report MUST separately attribute calls to CLI vs SDK backends.

### Feedback Loop (REQ-FBK)

- **REQ-FBK-01**: The evaluator's findings MUST be synthesized into structured `EvalFeedback` identifying: failing interfaces (list of endpoint/tool names), under-tested categories (categories with < 50% scenario coverage), near-miss scenarios (scenarios that passed but with > 500ms latency or partial assertion matches), and suggested focus areas.
- **REQ-FBK-02**: The feedback MUST be formatted as a prompt-compatible text block consumable by the CLI/SDK generator to guide subsequent scenario generation. The first iteration MUST pass `feedback=None` to the generator.
- **REQ-FBK-03**: The orchestrator MUST support multiple gen-eval iterations (configurable, default: 1) with feedback flowing from iteration N's evaluator to iteration N+1's generator.

### Orchestration (REQ-ORC)

- **REQ-ORC-01**: The orchestrator MUST manage the full lifecycle: service startup → health check (with configurable retry count and backoff) → seed data → generate → prioritize → evaluate → feedback → iterate → report → teardown. If health check fails after all retries, the run MUST abort with a clear error.
- **REQ-ORC-02**: The orchestrator MUST support parallel scenario execution using `asyncio.Semaphore` with a configurable concurrency limit (default: 5).
- **REQ-ORC-03**: The orchestrator MUST detect changed features by parsing `git diff --name-only <ref>` output and mapping changed source files to interface endpoints/tools using a configurable file-to-interface mapping in the descriptor.
- **REQ-ORC-04**: The orchestrator MUST produce structured reports (markdown + JSON) with: per-interface verdict (pass/fail/error count), per-category summary, interface coverage percentage (= unique interfaces tested / total interfaces in descriptor × 100), cost/time summary, and list of unevaluated interfaces.

### Integration (REQ-INT)

- **REQ-INT-01**: The framework MUST integrate with the existing `evaluation/metrics.py` for metrics collection (TokenUsage, timing, correctness).
- **REQ-INT-02**: The framework MUST be invocable as a CLI (`python -m evaluation.gen_eval`), as a skill (`/gen-eval`), and as a phase within `validate-feature`.
- **REQ-INT-03**: When a coordinator is available, the framework SHOULD use the work queue for distributed scenario execution and memory for cross-run finding storage. When unavailable, the framework MUST continue operating standalone without error.
- **REQ-INT-04**: The framework MUST add a CI job that runs `template-only` evaluation against docker-compose services, with a 10-minute timeout and fail-fast on 3 consecutive failures.

### Dogfood (REQ-DOG)

- **REQ-DOG-01**: The first interface descriptor MUST cover all 35 HTTP API endpoints, 39 MCP tools, and 31 CLI commands of the agent-coordinator.
- **REQ-DOG-02**: Template scenarios MUST include both success and failure paths for at minimum: lock lifecycle, work queue operations, auth boundaries, cross-interface consistency, and multi-agent contention.
- **REQ-DOG-03**: The dogfood descriptor MUST achieve 80%+ interface coverage (= unique interfaces exercised by at least one template scenario / total interfaces in descriptor × 100) with template scenarios alone.

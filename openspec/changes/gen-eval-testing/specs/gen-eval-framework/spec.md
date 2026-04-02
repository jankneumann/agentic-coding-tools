# Spec: Generator-Evaluator Testing Framework

**Change ID**: `gen-eval-testing`
**Capability**: `gen-eval-framework`

## ADDED Requirements

### Requirement: Interface Descriptor

The framework MUST accept an interface descriptor (YAML) that declaratively describes a project's testable surface including HTTP endpoints, MCP tools, CLI commands, and state verifiers.

The descriptor MUST include service startup/teardown configuration (command, health check URL/command, teardown command, health check timeout, and retry count).

The framework MUST support auto-discovery of HTTP endpoints from OpenAPI specs, MCP tools from `tools/list`, and CLI commands from `--help` output.

The descriptor format MUST be project-agnostic — no hardcoded references to agent-coordinator internals.

#### Scenario: Descriptor validates project surface
Given a YAML interface descriptor for a project
When the framework loads the descriptor
Then it correctly identifies HTTP endpoints, MCP tools, CLI commands, and state verifiers

#### Scenario: Descriptor supports service lifecycle config
Given a descriptor with startup command, health check URL, and teardown command
When the orchestrator starts and stops the service
Then it uses the configured lifecycle settings including retry count and timeout

#### Scenario: Auto-discovery populates descriptor surface
Given a project with an OpenAPI spec and an MCP server
When auto-discovery runs
Then HTTP endpoints are populated from the OpenAPI spec and MCP tools from `tools/list`

---

### Requirement: Scenario Generation

The framework MUST support template-based scenario generation from YAML files with parameterization (Jinja2-style variable substitution and combinatorial expansion). Combinatorial expansion MUST be capped by a configurable `max_expansions` limit (default: 100) to prevent combinatorial explosion.

The framework MUST support CLI-augmented scenario generation using subscription-covered CLI tools (`claude --print`, `codex`) that reads the interface descriptor and evaluator feedback to produce novel edge-case scenarios.

Generated scenarios MUST be validated against the `Scenario` Pydantic model schema before execution. Invalid scenarios MUST be logged and skipped, not halt the run.

The framework MUST support three generation modes: `template-only` (no LLM), `cli-augmented` (subscription-covered CLI tools, with adaptive SDK fallback), `sdk-only` (per-token, for CI without CLI access).

The generator MUST accept focus areas (changed endpoints, categories) to produce targeted scenarios.

The framework MUST default to CLI-based LLM execution (`claude --print`, `codex`) as the subscription-covered path.

The framework MUST provide an `AdaptiveBackend` that detects CLI rate limiting by checking: (a) non-zero exit codes with stderr containing "rate limit", "too many requests", or "quota exceeded"; (b) HTTP 429 status in stderr; (c) configurable custom patterns via `rate_limit_patterns` in config. On detection, it MUST transparently fall back to SDK-based execution for remaining calls in the current iteration.

SDK-based execution MUST be available as an explicit `sdk-only` mode for CI environments without CLI access, and as automatic fallback in `cli-augmented` mode when CLI is rate-limited. If both CLI and SDK fail, the framework MUST log the error and continue with template-only scenarios.

#### Scenario: Template generation expands parameters
Given a YAML template with combinatorial parameters and `max_expansions: 100`
When the generator expands the template
Then it produces parameterized scenario variants up to the configured cap

#### Scenario: CLI-augmented generation produces novel scenarios
Given a loaded interface descriptor and evaluator feedback from a prior iteration
When the generator runs in `cli-augmented` mode
Then it invokes `claude --print` and returns edge-case scenarios not present in templates

#### Scenario: Invalid scenarios are skipped
Given a generator that produces a scenario failing Pydantic model validation
When the framework validates generated scenarios
Then the invalid scenario is logged and skipped without halting the run

#### Scenario: AdaptiveBackend falls back on rate limit
Given a CLI tool that returns a non-zero exit code with "rate limit" in stderr
When `AdaptiveBackend` detects the signal
Then it transparently switches to SDK-based execution for remaining calls

#### Scenario: sdk-only mode runs without CLI
Given a CI environment with no CLI tool available
When the framework runs in `sdk-only` mode
Then it generates scenarios using the SDK without attempting CLI invocation

---

### Requirement: Scenario Model

A scenario MUST be an ordered sequence of action steps, each targeting a specific transport (http, mcp, cli, db, wait). Steps MUST execute sequentially — step N completes before step N+1 begins — to preserve variable capture dependencies.

Each step MUST support an expect block for asserting response status, body content (via JSONPath expressions), row counts, and error messages.

Steps MUST support variable capture using JSONPath expressions (`$.field.path`) to extract values from responses, and Jinja2-style interpolation (`{{ var }}`) to inject captured values into subsequent steps. Invalid JSONPath expressions MUST produce a step-level error verdict, not crash the scenario.

Scenarios MUST support cleanup steps that execute after the main steps regardless of pass/fail outcome. If a cleanup step fails, the failure MUST be recorded in the verdict as a warning but MUST NOT change the scenario's pass/fail status.

Scenarios MUST have category, priority, and interface tags for filtering and budget allocation.

Each scenario MUST include at least one failure/error-path step or be tagged `happy-path-only`. Template categories MUST include both success and failure scenarios (e.g., "lock acquire succeeds" AND "lock acquire fails when already held").

Each step MUST have a configurable timeout (default: 30 seconds). Steps exceeding their timeout MUST produce an `error` verdict with "timeout" reason.

#### Scenario: Sequential steps preserve capture order
Given a scenario where step 1 captures an ID and step 2 uses `{{ id }}` in its request
When the scenario executes
Then step 2 receives the value captured from step 1's response

#### Scenario: Invalid JSONPath produces step-level error
Given a scenario step with a malformed JSONPath expression in variable capture
When the step executes
Then it produces a step-level `error` verdict and the scenario continues

#### Scenario: Cleanup steps run on failure
Given a scenario where the main steps fail and cleanup steps are defined
When evaluation completes
Then cleanup steps execute and any cleanup failure is recorded as a warning only

#### Scenario: Step timeout produces error verdict
Given a scenario step with `timeout: 5` seconds targeting a slow service
When the step exceeds its timeout
Then the verdict is `error` with reason "timeout"

---

### Requirement: Transport Clients

The framework MUST provide pluggable transport clients for HTTP (httpx), MCP (fastmcp SDK), CLI (subprocess), and database (asyncpg). Each client MUST implement the `TransportClient` protocol: `async execute(step, context) -> StepResult`, `async health_check() -> bool`, `async cleanup() -> None`.

The HTTP client MUST support auth injection (API key headers) configured via the interface descriptor.

The CLI client MUST parse JSON output (when `json_flag` is configured) and check exit codes.

The database client MUST be read-only (SELECT queries only) — it verifies state, never mutates.

Transport selection MUST be explicit per step via the `transport` field in the scenario YAML. There is no automatic transport inference.

#### Scenario: HTTP client injects auth header
Given an interface descriptor with an API key header configured
When an HTTP transport step executes
Then the request includes the configured auth header

#### Scenario: Database client rejects mutation queries
Given a scenario step targeting the `db` transport with an INSERT statement
When the step executes
Then the client rejects the query and produces an error verdict

#### Scenario: Explicit transport selection routes correctly
Given a scenario with steps specifying `transport: mcp` and `transport: http` respectively
When the scenario executes
Then each step is routed to its declared transport client without inference

---

### Requirement: Evaluation

The evaluator MUST execute scenario steps sequentially through the transport client specified by each step's `transport` field and compare actual responses against expected values using programmatic assertion matching.

The evaluator MUST produce a structured `ScenarioVerdict` with per-step pass/fail/error status, actual vs expected values, diff details, and failure summaries.

The evaluator MUST support cross-interface consistency verification — the same state checked across multiple transports within one scenario. A cross-interface inconsistency (e.g., API returns `locked=true` but MCP returns `locked=false` for the same resource) MUST be reported as a `fail` with a structured diff showing both responses.

The evaluator MUST verify database state directly (not just API responses) when db steps are present in a scenario.

Evaluation MUST be independent — the evaluator has no access to the generator's intent, only the scenario spec and live service responses. Independence is enforced by the evaluator receiving only `Scenario` objects (not generator internals).

The evaluator MAY use CLI-powered LLM judgment (`claude --print`) for ambiguous verdict assessment where programmatic checks are insufficient. LLM judgment MUST be opt-in via a `use_llm_judgment: true` flag on the scenario or step, and MUST produce a structured `{verdict: pass|fail, confidence: float, reasoning: str}` response.

#### Scenario: Evaluator produces structured verdict
Given a scenario with multiple steps that pass and one that fails
When the evaluator runs the scenario
Then `ScenarioVerdict` contains per-step status, actual vs expected values, and a failure summary

#### Scenario: Cross-interface inconsistency is reported as fail
Given a scenario that checks the same lock resource via HTTP and MCP steps
When the HTTP step returns `locked=true` and the MCP step returns `locked=false`
Then the evaluator produces a `fail` verdict with a structured diff of both responses

#### Scenario: LLM judgment is opt-in
Given a scenario step with `use_llm_judgment: false`
When the evaluator assesses an ambiguous response
Then it uses only programmatic checks and does not invoke `claude --print`

---

### Requirement: Budget Management

In `cli-augmented` mode, the framework MUST enforce a configurable **time budget** (wall-clock minutes, default: 60) since CLI usage is subscription-covered with zero marginal cost.

In `sdk-only` mode, the framework MUST enforce a configurable **USD budget cap** (default: $5) for per-token API calls.

Template execution and programmatic evaluation MUST NOT count against any budget (they are instant and free).

The framework MUST allocate scope progressively: changed features (tier 1, 40% of budget) → critical paths (tier 2, 35%) → full surface (tier 3, 25%). Percentages MUST be configurable.

The framework MUST terminate gracefully when budget (time or USD) is exhausted: complete the current scenario, skip remaining scenarios, and produce a partial report with a `budget_exhausted: true` flag and the list of unevaluated scenarios.

The framework MUST track and report: CLI calls made, wall-clock time consumed, and (in SDK mode) USD cost per generation/evaluation. When `AdaptiveBackend` is active, the report MUST separately attribute calls to CLI vs SDK backends.

#### Scenario: Time budget terminates run gracefully
Given `cli-augmented` mode with a 1-minute time budget and many pending scenarios
When the budget expires mid-run
Then the current scenario completes, remaining scenarios are skipped, and the report includes `budget_exhausted: true`

#### Scenario: USD budget cap enforced in sdk-only mode
Given `sdk-only` mode with a $5 budget cap that is reached
When the budget is exhausted
Then the run terminates gracefully with a partial report listing unevaluated scenarios

#### Scenario: Progressive scope allocation prioritizes changed features
Given a run with changed features, critical paths, and full surface to test
When budget is allocated
Then 40% goes to changed features before 35% to critical paths and 25% to full surface

#### Scenario: Report attributes CLI vs SDK calls separately
Given a run where `AdaptiveBackend` used both CLI and SDK backends
When the final report is produced
Then CLI call count and SDK call count are reported as separate entries

---

### Requirement: Feedback Loop

The evaluator's findings MUST be synthesized into structured `EvalFeedback` identifying: failing interfaces (list of endpoint/tool names), under-tested categories (categories with < 50% scenario coverage), near-miss scenarios (scenarios that passed but with > 500ms latency or partial assertion matches), and suggested focus areas.

The feedback MUST be formatted as a prompt-compatible text block consumable by the CLI/SDK generator to guide subsequent scenario generation. The first iteration MUST pass `feedback=None` to the generator.

The orchestrator MUST support multiple gen-eval iterations (configurable, default: 1) with feedback flowing from iteration N's evaluator to iteration N+1's generator.

#### Scenario: Feedback identifies under-tested categories
Given an evaluation run where the "auth" category has less than 50% scenario coverage
When `EvalFeedback` is synthesized
Then "auth" appears in the under-tested categories list

#### Scenario: First iteration receives no feedback
Given an orchestrator starting its first gen-eval iteration
When the generator is invoked
Then `feedback=None` is passed and the generator proceeds without prior findings

#### Scenario: Feedback flows between iterations
Given an orchestrator configured for 2 iterations
When iteration 1 completes with failing interfaces
Then iteration 2's generator receives those findings as a prompt-compatible feedback block

---

### Requirement: Orchestration

The orchestrator MUST manage the full lifecycle: service startup → health check (with configurable retry count and backoff) → seed data → generate → prioritize → evaluate → feedback → iterate → report → teardown. If health check fails after all retries, the run MUST abort with a clear error.

The orchestrator MUST support parallel scenario execution using `asyncio.Semaphore` with a configurable concurrency limit (default: 5).

The orchestrator MUST detect changed features by parsing `git diff --name-only <ref>` output and mapping changed source files to interface endpoints/tools using a configurable file-to-interface mapping in the descriptor.

The orchestrator MUST produce structured reports (markdown + JSON) with: per-interface verdict (pass/fail/error count), per-category summary, interface coverage percentage (= unique interfaces tested / total interfaces in descriptor × 100), cost/time summary, and list of unevaluated interfaces.

#### Scenario: Health check failure aborts run
Given a service that never becomes healthy within the configured retry count
When the orchestrator attempts to start the run
Then it aborts with a clear error message before any scenario is generated or executed

#### Scenario: Parallel execution respects concurrency limit
Given 20 scenarios queued for evaluation and `concurrency: 5`
When the orchestrator executes scenarios
Then at most 5 scenarios run concurrently at any point

#### Scenario: Changed features are detected from git diff
Given a descriptor with a file-to-interface mapping and a git diff showing changed source files
When the orchestrator detects changed features
Then only the mapped interface endpoints/tools are flagged as tier-1 scope

#### Scenario: Report includes interface coverage percentage
Given a completed evaluation run
When the structured report is produced
Then it includes interface coverage percentage, per-interface verdicts, and unevaluated interfaces

---

### Requirement: Integration

The framework MUST integrate with the existing `evaluation/metrics.py` for metrics collection (TokenUsage, timing, correctness).

The framework MUST be invocable as a CLI (`python -m evaluation.gen_eval`), as a skill (`/gen-eval`), and as a phase within `validate-feature`.

When a coordinator is available, the framework SHOULD use the work queue for distributed scenario execution and memory for cross-run finding storage. When unavailable, the framework MUST continue operating standalone without error.

The framework MUST add a CI job that runs `template-only` evaluation against docker-compose services, with a 10-minute timeout and fail-fast on 3 consecutive failures.

#### Scenario: CLI invocation runs evaluation
Given a configured interface descriptor
When `python -m evaluation.gen_eval` is invoked from the command line
Then the framework completes a full gen-eval run and exits with a non-zero code on failures

#### Scenario: Framework operates standalone without coordinator
Given no coordinator service running
When the framework executes a gen-eval run
Then it completes without error, operating in standalone mode

#### Scenario: CI job fails fast on consecutive failures
Given a CI job running `template-only` evaluation where 3 consecutive scenarios fail
When the fail-fast threshold is reached
Then the CI job aborts and reports failure without running remaining scenarios

---

### Requirement: Dogfood

The first interface descriptor MUST cover all 35 HTTP API endpoints, 39 MCP tools, and 31 CLI commands of the agent-coordinator.

Template scenarios MUST include both success and failure paths for at minimum: lock lifecycle, work queue operations, auth boundaries, cross-interface consistency, and multi-agent contention.

The dogfood descriptor MUST achieve 80%+ interface coverage (= unique interfaces exercised by at least one template scenario / total interfaces in descriptor × 100) with template scenarios alone.

#### Scenario: Dogfood descriptor covers full agent-coordinator surface
Given the agent-coordinator dogfood descriptor
When the framework loads it
Then it registers all 35 HTTP endpoints, 39 MCP tools, and 31 CLI commands

#### Scenario: Template scenarios include failure paths for core operations
Given the dogfood template scenario set
When it is inspected for coverage
Then lock lifecycle, work queue, auth boundaries, cross-interface consistency, and multi-agent contention each have at least one failure-path scenario

#### Scenario: Template-only run achieves 80% interface coverage
Given the dogfood descriptor and template scenarios only (no LLM generation)
When a `template-only` run completes
Then the interface coverage percentage is at least 80%

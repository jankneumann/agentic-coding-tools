# Spec: Generator-Evaluator Testing Framework

**Change ID**: `gen-eval-testing`
**Capability**: `gen-eval-framework`

## Requirements

### Interface Descriptor (REQ-DESC)

- **REQ-DESC-01**: The framework MUST accept an interface descriptor (YAML) that declaratively describes a project's testable surface including HTTP endpoints, MCP tools, CLI commands, and state verifiers.
- **REQ-DESC-02**: The descriptor MUST include service startup/teardown configuration (command, health check URL, teardown command).
- **REQ-DESC-03**: The framework MUST support auto-discovery of HTTP endpoints from OpenAPI specs, MCP tools from `tools/list`, and CLI commands from `--help` output.
- **REQ-DESC-04**: The descriptor format MUST be project-agnostic — no hardcoded references to agent-coordinator internals.

### Scenario Generation (REQ-GEN)

- **REQ-GEN-01**: The framework MUST support template-based scenario generation from YAML files with parameterization (Jinja2-style variable substitution and combinatorial expansion).
- **REQ-GEN-02**: The framework MUST support CLI-augmented scenario generation using subscription-covered CLI tools (`claude --print`, `codex`) that reads the interface descriptor and evaluator feedback to produce novel edge-case scenarios.
- **REQ-GEN-03**: Generated scenarios MUST be validated against a defined schema before execution.
- **REQ-GEN-04**: The framework MUST support three generation modes: `template-only` (no LLM), `cli-augmented` (subscription-covered CLI tools), `api-fallback` (per-token, explicit opt-in).
- **REQ-GEN-05**: The generator MUST accept focus areas (changed endpoints, categories) to produce targeted scenarios.
- **REQ-GEN-06**: The framework MUST default to CLI-based LLM execution (`claude --print`, `codex`) as the subscription-covered path.
- **REQ-GEN-07**: The framework MUST provide an `AdaptiveBackend` that detects CLI rate limiting (exit codes, stderr patterns, session/weekly caps) and transparently falls back to SDK-based execution (Anthropic SDK, OpenAI SDK) for remaining calls.
- **REQ-GEN-08**: SDK-based execution MUST be available as an explicit `sdk-only` mode for CI environments without CLI access, and as automatic fallback in `cli-augmented` mode when CLI is rate-limited.

### Scenario Model (REQ-SCN)

- **REQ-SCN-01**: A scenario MUST be an ordered sequence of action steps, each targeting a specific transport (http, mcp, cli, db, browser, wait).
- **REQ-SCN-02**: Each step MUST support an expect block for asserting response status, body content, row counts, and error messages.
- **REQ-SCN-03**: Steps MUST support variable capture (extract values from responses) and interpolation (inject captured values into subsequent steps).
- **REQ-SCN-04**: Scenarios MUST support cleanup steps that execute after the main steps regardless of pass/fail outcome.
- **REQ-SCN-05**: Scenarios MUST have category, priority, and interface tags for filtering and budget allocation.

### Transport Clients (REQ-CLI)

- **REQ-CLI-01**: The framework MUST provide pluggable transport clients for HTTP (httpx), MCP (fastmcp SDK), CLI (subprocess), and database (asyncpg).
- **REQ-CLI-02**: Each client MUST implement a common `TransportClient` protocol with `execute()`, `health_check()`, and `cleanup()` methods.
- **REQ-CLI-03**: The HTTP client MUST support auth injection (API key headers) configured via the interface descriptor.
- **REQ-CLI-04**: The CLI client MUST parse JSON output (when json_flag is configured) and check exit codes.
- **REQ-CLI-05**: The database client MUST be read-only (SELECT queries only) — it verifies state, never mutates.
- **REQ-CLI-06**: The framework MUST provide a stub browser client (Playwright) for future frontend project support.

### Evaluation (REQ-EVAL)

- **REQ-EVAL-01**: The evaluator MUST execute scenario steps sequentially through the appropriate transport client and compare actual responses against expected values.
- **REQ-EVAL-02**: The evaluator MUST produce a structured `ScenarioVerdict` with per-step pass/fail/error status, actual vs expected values, and failure summaries.
- **REQ-EVAL-03**: The evaluator MUST support cross-interface consistency verification — the same state checked across multiple transports within one scenario.
- **REQ-EVAL-04**: The evaluator MUST verify database state directly (not just API responses) when db steps are present in a scenario.
- **REQ-EVAL-05**: Evaluation MUST be independent and skeptical — the evaluator has no access to the generator's intent, only the scenario spec and live service responses.

### Budget Management (REQ-BDG)

- **REQ-BDG-01**: In `cli-augmented` mode, the framework MUST enforce a configurable **time budget** (wall-clock minutes) since CLI usage is subscription-covered with zero marginal cost.
- **REQ-BDG-02**: In `api-fallback` mode, the framework MUST enforce a configurable **USD budget cap** for per-token API calls.
- **REQ-BDG-03**: Template execution and programmatic evaluation MUST NOT count against any budget (they are instant and free).
- **REQ-BDG-04**: The framework MUST allocate scope progressively: changed features (tier 1) → critical paths (tier 2) → full surface (tier 3).
- **REQ-BDG-05**: The framework MUST terminate gracefully when budget (time or USD) is exhausted, producing a report on what was evaluated.
- **REQ-BDG-06**: The framework MUST track and report: CLI calls made, wall-clock time consumed, and (in API mode) USD cost per generation/evaluation.

### Feedback Loop (REQ-FBK)

- **REQ-FBK-01**: The evaluator's findings MUST be synthesized into structured feedback identifying failing interfaces, under-tested categories, and suggested focus areas.
- **REQ-FBK-02**: The feedback MUST be consumable by the LLM generator to guide subsequent scenario generation toward under-tested areas.
- **REQ-FBK-03**: The orchestrator MUST support multiple gen-eval iterations (configurable) with feedback flowing between each round.

### Orchestration (REQ-ORC)

- **REQ-ORC-01**: The orchestrator MUST manage the full lifecycle: service startup → health check → seed data → generate → prioritize → evaluate → feedback → iterate → report → teardown.
- **REQ-ORC-02**: The orchestrator MUST support parallel scenario execution with configurable concurrency limits.
- **REQ-ORC-03**: The orchestrator MUST detect changed features from git diff or OpenSpec change-context to prioritize evaluation.
- **REQ-ORC-04**: The orchestrator MUST produce structured reports (markdown + JSON) with per-interface/per-category verdicts, coverage metrics, and cost summary.

### Integration (REQ-INT)

- **REQ-INT-01**: The framework MUST integrate with the existing `evaluation/metrics.py` for metrics collection (TokenUsage, timing, correctness).
- **REQ-INT-02**: The framework MUST be invocable as a CLI (`python -m evaluation.gen_eval`), as a skill (`/gen-eval`), and as a phase within `validate-feature`.
- **REQ-INT-03**: When a coordinator is available, the framework SHOULD use the work queue for distributed scenario execution and memory for cross-run finding storage.
- **REQ-INT-04**: The framework MUST add a CI job that runs template-only evaluation against docker-compose services.

### Dogfood (REQ-DOG)

- **REQ-DOG-01**: The first interface descriptor MUST cover all 35 HTTP API endpoints, 39 MCP tools, and 31 CLI commands of the agent-coordinator.
- **REQ-DOG-02**: Template scenarios MUST cover at minimum: lock lifecycle, work queue operations, auth boundaries, cross-interface consistency, and multi-agent contention.
- **REQ-DOG-03**: The dogfood descriptor MUST achieve 80%+ interface coverage with template scenarios alone.

# gen-eval-framework Specification

## Purpose
TBD - created by archiving change gen-eval-testing. Update Purpose after archive.
## Requirements
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

### Requirement: Scenario Pack Manifest

The gen-eval framework SHALL support a machine-readable scenario-pack manifest that classifies scenarios by visibility, provenance, determinism, and ownership.

The manifest SHALL support at minimum:
- `visibility`: `public` or `holdout`
- `source`: `spec`, `contract`, `doc`, `incident`, `archive`, or `manual`
- `determinism`: `deterministic`, `bounded-nondeterministic`, or `exploratory`
- `owner`: responsible team or change-id
- `promotion_status`: `draft`, `candidate`, `approved`

#### Scenario: Manifest validates public vs holdout classification
Given a scenario-pack manifest containing both public and holdout entries
When the framework loads the manifest
Then each entry is validated against the allowed visibility enum

#### Scenario: Manifest preserves provenance metadata
Given a scenario-pack manifest entry derived from an incident
When the entry is loaded
Then the framework records `source=incident` and preserves the linked incident reference

#### Scenario: Invalid visibility is rejected
Given a manifest entry with `visibility=private`
When the manifest is validated
Then validation fails with a clear enum error

### Requirement: Visibility-Aware Scenario Execution

The framework SHALL support visibility-aware scenario filtering and reporting.

Implementation-visible workflows SHALL execute `public` scenarios only unless explicitly overridden for diagnostic use. Validation and cleanup gates SHALL support executing both `public` and `holdout` scenarios, with separate reporting for each visibility bucket.

#### Scenario: Implementation run excludes holdout scenarios
Given a manifest with public and holdout scenarios
When gen-eval runs in implementation context
Then only public scenarios are selected for execution

#### Scenario: Cleanup gate includes holdout scenarios
Given a validation context with holdout scenarios available
When cleanup validation runs
Then the holdout scenarios are executed and reported separately from public scenarios

#### Scenario: Report includes visibility coverage
Given a completed evaluation run
When the report is generated
Then it includes pass/fail counts and coverage percentages grouped by visibility

#### Scenario: Implementation context rejects explicit holdout request
Given an implementation-context run with an explicit request to include holdout scenarios
When gen-eval validates the request
Then it rejects the request with a clear error indicating holdout scenarios are not available in implementation context

### Requirement: DTU Scaffold From Public Docs

The framework SHALL support generating a DTU-lite scaffold from public SDK/API documentation, examples, auth guidance, and error-mode descriptions.

The scaffold SHALL produce:
- a descriptor seed
- fixture placeholders
- an unsupported-surface list
- a fidelity report

The fidelity report SHALL determine whether the resulting DTU is eligible for holdout-backed validation.

#### Scenario: DTU scaffold generated from public docs
Given public SDK/API docs and examples for an external system
When the DTU scaffold flow runs
Then it creates a descriptor seed, fixture structure, and unsupported-surface list

#### Scenario: Fidelity report marks low-confidence twin as non-holdout
Given a DTU scaffold with low conformance or large unsupported surface
When the fidelity report is generated
Then the report marks the DTU as not eligible for holdout promotion

#### Scenario: Fidelity report captures live probe results
Given a DTU scaffold that can be probed against a live system
When fidelity checks run
Then the report records the probe outcomes and resulting conformance score

### Requirement: Multi-Source Scenario Bootstrap

The framework SHALL support bootstrapping scenarios from OpenSpec spec deltas, contract artifacts, incidents, archived exemplars, and public docs in addition to hand-authored templates.

Bootstrapped scenarios SHALL preserve source metadata in the scenario-pack manifest so downstream users can distinguish normative scenarios from mined or inferred ones.

#### Scenario: Bootstrap from spec deltas
Given an OpenSpec change with requirement scenarios
When the bootstrap flow runs
Then it emits scenario seeds linked to the originating requirement refs

#### Scenario: Bootstrap from archived exemplar
Given a mined exemplar from an archived OpenSpec change
When scenario bootstrap runs
Then it emits a new draft scenario with `source=archive`

#### Scenario: Bootstrap from contract artifact
Given an OpenAPI or schema contract
When scenario bootstrap runs
Then it emits scenario seeds that reference the contract path in their metadata

#### Scenario: Bootstrap from empty spec delta produces no scenarios
Given a spec delta with no requirement scenarios defined
When the bootstrap flow runs
Then it produces zero scenario seeds and logs a warning indicating no source material

#### Scenario: Bootstrap from malformed source skips gracefully
Given a corrupt or unparseable archived artifact
When scenario bootstrap runs
Then the malformed source is skipped with a warning and remaining sources are processed normally

### Requirement: OpenSpec-Seeded Scenario Generation

The gen-eval framework SHALL accept an `--openspec-change <change-id>` flag in `cli-augmented` mode. When set, the framework MUST walk `openspec/changes/<change-id>/specs/**/*.md`, parse Requirement and Scenario blocks (WHEN/THEN/AND structure), and pass them as additional constraints to the scenario-generation prompt alongside the interface descriptor.

The framework MUST preserve the source location (file path + line number) of each parsed scenario so generated test scenarios can be traced back to the originating Requirement.

The framework MUST handle the absence of the change directory gracefully: log a warning and proceed with descriptor-only generation, rather than failing.

When invoked without the `--openspec-change` flag, the framework MUST behave identically to its prior behavior (no regression).

#### Scenario: OpenSpec scenarios augment cli-augmented prompt

- **GIVEN** an interface descriptor at `evaluation/gen_eval/descriptors/api.yaml`
- **AND** an OpenSpec change at `openspec/changes/example-feature/specs/example/spec.md` with two `### Requirement` blocks containing three total `#### Scenario` blocks in WHEN/THEN form
- **WHEN** the framework runs with `--mode cli-augmented --openspec-change example-feature`
- **THEN** the cli-augmented prompt sent to the configured CLI tool MUST contain a section titled exactly `# OpenSpec Scenarios (constraints)`
- **AND** within that section, exactly three scenario blocks MUST appear, each preceded by a line of the form `## <requirement-name> :: <scenario-name> [<file>:<line-start>-<line-end>]`
- **AND** the prompt MUST be capturable for assertion (gen-eval emits the resolved prompt to a debug-output file when invoked with `--debug-prompt-path <path>`)
- **AND** the generated `Scenario` Pydantic objects MUST include a `source.openspec_scenario` field populated with the exact `<file>:<line-start>-<line-end>` reference for the scenario that produced them

#### Scenario: change-id input rejected if it contains path separators or shell metacharacters

- **GIVEN** any interface descriptor exists
- **WHEN** the framework runs with `--openspec-change "../../../etc"` (or any value matching `[^a-zA-Z0-9_-]`)
- **THEN** the framework MUST exit with a non-zero status code
- **AND** the framework MUST log an error naming the regex constraint (`change-id MUST match ^[a-zA-Z0-9_-]+$`)
- **AND** the framework MUST NOT walk any directory or read any file based on the rejected input

#### Scenario: scenario WHEN/THEN text is escaped before injection into cli-augmented prompt

- **GIVEN** an OpenSpec scenario whose WHEN clause contains literal triple-backticks, the string `### Requirement:`, or other prompt-structure markers
- **WHEN** the framework builds the cli-augmented prompt for that scenario
- **THEN** the scenario's text MUST be wrapped inside fenced code blocks or another delimiter that prevents the embedded markers from changing prompt structure
- **AND** the prompt's overall section structure MUST remain unchanged (e.g., `# OpenSpec Scenarios (constraints)` heading still present and at the same nesting level)

#### Scenario: Missing OpenSpec change degrades to descriptor-only

- **GIVEN** an interface descriptor exists
- **AND** no directory at `openspec/changes/<id>/`
- **WHEN** the framework runs with `--mode cli-augmented --openspec-change <id>`
- **THEN** the framework MUST log a warning naming the missing path
- **AND** the framework MUST continue with descriptor-only scenario generation
- **AND** the framework MUST exit with the same status code as a descriptor-only run

#### Scenario: Backward compatibility without flag

- **GIVEN** any interface descriptor
- **WHEN** the framework runs with `--mode cli-augmented` and no `--openspec-change` flag
- **THEN** the framework MUST behave identically to the pre-change cli-augmented mode
- **AND** the generated prompt MUST NOT include any OpenSpec content
- **AND** generated `Scenario` objects MUST NOT include the `source.openspec_scenario` field

---

### Requirement: Behavioral Findings Schema Conformance

Any behavioral validator (gen-eval invoked from `agent-coordinator/evaluation/gen_eval/__main__.py`, OR the Playwright validator implemented as the peer skill `skills/playwright-validator/`) SHALL emit findings to a per-vendor file conforming to the `review-findings.schema.json` schema defined at `openspec/schemas/review-findings.schema.json`.

Filename routing follows D2 (peer-skill packaging): when emitted by `agent-coordinator/evaluation/gen_eval/__main__.py` the file MUST be named `findings-gen-eval.json`; when emitted by `skills/playwright-validator/` the file MUST be named `findings-playwright.json`. The two filenames are mutually exclusive — a single change MUST NOT have both validators write under the same filename.

Each finding emitted by either validator MUST use `type: behavioral_failure` and MUST populate the schema's required `severity`, `description`, and `location` fields.

When the failing scenario originated from an OpenSpec scenario (per the OpenSpec-Seeded Scenario Generation requirement), the finding's `location` MUST reference the OpenSpec scenario's `file:line-range`, not the gen-eval scenario YAML or the generated Playwright `.spec.ts` file. This applies uniformly to gen-eval and Playwright outputs.

#### Scenario: Findings file produced and schema-valid

- **GIVEN** the framework runs with `--report-format json` and produces 2 failing scenarios and 5 passing scenarios
- **WHEN** the run completes
- **THEN** a file `findings-gen-eval.json` MUST exist in the `--output-dir`
- **AND** running `python -c "import json,jsonschema; jsonschema.validate(json.load(open('<file>')), json.load(open('openspec/schemas/review-findings.schema.json')))"` MUST exit zero
- **AND** the file MUST contain exactly 2 finding entries (one per failing scenario), all with `type: behavioral_failure`

#### Scenario: Concurrent gen-eval and Playwright validators write to distinct filenames

- **GIVEN** an OpenSpec change has both an HTTP/MCP/CLI descriptor AND a frontend descriptor
- **AND** `validate-feature --phase gen-eval` runs both validators against the same change
- **WHEN** both validators complete
- **THEN** `findings-gen-eval.json` (from gen-eval) MUST exist in the change directory
- **AND** `findings-playwright.json` (from Playwright) MUST exist in the change directory
- **AND** neither file MUST contain findings produced by the other validator
- **AND** `consensus_synthesizer.py` MUST merge both files as separate vendor sources and emit one `consensus.json`

#### Scenario: Playwright findings trace to OpenSpec scenarios

- **GIVEN** the Playwright validator runs against a frontend descriptor and an OpenSpec change with WHEN/THEN scenarios at `openspec/changes/foo/specs/ui/spec.md` lines 30-45
- **AND** one Playwright assertion fails for the scenario at lines 38-44
- **WHEN** the Playwright validator emits `findings-playwright.json`
- **THEN** the failing finding's `location.file` MUST be `openspec/changes/foo/specs/ui/spec.md`
- **AND** the failing finding's `location.line_start` MUST be 38 and `line_end` MUST be 44
- **AND** the finding's `metadata.scenario_id` MUST reference the originating scenario name (not the generated `.spec.ts` test name)

#### Scenario: OpenSpec-sourced finding points back to spec

- **GIVEN** a failing scenario whose `source.openspec_scenario` is `openspec/changes/foo/specs/api/spec.md:42-50`
- **WHEN** the framework emits the corresponding finding to `findings-gen-eval.json`
- **THEN** the finding's `location.file` MUST be `openspec/changes/foo/specs/api/spec.md`
- **AND** the finding's `location.line_start` MUST be 42 and `line_end` MUST be 50

---

### Requirement: Browser-Driving Behavioral Validation via Playwright CLI

The gen-eval framework SHALL support a `playwright` validator pipeline that drives a deployed frontend via the Playwright CLI (`npx playwright test --reporter=json`). The pipeline MAY be packaged either as a new gen-eval mode (`--mode playwright`) or as a peer skill (`skills/playwright-validator/`); the design.md decision will resolve this. Either packaging MUST satisfy the requirements below.

The pipeline MUST accept a frontend descriptor YAML conforming to a frontend descriptor schema (`contracts/frontend-descriptor.schema.json` introduced by this change), covering: base URL, auth flow steps, selector aliases, and a browser matrix (any subset of `chromium`, `firefox`, `webkit`).

The pipeline MUST generate Playwright test scripts from OpenSpec scenarios (per the OpenSpec-Seeded Scenario Generation requirement) plus the frontend descriptor's selector aliases, then execute the generated scripts via the Playwright CLI.

The pipeline MUST emit findings conforming to the Behavioral Findings Schema Conformance requirement, with one finding per failing Playwright assertion. The finding's `location` MUST reference the originating OpenSpec scenario when one exists.

The pipeline MUST exit non-zero if any Playwright test fails, but the calling skill MAY treat the failure as non-blocking (consistent with the existing template-only gen-eval phase's non-critical posture).

The pipeline MUST handle partial failures gracefully: when test-script generation fails for a subset of scenarios (malformed WHEN/THEN), browser-binary launch fails for a subset of browsers, or `npx playwright test` fails for a subset of generated tests, the pipeline MUST emit findings for the cases that DID run AND log warnings naming the failed cases AND exit zero only when zero scenarios produced findings (full-pipeline failure). Partial-failure scenarios surface as `severity: high` behavioral_failure findings with `description` naming the failure mode (`script_generation_failed`, `browser_launch_failed`, `test_execution_failed`).

The pipeline's local HTTP server (started for sample/test descriptors via `lifecycle.startup_command`) MUST bind to `127.0.0.1` rather than `0.0.0.0`. The frontend-descriptor schema enforces this default but does not override an explicit operator-supplied `--bind` flag; operators are responsible for any deliberate non-localhost binding.

The pipeline MUST NOT execute env-var-substituted `auth_flow.value` strings via shell expansion. Substitution MUST be performed using string-template replacement (Python's `string.Template.substitute` or equivalent), and missing env vars MUST cause the pipeline to fail fast with a clear error naming the missing variable rather than expanding to an empty string.

#### Scenario: Sample frontend exercise validates the full path

- **GIVEN** the sample frontend at `evaluation/gen_eval/fixtures/sample-frontend/index.html`
- **AND** the sample frontend descriptor at `evaluation/gen_eval/descriptors/sample-frontend.yaml`
- **AND** an OpenSpec change with at least one `#### Scenario` block describing a click-and-assert flow
- **WHEN** the Playwright pipeline runs with `--mode playwright --openspec-change <id>` (or the skill-equivalent invocation `/playwright-validator <id>`)
- **THEN** the pipeline MUST start a local HTTP server bound to `127.0.0.1` only (per design D7 — verifiable by `ss -tlnp` showing the listening socket on 127.0.0.1, not 0.0.0.0)
- **AND** the pipeline MUST generate a Playwright TypeScript test file under `skills/playwright-validator/test-results/generated/` that passes `npx playwright test --dry-run` (i.e., the script is syntactically valid Playwright TypeScript)
- **AND** the generated test MUST reference each OpenSpec WHEN step as a Playwright action (`page.click`, `page.fill`, `page.goto`, `page.waitForSelector`) and each OpenSpec THEN step as a Playwright assertion (`expect(...).toBeVisible()`, `expect(...).toHaveText(...)`, etc.)
- **AND** the generated test's selector arguments MUST resolve through the descriptor's `selectors` map (each selector alias MUST be expanded to the literal Playwright selector before script emission)
- **AND** the pipeline MUST execute `npx playwright test --reporter=json` against the generated script
- **AND** the pipeline MUST emit `findings-playwright.json` (per the Behavioral Findings Schema Conformance requirement) conforming to `review-findings.schema.json`

#### Scenario: Auth flow with missing env var fails fast

- **GIVEN** a frontend descriptor whose `auth_flow[].value` references `${MISSING_VAR}`
- **AND** the environment does not define `MISSING_VAR`
- **WHEN** the Playwright pipeline runs
- **THEN** the pipeline MUST exit with a non-zero status before starting any browser
- **AND** the pipeline MUST log "auth_flow: required env var MISSING_VAR not set" with that exact env var name
- **AND** the pipeline MUST NOT pass the literal string `${MISSING_VAR}` to any Playwright action

#### Scenario: Concurrent gen-eval and Playwright on same change

- **GIVEN** a change with both an HTTP descriptor (`evaluation/gen_eval/descriptors/api.yaml`) and a frontend descriptor (`evaluation/gen_eval/descriptors/sample-frontend.yaml`)
- **WHEN** `validate-feature --phase gen-eval <change-id>` runs
- **THEN** the phase MUST dispatch both gen-eval (for the HTTP descriptor) and the Playwright validator (for the frontend descriptor)
- **AND** the resulting findings files MUST be `findings-gen-eval.json` and `findings-playwright.json` — distinct files, no overwrite
- **AND** both files MUST validate against `openspec/schemas/review-findings.schema.json`
- **AND** the consensus synthesizer MUST treat both as separate vendor sources (per `contracts/findings-vendor-source.md`)

#### Scenario: Playwright dispatcher auto-detection in validate-feature

- **GIVEN** a change with a frontend descriptor at `evaluation/gen_eval/descriptors/*.yaml` that conforms to `frontend-descriptor.schema.json`
- **WHEN** `validate-feature --phase gen-eval <change-id>` runs
- **THEN** the phase handler MUST detect the descriptor as a frontend descriptor (by attempting to validate it against `frontend-descriptor.schema.json` rather than the HTTP/MCP descriptor schema)
- **AND** the handler MUST invoke the Playwright validator skill (e.g., `/playwright-validator <change-id>`) for that descriptor
- **AND** non-frontend descriptors in the same directory MUST still be dispatched to the HTTP/MCP gen-eval path (no regression)

#### Scenario: Playwright pipeline partial failure recovery

- **GIVEN** a Playwright run with 5 generated tests across 2 browsers (10 total executions)
- **AND** 3 of those executions fail (e.g., 2 in chromium, 1 in firefox), 7 pass
- **WHEN** the run completes
- **THEN** the pipeline MUST emit `findings-playwright.json` containing exactly 3 finding entries (one per failed execution)
- **AND** each finding MUST include `metadata.browser` identifying which browser produced it
- **AND** the pipeline MUST exit with a non-zero status code (test failures are not pipeline failures, but the calling skill needs to know tests failed)
- **AND** the pipeline MUST NOT abort early — all 10 executions must complete before the report is emitted

#### Scenario: Browser matrix executes all configured browsers

- **GIVEN** a frontend descriptor with `browsers: [chromium, firefox]`
- **WHEN** the Playwright pipeline runs
- **THEN** the pipeline MUST execute the test script in both Chromium and Firefox
- **AND** findings from both browsers MUST appear in the emitted findings file
- **AND** each finding MUST include a `metadata.browser` field identifying which browser produced it

#### Scenario: Missing Playwright CLI degrades cleanly

- **GIVEN** a project where `npx playwright` is not available on PATH (or playwright is not installed)
- **WHEN** the Playwright pipeline is invoked
- **THEN** the pipeline MUST log a clear error naming the missing dependency and the install command (`npx playwright install`)
- **AND** the pipeline MUST exit with a non-zero status code distinguishable from a test failure (e.g., 127 for missing dependency)
- **AND** the pipeline MUST NOT emit a findings file


# gen-eval-framework Specification

## Purpose
TBD - created by archiving change gen-eval-testing. Update Purpose after archive.
## Requirements
### Requirement: Interface Descriptor

The framework MUST accept an interface descriptor (YAML) that declaratively
describes a project's testable surface including HTTP endpoints, MCP tools, CLI
commands, and state verifiers.

Service lifecycle configuration (startup command, health check, teardown
command, health check timeout, retry count) MUST be optional. A descriptor for
a project with nothing to start MUST be loadable without it, and the
orchestrator MUST skip startup, health check, seeding, and teardown when it is
absent.

The framework MUST derive a descriptor's declared surface from a contract —
an OpenAPI document for service descriptors, a CLI contract for tool
descriptors. The framework MUST NOT populate a declared surface by
introspecting a running implementation; implementation introspection is
reserved for subset verification.

The descriptor format MUST be project-agnostic — no hardcoded references to
agent-coordinator internals.

#### Scenario: Descriptor validates project surface

- **WHEN** the framework loads a YAML interface descriptor for a project
- **THEN** it SHALL correctly identify HTTP endpoints, MCP tools, CLI commands,
  and state verifiers

#### Scenario: Descriptor supports optional service lifecycle config

- **WHEN** a descriptor declares startup command, health check, and teardown
- **THEN** the orchestrator SHALL use those settings including retry count and
  timeout

#### Scenario: Descriptor without lifecycle config loads and runs

- **WHEN** a descriptor omits service lifecycle configuration
- **THEN** the framework SHALL load it without error
- **AND** the orchestrator SHALL skip startup, health check, seeding, and
  teardown

#### Scenario: Declared surface comes from the contract

- **WHEN** a descriptor references an OpenAPI or CLI contract
- **THEN** the declared surface SHALL be derived from that contract
- **AND** a running implementation SHALL NOT be consulted to enumerate it

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

The agent-coordinator dogfood descriptor MUST cover the coordinator's full
declared surface across its HTTP, MCP, and CLI bindings: at minimum 38 HTTP
endpoints, 39 MCP tools, and 37 CLI commands.

Template scenarios MUST include both success and failure paths for at minimum:
lock lifecycle, work queue operations, auth boundaries, cross-interface
consistency, and multi-agent contention.

A **service** dogfood descriptor whose declared surface is non-empty MUST
achieve 80%+ interface coverage (unique interfaces exercised by at least one
template scenario / total declared interfaces × 100) with template scenarios
alone.

A **tool** dogfood descriptor MUST instead satisfy a completeness rule: every
contracted coverage unit MUST be either exercised by at least one scenario or
declared as an explicit exclusion carrying a stated reason. A coverage unit that
is neither exercised nor excluded MUST fail the gate.

A descriptor whose declared surface is empty MUST fail rather than report
coverage, since a vacuous coverage figure is indistinguishable from full
coverage.

gen-eval MUST maintain a tool descriptor for its own CLI surface, derived from
a CLI contract, and MUST evaluate it as a blocking gate.

#### Scenario: Dogfood descriptor covers the full agent-coordinator surface

- **WHEN** the framework loads the agent-coordinator dogfood descriptor
- **THEN** it SHALL register every HTTP endpoint, MCP tool, and CLI command the
  descriptor declares
- **AND** the registered counts SHALL be at least 38 HTTP endpoints, 39 MCP
  tools, and 37 CLI commands

#### Scenario: Template scenarios include failure paths for core operations

- **WHEN** the dogfood template scenario set is inspected for coverage
- **THEN** lock lifecycle, work queue, auth boundaries, cross-interface
  consistency, and multi-agent contention SHALL each have at least one
  failure-path scenario

#### Scenario: Template-only run achieves 80% interface coverage

- **WHEN** a `template-only` run completes against a **service** dogfood
  descriptor with a non-empty declared surface
- **THEN** the interface coverage percentage SHALL be at least 80%

#### Scenario: An unexercised, unexcluded tool coverage unit fails the gate

- **WHEN** a tool dogfood descriptor declares a coverage unit that no scenario
  exercises and that carries no exclusion entry
- **THEN** the gate SHALL fail naming that unit
- **AND** a percentage above any threshold SHALL NOT satisfy the gate in its place

#### Scenario: An excluded coverage unit states why

- **WHEN** a contracted coverage unit is declared as an exclusion
- **THEN** the exclusion SHALL carry a stated reason
- **AND** an exclusion without a reason SHALL fail the gate

#### Scenario: An empty declared surface fails rather than reporting coverage

- **WHEN** a dogfood run completes against a descriptor declaring zero
  interfaces
- **THEN** the run SHALL fail
- **AND** it SHALL NOT report a coverage percentage implying full coverage

#### Scenario: gen-eval evaluates its own CLI surface

- **WHEN** gen-eval's own tool descriptor is evaluated
- **THEN** its declared surface SHALL be non-empty
- **AND** the evaluation SHALL gate CI

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

### Requirement: Contract As Descriptor Source Of Truth

Descriptors SHALL be derived from a machine-readable contract, and runtime
introspection of a running implementation SHALL NOT be used to populate a
descriptor's declared surface.

The contract SHALL live under `openspec/contracts/<capability>/` — `openapi/`
for service contracts, `cli/` for tool contracts — which is the canonical
location that survives change archival.

Runtime introspection SHALL be used only to verify that an implemented surface
is a subset of its contract, per the Implemented Surface Subset Verification
requirement.

#### Scenario: Descriptor derives from a contract

- **WHEN** a descriptor declares a contract reference
- **THEN** the framework SHALL populate the declared surface from that contract
- **AND** it SHALL NOT invoke the implementation to enumerate that surface

#### Scenario: Unreachable implementation does not shrink the declared surface

- **WHEN** a descriptor is loaded and the implementation it describes is broken,
  absent, or unreachable
- **THEN** the declared surface SHALL be unchanged from the contract
- **AND** coverage SHALL be computed against that unchanged declared surface

### Requirement: Service And Tool Descriptor Archetypes

The framework SHALL distinguish a service descriptor from a tool descriptor,
and SHALL apply the coverage and lifecycle semantics appropriate to each.

A service descriptor describes a system whose surface is projected across HTTP
and MCP bindings from one operation set; its contract is OpenAPI and its
coverage unit is the operation.

A tool descriptor describes a program's own invocation surface; its contract is
a CLI contract and its coverage unit is the command or flag. A tool descriptor
SHALL NOT require service lifecycle configuration.

Both archetypes SHALL be loadable alongside the existing hand-authored
descriptor format, which remains supported and is deprecated.

#### Scenario: Tool descriptor requires no lifecycle configuration

- **WHEN** a tool descriptor is loaded
- **THEN** the framework SHALL NOT require startup, health-check, or teardown
  configuration
- **AND** the orchestrator SHALL skip startup, health check, seeding, and
  teardown

#### Scenario: Hand-authored descriptor still loads

- **WHEN** a descriptor declares no contract reference
- **THEN** the framework SHALL load it using the existing hand-authored format
- **AND** it SHALL emit a deprecation warning naming the contract-derived
  replacement

### Requirement: Descriptor Derivation Drift Guard

Derived descriptors SHALL be generated as checked-in artifacts, and a
`--check` mode SHALL exit non-zero when a checked-in artifact differs from
what the generator produces from the current contract.

The guard SHALL fail when the generated artifact declares zero coverage units.

The guard SHALL fail when the generated artifact's coverage-unit count differs
from the contract's coverage-unit count.

The coverage unit SHALL be the operation for a service descriptor, and the flag,
positional argument, or named subcommand for a tool descriptor. The guard SHALL
NOT count commands as coverage units for a tool descriptor.

#### Scenario: Drift between contract and checked-in descriptor fails

- **WHEN** a contract is changed and the derived descriptor is not regenerated
- **THEN** `--check` SHALL exit non-zero
- **AND** it SHALL report which artifact drifted

#### Scenario: An empty derived descriptor fails rather than passing trivially

- **WHEN** derivation produces a descriptor declaring zero operations
- **THEN** the guard SHALL fail on the non-emptiness assertion
- **AND** it SHALL NOT report success on the grounds that the checked-in copy
  is also empty

#### Scenario: Operation count mismatch fails

- **WHEN** a derived descriptor declares a different number of operations than
  its contract
- **THEN** the guard SHALL fail
- **AND** it SHALL report both counts

#### Scenario: A tool contract declaring commands but no coverage units fails

- **WHEN** a tool contract declares one or more commands and zero flags,
  positionals, and named subcommands
- **THEN** the guard SHALL fail on the non-emptiness assertion
- **AND** it SHALL NOT report success on the grounds that the command count is
  non-zero and matches

### Requirement: Implemented Surface Subset Verification

The framework SHALL verify that an implementation exposes no surface absent
from its contract, for HTTP, MCP, and CLI surfaces.

HTTP surfaces SHALL be introspected from the application's generated OpenAPI
document, MCP surfaces from the server's tool listing, and CLI surfaces from
the argument parser's declared actions.

A surface element present in the implementation but absent from the contract
SHALL be reported as a contract violation.

#### Scenario: Undocumented endpoint is reported

- **WHEN** an implementation exposes an HTTP route absent from its contract
- **THEN** verification SHALL report a contract violation naming that route

#### Scenario: Undocumented CLI flag is reported

- **WHEN** an argument parser declares a flag absent from the tool contract
- **THEN** verification SHALL report a contract violation naming that flag

#### Scenario: Verification distinguishes excess from omission

- **WHEN** verification runs against a conformant implementation
- **THEN** it SHALL report no violation
- **AND** an implementation missing a contracted element SHALL be reported by
  coverage rather than by subset verification

### Requirement: Operation And Surface Coverage Model

Coverage SHALL be keyed on the operation, with per-surface exposure and
per-surface coverage recorded separately.

A surface that does not expose a given operation SHALL be recorded as not
exposed, and SHALL NOT count as an uncovered surface for that operation.

An operation SHALL be reported as unevaluated when no surface that exposes it
was exercised by any scenario.

Each exposed surface entry SHALL name the surface-local element that serves the
operation, and one element MAY serve more than one operation. Exercising a bound
element SHALL count as coverage of every operation bound to it.

The binding SHALL be expressible in the contract itself: a service contract
SHALL declare it on the operation, and a tool contract SHALL declare it on the
command. A binding that exists only in derived output and cannot be authored in
a contract SHALL NOT satisfy this requirement.

The identifiers recorded as tested SHALL be drawn from the same vocabulary as
the declared surface, so that a tested element matches its declared counterpart.

The framework SHALL provide a coverage threshold that fails a run when interface
coverage falls below it, separately from the pass-rate threshold.

The report SHALL continue to emit the flat interface list and the per-interface
coverage map for backward compatibility during the deprecation window, both
computed from the operation model.

#### Scenario: One operation tested via one surface is not three gaps

- **WHEN** an operation exposed on HTTP, MCP, and CLI is exercised via HTTP only
- **THEN** the operation SHALL be reported as covered
- **AND** the report SHALL record MCP and CLI as exposed but not covered

#### Scenario: A surface that does not expose an operation is not a gap

- **WHEN** an operation is exposed on HTTP but not on CLI
- **THEN** the CLI surface SHALL be recorded as not exposed for that operation
- **AND** it SHALL NOT contribute to the unevaluated set

#### Scenario: Flag-only tool surfaces are nameable

- **WHEN** a tool descriptor is derived from a CLI contract for a program with
  no subcommands
- **THEN** each contracted flag SHALL be a nameable coverage unit
- **AND** the declared surface SHALL be non-empty

#### Scenario: The many-to-one binding is authorable in a contract

- **WHEN** two operations in a service contract declare the same surface element
- **THEN** the contract SHALL validate
- **AND** derivation SHALL emit that element once rather than one element per
  operation

#### Scenario: One surface element serving two operations is covered once

- **WHEN** two operations bind to the same MCP tool and a scenario exercises
  that tool
- **THEN** both operations SHALL be reported as covered on the MCP surface
- **AND** subset verification SHALL NOT report that tool as undocumented
- **AND** it SHALL NOT report the two operations as omitted tools

#### Scenario: A flag exercised by a scenario is recorded as covered

- **WHEN** a scenario step invokes a tool with a contracted flag among its
  arguments
- **THEN** that flag SHALL appear in the tested identifier set
- **AND** it SHALL match the declared coverage unit of the same name

#### Scenario: Coverage below the threshold fails the run

- **WHEN** a run completes with interface coverage below the configured
  coverage threshold
- **THEN** the framework SHALL exit non-zero
- **AND** it SHALL do so independently of whether the pass-rate threshold was met

### Requirement: Descriptor Reclamation Is Announced

A previously-aliased type name assigned to a different type SHALL resolve, at
package level, to the new type, and SHALL be recorded in a downstream notice
naming both the previous and the new meaning.

Reclaiming a Python export name SHALL NOT, on that account alone, increment the
descriptor contract version. The published JSON Schema contract is unchanged by
which Python object a name binds to — the version tracks the schema, not the
package's export table. Incrementing it for a reclamation would signal a schema
change to every downstream consumer that validates against it, with nothing for
them to react to; the downstream notice is what carries a rename that only
affects importers.

A reclaimed name SHALL NOT be left resolving to the superseded type at package
level while resolving to the new type within its defining module.

#### Scenario: A reclaimed name is announced rather than silently rebound

- **WHEN** a descriptor archetype takes a name that previously denoted an
  element or container type
- **THEN** a downstream notice SHALL name both the previous and the new meaning
- **AND** the descriptor contract version SHALL NOT be incremented on that
  account alone

#### Scenario: Package-level export resolves to the reclaimed type

- **WHEN** a caller imports a reclaimed name from the package root
- **THEN** it SHALL receive the new archetype
- **AND** it SHALL NOT receive the superseded element or container type


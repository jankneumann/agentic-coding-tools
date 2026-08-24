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

### Requirement: Contracted operations cite the requirements they serve

A contracted operation SHALL cite one or more requirement identifiers naming
the requirements it exists to serve, or SHALL carry an exclusion with a stated
reason. Citations SHALL be written into the contract by its author and SHALL
NOT be inferred from operation names, paths, or prose similarity.

Inference has one failure mode and it is fatal: a plausible-looking match makes
the gate report green on a mapping nobody agreed with, which is worse than no
gate. The citation is a claim a human makes at the moment they design the
operation. An empty citation list is not permitted — it is an exclusion written
without a reason, spelled differently.

<!-- Scenario ID: gen-eval-framework.citation-is-declared -->
#### Scenario: An operation declares its citations

- **WHEN** a contract declares an operation with a `traceability` block naming
  one or more requirement identifiers
- **THEN** the framework SHALL record those identifiers against that operation
- **AND** it SHALL NOT add, remove, or reorder identifiers based on the
  operation's name or path

<!-- Scenario ID: gen-eval-framework.citation-resolves -->
#### Scenario: A citation names a requirement that exists

- **WHEN** an operation cites a requirement identifier
- **THEN** the identifier SHALL resolve to a requirement in the referenced
  capability's spec
- **AND** an identifier resolving to no requirement SHALL fail the gate
- **AND** the failure SHALL name the unresolved identifier and the nearest
  candidate requirement headings in that capability, bounded to at most five,
  ranked for display only — ranking SHALL NOT rebind the citation

### Requirement: Requirement identifiers are stable and fail closed

The framework SHALL derive a requirement identifier from its capability and the
slug of its heading, using one normative algorithm: Unicode-normalize (NFKD)
and drop non-ASCII marks, lowercase, replace each run of characters outside
`[a-z0-9]` with a single `-`, and strip leading and trailing `-`. Reworded
headings SHALL break citations to them rather than silently rebinding to the
nearest match. Two requirements in one capability deriving the same identifier
SHALL fail the resolver.

A broken citation is an accurate signal that the requirement changed. Fuzzy
re-matching would silently rebind the citation to whatever heading now looks
closest, which is the inference this capability forbids, reintroduced through
the back door. An undetected slug collision is worse: a citation to either
heading marks both requirements cited, and one requirement becomes permanently
invisible to reverse completeness with no signal at all.

<!-- Scenario ID: gen-eval-framework.identifier-derivation -->
#### Scenario: An identifier is derived from the heading

- **WHEN** the resolver reads a capability's spec
- **THEN** each requirement SHALL be addressable as
  `<capability>.<slug-of-heading>` under the normative slug algorithm
- **AND** every derived identifier SHALL match the citation pattern declared in
  `traceability.schema.json`
- **AND** the derived identifiers SHALL be stable across runs for unchanged
  headings

<!-- Scenario ID: gen-eval-framework.reworded-heading-fails-closed -->
#### Scenario: A reworded heading breaks its citations

- **WHEN** a requirement's heading is reworded and a citation still names the
  previous identifier
- **THEN** the gate SHALL fail
- **AND** it SHALL NOT rebind the citation to the reworded requirement

<!-- Scenario ID: gen-eval-framework.colliding-identifiers-fail -->
#### Scenario: Two headings deriving the same identifier fail the resolver

- **WHEN** two requirement headings in one capability derive the same
  identifier
- **THEN** the resolver SHALL fail naming both headings
- **AND** it SHALL NOT resolve citations to that identifier against either
  requirement

### Requirement: Traceability completeness is enforced in both directions

The framework SHALL fail when a contracted operation cites no requirement and
carries no exclusion, and SHALL fail when a requirement subject to reverse
enforcement is cited by no operation and carries no exclusion.

The reverse direction is the one nothing else detects. The coverage model
measures the declared surface against scenarios and cannot see a requirement
that never became an operation; the drift guards compare artifacts to contracts.
A requirement nobody built has no diff, so review does not reliably catch it
either.

<!-- Scenario ID: gen-eval-framework.forward-completeness -->
#### Scenario: An uncited operation fails the gate

- **WHEN** a traced contract declares ten operations of which nine cite a
  requirement and one cites nothing and carries no exclusion
- **THEN** the gate SHALL fail naming the uncited operation
- **AND** the gate SHALL NOT pass on the basis of the proportion of operations
  traced

<!-- Scenario ID: gen-eval-framework.reverse-completeness -->
#### Scenario: An uncited requirement fails the gate

- **WHEN** a requirement in a capability with reverse enforcement is cited by
  no operation and carries no exclusion
- **THEN** the gate SHALL fail naming that requirement

<!-- Scenario ID: gen-eval-framework.every-failure-is-named -->
#### Scenario: Every failure is reported in one run

- **WHEN** a run finds at least two uncited operations and at least two uncited
  requirements
- **THEN** the gate SHALL report all of them in a single run
- **AND** the number of findings reported SHALL equal the number of violations
- **AND** it SHALL NOT stop at the first

### Requirement: Traceability exclusions state a reason

An exclusion SHALL carry a non-blank reason. Operation exclusions SHALL be
written in the contract on the operation they exclude; requirement exclusions
SHALL be written in the capability's
`openspec/contracts/<capability>/traceability-exclusions.yaml`. An exclusion
naming an operation or requirement that no longer exists SHALL fail the gate.
An exclusions file SHALL only exclude requirements of its own capability; an
entry naming a requirement whose capability prefix is not the owning capability
SHALL fail the gate naming both capabilities.

Cross-capability *citations* are permitted (a citation adds a claim, and D9
reports them as a distinct list), but a cross-capability *exclusion* is
refused, because the two are not symmetric. A citation says "this operation
serves that requirement" — information the cited capability can audit. An
exclusion says "that requirement needs no operation at all", which discharges
an obligation the other capability owns and can neither see nor contest. That
is the laundering path D4 exists to close, arriving from outside.

An unexplained exclusion is how a gap gets laundered into "intentional". A
requirement with no operation has no operation to carry its exclusion, so the
reverse direction needs its own artifact — the same shape
`check_coverage_completeness.py` established for coverage units. A stale
exclusion is worse here than for coverage units, because requirements outlive
operations: an exclusion for a deleted requirement keeps a slot warm for the
next requirement to reuse the slug, which inherits an approval nobody granted
it.

<!-- Scenario ID: gen-eval-framework.blank-reason-fails -->
#### Scenario: A blank reason fails the gate

- **WHEN** an exclusion carries an empty or whitespace-only reason
- **THEN** the gate SHALL fail naming that exclusion

<!-- Scenario ID: gen-eval-framework.stale-exclusion-fails -->
#### Scenario: A stale exclusion fails the gate

- **WHEN** an exclusion names a requirement identifier or operation that no
  longer exists
- **THEN** the gate SHALL fail naming that exclusion

<!-- Scenario ID: gen-eval-framework.valid-operation-exclusion-suppresses -->
#### Scenario: An excluded operation does not fail forward completeness

- **WHEN** an operation carries an exclusion with a non-blank reason and cites
  no requirement
- **THEN** forward completeness SHALL NOT fail on that operation
- **AND** the exclusion and its reason SHALL appear in the gate's output

<!-- Scenario ID: gen-eval-framework.valid-requirement-exclusion-suppresses -->
#### Scenario: An excluded requirement does not fail reverse completeness

- **WHEN** a requirement is cited by no operation and the capability's
  exclusions file excludes it with a non-blank reason
- **THEN** reverse completeness SHALL NOT fail on that requirement
- **AND** the exclusion and its reason SHALL appear in the gate's output

<!-- Scenario ID: gen-eval-framework.cross-capability-exclusion-fails -->
#### Scenario: One capability cannot excuse another's requirement

- **WHEN** `openspec/contracts/<A>/traceability-exclusions.yaml` contains an
  exclusion whose requirement identifier resolves to capability `B`
- **THEN** the gate SHALL exit non-zero naming both `A` and `B`
- **AND** the excluded requirement SHALL still count against `B`'s reverse
  completeness

### Requirement: Forward enforcement is opt-in per contract document

A contract document declaring a traceability block on any operation SHALL be
enforced strictly across all of its operations. A contract document declaring
none SHALL be recorded as untraced and SHALL NOT fail forward completeness.

Keying forward enforcement on the block's presence in the document makes the
decision one-way at the right grain. A document cannot report green while most
of it is unattributed, and a document that has not opted in is visible in the
report rather than silent. Splitting a capability's surface into several
documents stages the forward direction — each document opts in when its
subsystem is ready — without weakening any document that has opted in.

<!-- Scenario ID: gen-eval-framework.opting-in-is-total -->
#### Scenario: Declaring traceability commits the whole contract document

- **WHEN** a contract document declares a traceability block on one operation
  and omits it on another
- **THEN** the gate SHALL fail for the operation that omits it

<!-- Scenario ID: gen-eval-framework.untraced-is-recorded -->
#### Scenario: A contract with no traceability is recorded, not failed

- **WHEN** a contract document declares no traceability block on any operation
- **THEN** the gate SHALL record the document as untraced
- **AND** the run SHALL NOT fail on that document
- **AND** the untraced status SHALL appear in the gate's output

<!-- Scenario ID: gen-eval-framework.mixed-capability-documents -->
#### Scenario: A traced and an untraced document coexist in one capability

- **WHEN** a capability holds one contract document that has opted in and one
  that has not
- **THEN** forward completeness SHALL be enforced on the traced document only
- **AND** the untraced document SHALL be recorded as untraced
- **AND** the traced document's citations SHALL still count toward the
  capability's reverse completeness

### Requirement: Reverse enforcement is opt-in per capability via the exclusions file

Reverse completeness SHALL be enforced for a capability exactly when
`openspec/contracts/<capability>/traceability-exclusions.yaml` exists. For a
capability without that file, uncited requirements SHALL be reported and SHALL
NOT fail the gate. An exclusions file with an empty exclusion list SHALL be
valid and SHALL mean every requirement must be cited.

The two directions make different claims with different owners, so each gets
exactly one switch. Forward — "every operation in this document is justified" —
is a claim the document's author can make one document at a time. Reverse —
"every requirement of this capability is served or excused" — is a claim about
the whole capability that no single document can make. Creating the exclusions
file is the act of triaging the capability's requirement set, which is why the
file and the switch are the same artifact: the switch cannot be flipped without
doing the work it certifies.

<!-- Scenario ID: gen-eval-framework.reverse-opt-in-enforces -->
#### Scenario: The exclusions file's presence enforces reverse completeness

- **WHEN** a capability has a traceability-exclusions file and a requirement is
  cited by no operation and not excluded
- **THEN** the gate SHALL fail naming that requirement

<!-- Scenario ID: gen-eval-framework.reverse-not-opted-in-reports -->
#### Scenario: Without the exclusions file, uncited requirements are reported

- **WHEN** a capability has no traceability-exclusions file and a requirement
  is cited by no operation
- **THEN** the gate SHALL report that requirement as uncited
- **AND** the run SHALL NOT fail on it
- **AND** the capability's reverse status SHALL appear in the output as
  not opted in

### Requirement: The gate reports citation concentration deterministically

The gate SHALL emit, for every cited requirement in a capability, the count and
share of the capability's traced operations citing it, ordered by share
descending, and SHALL mark entries at or above a named reporting constant as
concentrated. The exit code SHALL NOT depend on concentration.

Citing one catch-all requirement everywhere is the predictable way to defeat
this gate. The threshold between a requirement that genuinely governs many
operations and box-ticking is a judgement, so concentration never fails a run —
but the *output* must be deterministic, or the test for it asserts the
implementation against itself. The denominator is the capability's traced
operations, not one document's: a per-document share would be defeated by
splitting the document.

<!-- Scenario ID: gen-eval-framework.concentration-is-surfaced -->
#### Scenario: Concentration appears in the output

- **WHEN** one requirement's share of a capability's traced operations meets or
  exceeds the reporting constant
- **THEN** the gate SHALL name that requirement, its count, and its share in
  the concentration section of its output

<!-- Scenario ID: gen-eval-framework.concentration-never-fails -->
#### Scenario: A run whose only finding is concentration exits zero

- **WHEN** a run's completeness checks all pass and one requirement exceeds the
  concentration reporting constant
- **THEN** the run SHALL exit zero
- **AND** the same concentration entry SHALL be present when an unrelated
  failure makes the run exit non-zero

### Requirement: Citations may name requirements in another capability

A citation SHALL be permitted to name a requirement belonging to any
capability. The gate SHALL report cross-capability citations as a distinct list
and SHALL NOT fail on the capability differing. A cross-capability citation
SHALL count toward the cited capability's reverse completeness.

Cross-capability operations already exist — one service may serve another
capability's requirement. Forbidding the citation would not remove the
coupling; it would make the only artifact that records it illegal. Crediting
the cited capability is what makes the record honest: the requirement *is*
served, and reporting it uncited would demand a false exclusion.

<!-- Scenario ID: gen-eval-framework.cross-capability-citation -->
#### Scenario: An operation cites another capability's requirement

- **WHEN** an operation in one capability's contract cites a requirement
  identifier carrying a different capability's prefix
- **THEN** the citation SHALL resolve against that capability's spec
- **AND** the gate SHALL NOT fail on the basis of the capability differing
- **AND** the gate SHALL name the citation in its cross-capability report

<!-- Scenario ID: gen-eval-framework.cross-capability-credits-reverse -->
#### Scenario: A cross-capability citation satisfies the cited capability's reverse completeness

- **WHEN** capability B's requirement is cited only by an operation in
  capability A's contract
- **THEN** B's reverse completeness SHALL treat that requirement as cited

<!-- Scenario ID: gen-eval-framework.cross-capability-unresolvable-fails -->
#### Scenario: An unresolvable cross-capability citation fails

- **WHEN** a citation names an identifier whose capability prefix matches no
  capability spec, or whose slug matches no requirement in that capability
- **THEN** the gate SHALL fail naming the citation
- **AND** the failure SHALL distinguish an unknown capability from an unknown
  requirement within a known capability

### Requirement: Completeness is evaluated per capability

The framework SHALL evaluate completeness across every contract document citing
into a capability, taken together, rather than one document at a time.

Because a requirement may be served by an operation in another document — or
another capability's document — a per-document evaluation reports
genuinely-served requirements as uncited, and the only available remedy is an
exclusion asserting something false.

<!-- Scenario ID: gen-eval-framework.capability-scoped-completeness -->
#### Scenario: A requirement served from another contract is covered

- **WHEN** a requirement is cited by an operation in a different contract
  document of the same capability
- **THEN** reverse completeness SHALL treat that requirement as cited
- **AND** the gate SHALL NOT require a duplicate citation in every document

<!-- Scenario ID: gen-eval-framework.split-contracts-are-unioned -->
#### Scenario: A capability's contracts are evaluated as one surface

- **WHEN** a capability declares several contract documents
- **THEN** the gate SHALL union their citations before evaluating completeness
- **AND** a capability whose contracts are split SHALL be evaluated identically
  to one whose contracts are combined

<!-- Scenario ID: gen-eval-framework.union-does-not-hide-gaps -->
#### Scenario: A requirement cited by no document still fails

- **WHEN** a capability with reverse enforcement declares two contract
  documents and a requirement is cited by neither and excluded by neither
- **THEN** the gate SHALL fail naming that requirement exactly once
- **AND** it SHALL NOT report the gap once per document

### Requirement: The active change's spec delta shadows the archived spec

The framework SHALL resolve requirement identifiers against the archived
capability specs, with the active change's spec delta taking precedence: added
requirements SHALL resolve, modified requirements SHALL resolve to the changed
form, removed requirements SHALL NOT resolve, and renamed requirements SHALL
resolve under the new identifier only. Requirements belonging to other
in-flight changes SHALL be neither citable nor excludable.

Every requirement a change adds exists only in its own delta until archive, so
resolving against the archive alone would fail every citation a change makes to
its own new requirements. Permitting references to *other* changes' unarchived
requirements is separately disallowed: when such a change archives, the
exclusion written against it silently suppresses a real finding while its
target exists, which no staleness check can detect. RENAMED sections matter
because ignoring them fails open — the old identifier keeps resolving out of
the archive while the new one resolves to nothing, both wrong in opposite
directions.

<!-- Scenario ID: gen-eval-framework.added-requirement-resolves -->
#### Scenario: A citation to the change's own new requirement resolves

- **WHEN** the active change adds a requirement and an operation cites it
- **THEN** the identifier SHALL resolve
- **AND** the gate SHALL NOT fail on the requirement being unarchived

<!-- Scenario ID: gen-eval-framework.removed-requirement-stops-resolving -->
#### Scenario: Removing a requirement breaks operations that still cite it

- **WHEN** the active change removes a requirement and an operation still cites
  it
- **THEN** the identifier SHALL NOT resolve
- **AND** the gate SHALL fail naming the operation

<!-- Scenario ID: gen-eval-framework.renamed-requirement-rebinds-closed -->
#### Scenario: Renaming a requirement moves its identifier, fail-closed

- **WHEN** the active change renames a requirement's heading, or modifies a
  requirement in a way that rewords its heading
- **THEN** the previous identifier SHALL NOT resolve
- **AND** the new identifier SHALL resolve
- **AND** a citation still naming the previous identifier SHALL fail, naming
  the new heading among the candidates

<!-- Scenario ID: gen-eval-framework.other-changes-are-invisible -->
#### Scenario: Another change's unarchived requirement cannot be referenced

- **WHEN** a citation or exclusion names a requirement that exists only in a
  different in-flight change's spec delta
- **THEN** the gate SHALL fail
- **AND** the failure SHALL state that the requirement is not in the effective
  requirement set

### Requirement: Validation-time evaluation is scoped to the change

At validation the framework SHALL evaluate only the operations and requirements
the active change touches, and SHALL report rather than fail on violations that
already existed. The touched set SHALL be: operations whose contract nodes
changed in the diff between the merge base and the working tree, requirements
added, modified, removed, or renamed in the active change's spec delta, and
requirements named by citations or exclusions the diff adds or changes. The
active change SHALL be named explicitly to the gate, the merge base SHALL be
computed against a named integration branch, and a merge base that cannot be
resolved SHALL be an error rather than an empty scope.

A change that flips an opt-in switch SHALL additionally touch everything that
switch newly governs. Where the diff adds a traceability block to a contract
document that had none, every operation in that document SHALL be touched.
Where the diff adds a `traceability-exclusions.yaml` for a capability that had
none, every requirement of that capability SHALL be touched.

A validation run enforcing the full archived set blocks every change to a
capability on gaps it did not create. But a scope that silently resolves to
empty is worse than a broad one — a blocking gate that evaluates nothing while
reporting success is the unfalsifiable-green failure this whole change exists
to eliminate. Change scope restricts what the full evaluation would enforce; it
never enforces anything the full evaluation would not.

The opt-in clause exists because the transition is otherwise invisible to a
node-level diff. Adding one traceability block changes one node, but D6 makes
the whole document strictly enforced from that moment; creating an exclusions
file changes no requirement at all, yet D13 turns the capability's entire
reverse direction blocking. Under a touched set keyed only on changed nodes,
`/validate-feature` would pass on the very change that flips the switch and
`main` would red immediately afterward — the gate reporting green on the one
diff that could still cheaply fix it. The switch-flipping change is precisely
the change that must prove the surface is clean, because it is the change
asserting that it is.

<!-- Scenario ID: gen-eval-framework.pre-existing-gap-does-not-block -->
#### Scenario: A pre-existing gap does not fail a change that did not create it

- **WHEN** a change touches one operation in a capability that already contains
  uncited operations it does not touch
- **THEN** the gate SHALL fail only on the touched operation if it is uncited
- **AND** it SHALL report the untouched pre-existing gaps without failing

<!-- Scenario ID: gen-eval-framework.change-scoped-reverse-completeness -->
#### Scenario: A requirement the change adds and nobody cites fails the change-scoped run

- **WHEN** the active change adds a requirement to a capability with reverse
  enforcement, and no operation cites it and no exclusion covers it
- **THEN** the change-scoped run SHALL fail naming that requirement

<!-- Scenario ID: gen-eval-framework.forward-opt-in-touches-document -->
#### Scenario: Opting a document in touches every operation in it

- **WHEN** the active change adds a traceability block to a contract document
  that previously declared none, and another operation in that same document
  cites no requirement and carries no exclusion
- **THEN** the change-scoped run SHALL fail naming that other operation
- **AND** it SHALL NOT pass on the grounds that the operation's node is
  unchanged in the diff

<!-- Scenario ID: gen-eval-framework.reverse-opt-in-touches-capability -->
#### Scenario: Opting a capability in touches every requirement of it

- **WHEN** the active change adds `traceability-exclusions.yaml` to a
  capability that previously had none, and a pre-existing requirement of that
  capability is cited by no operation and excluded by no entry
- **THEN** the change-scoped run SHALL fail naming that requirement
- **AND** the failure SHALL NOT be deferred to the full sweep on `main`

<!-- Scenario ID: gen-eval-framework.unresolvable-scope-errors -->
#### Scenario: An unresolvable merge base is an error, not an empty scope

- **WHEN** a change-scoped run cannot resolve the merge base against the
  integration branch, or is given no active change identifier
- **THEN** the run SHALL exit non-zero stating what could not be resolved
- **AND** it SHALL NOT pass by evaluating an empty touched set

<!-- Scenario ID: gen-eval-framework.scope-is-stated-in-the-output -->
#### Scenario: The output states which scope it evaluated

- **WHEN** the gate completes a change-scoped run
- **THEN** its output SHALL contain the line
  `scope: change (<change-id>) — touched operations and requirements only; capability completeness not evaluated`
- **AND** it SHALL NOT report completeness for the capability as a whole

### Requirement: The full sweep blocks opted-in surfaces and reports the rest

A full-capability evaluation SHALL run as a blocking check on the merge
candidate, and SHALL run again, explicitly non-blocking, on the integration
branch after merge. The blocking run SHALL fail on violations in contract
documents that have opted into forward enforcement and in capabilities that
have opted into reverse enforcement, and SHALL report untraced documents and
not-opted-in capabilities without failing.

The gate SHALL have exactly one resolution rule, keyed on whether a change id
is supplied. Given `--change <id>`, it SHALL resolve against the archived
capability specs shadowed by that change's spec delta, with other in-flight
changes' requirements neither citable nor excludable. With `--change` omitted,
it SHALL resolve against the archived specs shadowed by every spec delta present
directly under `openspec/changes/<id>/` on the branch, excluding
`openspec/changes/archive/`. Archived deltas SHALL NOT be unioned: they have
already been merged into `openspec/specs/`, so re-applying them shadows the
archive with itself, and a delta that REMOVED or RENAMED a requirement would
resurrect or re-move it. Which run blocks SHALL be a property of
the CI job and not of the gate: every blocking invocation SHALL supply
`--change <id>`, and union mode SHALL be used only by the non-blocking
post-merge run. The gate SHALL NOT infer blocking from the flag, and SHALL NOT
fail merely because `--change` was omitted — a gate that required a change id
would reject the one run legitimately entitled to omit it.

The sweep SHALL run as a single CI job on three events — `pull_request`,
`merge_group`, and `push` to the integration branch — and SHALL select both its
invocation and whether its result gates on `github.event_name`. The job SHALL
NOT be guarded off any of those three events. A required check that does not run
on `merge_group` is not a check on the merge candidate, and an unguarded job on
an event with no rule is the unfalsifiable green this requirement exists to
prevent; the event set is therefore normative here, not a CI implementation
detail.

Change-id derivation SHALL consider only paths that the diff ADDS or MODIFIES,
under a directory matching `openspec/changes/<id>/` where `<id>` is not
`archive`, and SHALL be computed with rename detection disabled so that the
derived set does not depend on a similarity heuristic. Deleted paths SHALL NOT
yield a change id.

All three conditions are load-bearing, and the deletion filter is the one whose
absence is least visible. Archiving is a `git mv` from
`openspec/changes/<id>/` to `openspec/changes/archive/<date>-<id>/`. With
rename detection disabled — which the determinism requirement above mandates —
that move decomposes into deletions at the source and additions at the
destination. Excluding `archive` therefore suppresses only the destination
half: the source half still names `<id>`, so an archive pull request would
derive the id of the change it is archiving and invoke a blocking run against a
directory that no longer exists on that commit. Excluding deletions suppresses
the source half, and the two exclusions together make an archive pull request
touch no change directory at all.

That result — the SKIP — is the correct one, because archiving is OpenSpec
bookkeeping rather than a change the gate can scope to, and any traceability
debt the merge introduces is reported by the post-merge run.

The deletion filter also makes derivation robust to a base commit that predates
an archive: without it, any pull request whose diff spans an archive commit
derives the archived id alongside its own and fails the ambiguity rule.

On `pull_request`, the job SHALL derive a change id from the change directory
touched by the diff against the pull request's base commit, SHALL invoke the
gate with `--change <id>`, and SHALL block. Where the diff touches no change
directory, it SHALL print an explicit SKIP naming the branch and SHALL NOT
fail. Where it touches more than one, it SHALL fail as ambiguous rather than
choosing.

On `merge_group`, the job SHALL derive the set of change directories touched by
the diff against the merge group's base commit, SHALL invoke the gate once per
derived change id with `--change <id>`, and SHALL block if any invocation fails.
The ambiguity rule SHALL NOT apply: a merge group batches whatever the queue
batched, so several change directories is its ordinary case rather than an
error. Where the diff touches no change directory, the job SHALL print an
explicit SKIP naming the merge group and SHALL NOT fail.

The merge-group run SHALL NOT use union mode. The set of change directories in
the *diff* is the batch; the set present in the *tree* is not, because a
merge-queue branch is the integration branch plus the batched pull requests and
therefore carries every unarchived change directory the integration branch
already had. Unioning the tree would evaluate a blocking run against
requirements belonging to changes that are not in the batch, whose
implementations have not landed and which the batch's authors cannot cite or
exclude — an exclusion naming them fails by the rule above. A blocking run
SHALL only ever be scoped to a change it is actually evaluating.

On `push` to the integration branch, the job SHALL invoke the gate with
`--change` omitted, SHALL evaluate every capability in full, and SHALL NOT
block — its exit status SHALL NOT depend on what it found.

Where a base commit is required and cannot be resolved, the job SHALL fail
naming the event and the base it could not resolve, and SHALL NOT skip.

An unresolvable base and an absent change directory SHALL NOT share an exit
path. They are opposite conditions: the second says the work was not planned
through OpenSpec and is legitimately out of the gate's remit, while the first
says the gate does not know what it is looking at. A rule that skipped on both
would turn every event whose base the derivation did not anticipate into a
silent pass. That is the unfalsifiable-green outcome this capability's
change-scope requirement already forbids in terms; the blocking sweep does not
get an exemption from it. The rule is stated for the three events the job runs
on precisely so that a fourth event, added later without a rule, fails loudly
instead of passing quietly.

Keying resolution on the flag rather than on the run context is what keeps the
gate out of the business of knowing which CI job invoked it. The gate still has
exactly one resolution rule; the job, not the gate, reads `github.event_name`.

Union mode is deliberately the looser of the two — it admits requirements from
changes whose implementation has not landed — and that is exactly why the only
run that uses it reports and never blocks. `openspec/changes/` on any branch
built from the integration branch holds every in-flight change, not the subset
under evaluation, so union mode can never say anything scoped. An earlier draft
of this requirement assumed a merge-queue branch was an exception, on the
reasoning that it "is the integration branch plus the batched pull requests" —
which is true and is precisely the refutation, since the integration branch part
carries all the others. Under that draft the blocking merge-group run would have
failed on uncited requirements belonging to changes outside the batch, and the
batch's authors could not have fixed it: citing them is not their work, and
excluding them fails by the other-changes-are-invisible rule. Blocking scope
comes from the diff, never from the tree.

The SKIP exists because OpenSpec is not the only way work reaches this
repository. Dependency bumps, chores, and cloud-session branches carry no spec
delta, no contract citation, and no exclusions file, because nothing in the
planning process was expected to produce them; failing them for the absence of
an artifact they were never asked to author would red every such pull request
on the day this gate lands. The debt those pull requests could still introduce
is not lost — the post-merge run sees every capability in full and reports it.

Diff-scoping alone would never surface accumulated gaps — nothing touches them,
so nothing reports them. The sweep is what makes existing debt visible without
blocking anyone, and opting in is the only switch that turns its report into a
block: a second reported-to-blocking flag would create an opted-in-but-not-
blocking state, which is the half-traced-yet-green outcome opt-in exists to
make impossible. The blocking run is on the merge candidate, not on a push to
the integration branch: a scheduled run cannot block a merge, but neither can a
push event that fires *after* the merge has landed. Both can red the branch;
only a check on the candidate can stop it going red.

<!-- Scenario ID: gen-eval-framework.sweep-blocks-opted-in -->
#### Scenario: An opted-in surface fails the sweep

- **WHEN** the full sweep finds an uncited operation in a traced document, or
  an uncited unexcluded requirement in a capability with reverse enforcement
- **THEN** the sweep SHALL exit non-zero naming the violation

<!-- Scenario ID: gen-eval-framework.sweep-reports-not-opted-in -->
#### Scenario: A surface that has not opted in is reported, not failed

- **WHEN** the full sweep encounters untraced contract documents and
  capabilities without reverse enforcement
- **THEN** it SHALL report each with its status
- **AND** it SHALL NOT fail on them

<!-- Scenario ID: gen-eval-framework.change-flag-selects-resolution -->
#### Scenario: The change flag selects which delta shadows the archive

- **WHEN** the sweep runs at capability scope with `--change <id>` on a change
  that adds new requirements and cites them from a contract document in the
  same change
- **THEN** those citations SHALL resolve against that change's spec delta
- **AND** requirements belonging to other in-flight changes SHALL NOT resolve

<!-- Scenario ID: gen-eval-framework.omitted-change-flag-unions-deltas -->
#### Scenario: Omitting the change flag unions every on-branch delta

- **WHEN** the sweep runs at capability scope with no `--change` argument
- **THEN** it SHALL resolve against the archived specs shadowed by every spec
  delta present directly under `openspec/changes/<id>/`
- **AND** it SHALL NOT union deltas under `openspec/changes/archive/`, which
  are already merged into `openspec/specs/`
- **AND** it SHALL NOT fail for the absence of a change id

<!-- Scenario ID: gen-eval-framework.non-openspec-pr-skips -->
#### Scenario: A pull request that was not planned through OpenSpec skips

- **WHEN** the blocking job runs on a pull request whose base resolves and
  whose diff touches no directory under `openspec/changes/`
- **THEN** it SHALL print a SKIP naming the branch
- **AND** it SHALL NOT fail the pull request
- **AND** the post-merge run SHALL still evaluate every capability in full

<!-- Scenario ID: gen-eval-framework.unresolvable-base-fails-not-skips -->
#### Scenario: An unresolvable base fails rather than skipping

- **WHEN** the job runs on an event that requires a base commit and cannot
  resolve it
- **THEN** it SHALL fail naming the event and the base it could not resolve
- **AND** it SHALL NOT take the no-change-directory SKIP path, which would make
  an unanticipated event indistinguishable from work not planned through
  OpenSpec

<!-- Scenario ID: gen-eval-framework.ambiguous-change-fails -->
#### Scenario: A pull request touching two change directories fails as ambiguous

- **WHEN** the job runs on a `pull_request` event whose diff touches more than
  one directory under `openspec/changes/`
- **THEN** it SHALL fail naming each candidate change id
- **AND** it SHALL NOT choose one

<!-- Scenario ID: gen-eval-framework.merge-group-iterates-over-the-batch -->
#### Scenario: A merge group batching two changes is evaluated once per change

- **WHEN** the job runs on a `merge_group` event whose diff touches two
  directories under `openspec/changes/`
- **THEN** it SHALL invoke the gate twice, once per derived change id, each
  with `--change <id>`
- **AND** it SHALL NOT fail as ambiguous
- **AND** a violation in an opted-in surface of either change SHALL fail the
  merge group

<!-- Scenario ID: gen-eval-framework.archive-pull-requests-skip -->
#### Scenario: An archive pull request derives no change id

- **WHEN** the job runs on a pull request that moves `openspec/changes/<id>/`
  to `openspec/changes/archive/<date>-<id>/` and changes nothing else under
  `openspec/changes/`
- **THEN** it SHALL derive no change id
- **AND** it SHALL derive neither the literal id `archive` from the added paths
  nor `<id>` from the deleted paths
- **AND** it SHALL print a SKIP and SHALL NOT fail as ambiguous

<!-- Scenario ID: gen-eval-framework.merge-group-ignores-unbatched-changes -->
#### Scenario: A merge group is not evaluated against changes outside the batch

- **WHEN** the job runs on a `merge_group` event and the branch carries
  unarchived change directories that the diff against the merge group's base
  does not touch
- **THEN** those changes' requirements SHALL NOT enter any blocking invocation's
  effective requirement set
- **AND** the merge group SHALL NOT fail for an uncited requirement belonging
  to a change outside the batch

<!-- Scenario ID: gen-eval-framework.push-to-integration-branch-reports -->
#### Scenario: The run on the integration branch cannot fail

- **WHEN** the job runs on a `push` to the integration branch and the sweep
  finds violations in opted-in surfaces
- **THEN** it SHALL report every violation it found
- **AND** it SHALL exit zero, because a run that fires after the merge can red
  the branch but cannot stop it going red

<!-- Scenario ID: gen-eval-framework.job-runs-on-every-declared-event -->
#### Scenario: The job is not guarded off any declared event

- **WHEN** the CI workflow declares the `pull_request`, `merge_group`, and
  `push` triggers
- **THEN** the sweep job SHALL run on all three
- **AND** it SHALL NOT carry a condition that excludes it from `merge_group`,
  which would leave the merge candidate unevaluated by the check that gates it

### Requirement: The gate fails closed on malformed input

A contract document SHALL be a contract instance under
`openspec/contracts/<capability>/openapi/` or
`openspec/contracts/<capability>/cli/`; files under `schemas/` SHALL NOT be
contract documents. An instance SHALL be identified structurally, not by
location: a `.yaml`, `.yml`, or `.json` file whose top level is a mapping
carrying an `openapi` key (OpenAPI instance) or a `tool` key (CLI contract
instance). `README.md` and `traceability-exclusions.yaml` carry neither and
SHALL NOT be treated as instances under any rule. An instance found at the
capability root SHALL be reported as misplaced, naming the file and the
expected location, and SHALL NOT be silently skipped; the sweep SHALL NOT fail
on it, and change scope SHALL fail on it only when the diff adds or modifies
it. A contract document that cannot be parsed SHALL fail the gate naming
the file, and SHALL NOT be recorded as untraced. A traceability block that violates the
traceability schema SHALL fail the gate naming the file and the offending
block. An existing `traceability-exclusions.yaml` that cannot be read, cannot
be parsed, is empty, or violates the exclusions schema SHALL fail the gate
naming the file, and SHALL NOT be treated as absent. A capability directory
containing contract documents that declare traceability, but no capability
spec, SHALL fail with a message distinguishing the missing spec from an
unresolved identifier; where no document declares traceability, the missing
spec SHALL be reported and SHALL NOT fail. A capability with a spec and no
contracts SHALL be recorded as forward-untraced, which SHALL NOT affect
whether its reverse direction is enforced.

Enforcement is keyed on the presence of traceability blocks, so a parse error
that reads as "no blocks found" would silently downgrade a traced contract to
untraced and turn a syntax error into a green run. The schema-invalid shapes —
`requirements` and `excluded` together, or an empty citation list — were
excluded from the schema deliberately, and a gate that let them through would
have to pick a winner, which is the silent decision the schema exists to
refuse.

The misplaced instance is the one rule here that reports rather than fails, and
deliberately: `openspec/contracts/code-search/v2.yaml` is an OpenAPI instance at
a capability root **today**. A rule that failed on it would red the tree the
moment the blocking sweep was installed, and would contradict the acceptance
criterion that the merge candidate exit zero at capability scope. Reporting the
existing one while failing any newly added one is the ratchet: the debt is
visible and cannot grow, without the change reddening the branch it lands on.
Structural identification matters for the same reason — "any file at the root"
fails `README.md`, and "any YAML at the root" fails
`traceability-exclusions.yaml`, which would turn D13's reverse opt-in switch
into a permanent gate failure the first time anyone flipped it.

The exclusions file needs the same protection for a stronger reason: D13 makes
its *existence* the reverse switch, so "cannot read it" and "it isn't there"
are one byte apart in consequence and opposite in meaning. A capability that
had opted in would silently opt back out on a YAML typo, and the direction D3
calls the valuable one would fail open — inverting
`check_coverage_completeness.py`, the precedent D4 claims to lift wholesale.
Absence is a decision; unreadability is an accident, and the gate SHALL NOT
read one as the other.

The missing-spec case is bounded twice, because measured on this repository on
2026-07-28 an unbounded reading would red `main` the moment this change merged.
Three capability directories under `openspec/contracts/` have no matching spec
directory — `phase-record`, `project-context-refresh` (the spec tree carries
`project-context-refresh-orchestration` and `project-context-refresh-records`,
neither named `project-context-refresh`), and `prototyping`. All three hold
only `schemas/`, so under D6's definition they contain no contract *documents*
at all and the rule never reaches them. The opt-in gate is the second bound,
covering the future case where such a directory gains an instance: the rule
keeps its teeth exactly where a document has claimed to be traced, which is the
only place a missing spec can hide an unresolved citation.

<!-- Scenario ID: gen-eval-framework.malformed-contract-fails -->
#### Scenario: An unparseable contract fails the gate

- **WHEN** a contract document under `openspec/contracts/` cannot be parsed
- **THEN** the gate SHALL exit non-zero naming the file
- **AND** the document SHALL NOT be recorded as untraced

<!-- Scenario ID: gen-eval-framework.schema-invalid-block-fails -->
#### Scenario: A schema-invalid traceability block fails the gate

- **WHEN** a traceability block carries both `requirements` and `excluded`, or
  an empty `requirements` list, or an exclusion without a reason field
- **THEN** the gate SHALL exit non-zero naming the file and the operation
  carrying the block
- **AND** it SHALL NOT choose between the conflicting keys

<!-- Scenario ID: gen-eval-framework.misplaced-instance-is-reported -->
#### Scenario: A contract instance outside openapi/ or cli/ is reported

- **WHEN** the full sweep encounters a file at a capability root whose top
  level carries an `openapi` or `tool` key, rather than under `openapi/` or
  `cli/`
- **THEN** the sweep SHALL report it as misplaced, naming the file and the
  expected location
- **AND** it SHALL NOT silently exclude the document from the report
- **AND** it SHALL NOT fail on it, so a pre-existing misplaced instance does
  not red the branch on the day the sweep is installed

<!-- Scenario ID: gen-eval-framework.newly-misplaced-instance-fails -->
#### Scenario: A newly misplaced instance fails change scope

- **WHEN** the diff adds or modifies an instance at a capability root
- **THEN** the change-scoped gate SHALL exit non-zero naming the file and the
  expected location

<!-- Scenario ID: gen-eval-framework.root-non-instances-are-not-documents -->
#### Scenario: README and the exclusions file are never instances

- **WHEN** a capability root holds `README.md` and
  `traceability-exclusions.yaml`
- **THEN** neither SHALL be treated as a contract instance
- **AND** the misplaced-instance rule SHALL NOT fire on the exclusions file,
  whose presence at that exact path is the reverse opt-in switch

<!-- Scenario ID: gen-eval-framework.schemas-are-not-documents -->
#### Scenario: A schemas-only capability holds no contract documents

- **WHEN** a capability directory contains only `schemas/*.schema.json` files
- **THEN** the gate SHALL NOT treat it as containing contract documents
- **AND** the missing-capability-spec rule SHALL NOT fail on it

<!-- Scenario ID: gen-eval-framework.malformed-exclusions-file-fails -->
#### Scenario: An unreadable exclusions file fails rather than opting out

- **WHEN** `openspec/contracts/<capability>/traceability-exclusions.yaml`
  exists but cannot be read, cannot be parsed, is empty, or violates the
  exclusions schema
- **THEN** the gate SHALL exit non-zero naming the file
- **AND** it SHALL NOT record the capability's reverse direction as not opted in

<!-- Scenario ID: gen-eval-framework.missing-capability-spec-fails -->
#### Scenario: Contracts without a capability spec fail distinctly

- **WHEN** a capability directory under `openspec/contracts/` contains contract
  documents that declare traceability, and no `openspec/specs/<capability>/spec.md`
  exists
- **THEN** the gate SHALL fail stating that the capability has no spec
- **AND** the message SHALL be distinguishable from an unresolved identifier

<!-- Scenario ID: gen-eval-framework.missing-spec-untraced-reports -->
#### Scenario: A specless capability that has not opted in is reported

- **WHEN** a capability directory under `openspec/contracts/` contains contract
  documents, none of which declares traceability, and no
  `openspec/specs/<capability>/spec.md` exists
- **THEN** the gate SHALL report the missing spec
- **AND** the run SHALL NOT fail on it

<!-- Scenario ID: gen-eval-framework.spec-without-contracts-untraced -->
#### Scenario: A capability with a spec and no contracts is forward-untraced

- **WHEN** a capability has a spec and no contract documents
- **THEN** the gate SHALL record its forward direction as untraced
- **AND** the run SHALL NOT fail forward completeness on it
- **AND** if the capability has an exclusions file, its reverse completeness
  SHALL still be enforced, failing on any requirement neither cited nor excluded

### Requirement: The gate makes no claim that a requirement is satisfied

The gate SHALL establish only that each operation cites a requirement and each
requirement is cited, and SHALL NOT report or imply that a cited operation
satisfies the requirement it cites. On success its output SHALL contain the
line `<N> operations cite <M> requirements. This gate does not check that any
requirement is satisfied.` and SHALL NOT apply the words `implemented`,
`satisfied`, or `verified` to a requirement as subject.

No static check can decide satisfaction, and output implying otherwise would be
an unfalsifiable green light over a correctness claim. Satisfaction is
established by scenarios, the coverage model, and review. The canonical line is
pinned so the wording test asserts the spec's phrase rather than freezing a
literal the test author invented.

<!-- Scenario ID: gen-eval-framework.no-satisfaction-claim -->
#### Scenario: Output does not claim satisfaction

- **WHEN** the gate passes
- **THEN** its output SHALL contain the canonical citation-claim line
- **AND** it SHALL NOT apply `implemented`, `satisfied`, or `verified` to a
  requirement as subject

### Requirement: Pass-rate gating governs exit status

A run SHALL exit 0 only when the evaluated pass rate meets a configurable
minimum pass-rate threshold (default: 0.95), and a run that evaluated zero
scenarios SHALL exit non-zero regardless of the configured threshold.

Threshold arithmetic alone cannot distinguish a vacuous run from a perfect
one — zero failures over zero scenarios meets any threshold — so vacuous
success is guarded explicitly rather than left to the ratio.

<!-- Scenario ID: gen-eval-framework.pass-rate-gates-exit -->
#### Scenario: Pass rate below the threshold fails the run

- **WHEN** a run evaluates scenarios and the pass rate falls below the
  configured threshold
- **THEN** the run SHALL exit non-zero

#### Scenario: A vacuous run fails regardless of threshold

- **WHEN** a run evaluates zero scenarios
- **THEN** the run SHALL exit non-zero


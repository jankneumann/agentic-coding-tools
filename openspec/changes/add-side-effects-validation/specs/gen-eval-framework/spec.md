# gen-eval-framework Specification Delta

## ADDED Requirements

### Requirement: Extended Assertion Types

The `ExpectBlock` model SHALL support the following assertion types in addition to existing `status`, `exit_code`, `body`, `rows`, `row`, `error_contains`, and `not_empty`:

- `body_contains`: Deep partial matching — assert that expected key/value pairs exist within the response body, including nested structures and array elements. Matching SHALL be recursive: dict values match if all expected keys are present with matching values; list values match if expected items are a subset of actual items.
- `body_excludes`: Negative assertion — assert that specified key/value pairs do NOT appear in the response body. Uses the same recursive matching as `body_contains` but inverts the result.
- `status_one_of`: Accept multiple valid HTTP status codes as a list of integers (e.g., `[200, 201]`). The step passes if the actual status matches any code in the list. `status_one_of` and `status` SHALL be mutually exclusive — specifying both is a validation error.
- `rows_gte`: Assert that the DB row count is greater than or equal to the specified integer.
- `rows_lte`: Assert that the DB row count is less than or equal to the specified integer.
- `array_contains`: Assert that a JSON array at a specified JSONPath contains at least one element matching specified field criteria.

The evaluator's `_compare()` method SHALL implement all extended assertion types with structured diff output on failure.

#### Scenario: body_contains matches partial structure
WHEN a step expects `body_contains: { entries: [{ agent_id: "agent-1" }] }`
AND the response body is `{ entries: [{ agent_id: "agent-1", ts: "..." }, { agent_id: "agent-2" }], total: 2 }`
THEN the assertion passes because the expected subset exists within the actual response

#### Scenario: body_excludes detects unwanted content
WHEN a step expects `body_excludes: { entries: [{ agent_id: "agent-secret" }] }`
AND the response body contains `{ entries: [{ agent_id: "agent-secret" }] }`
THEN the assertion fails with a diff showing the excluded content was present

#### Scenario: status_one_of accepts any listed code
WHEN a step expects `status_one_of: [200, 422]`
AND the response status is 422
THEN the assertion passes

#### Scenario: status and status_one_of are mutually exclusive
WHEN a step specifies both `status: 200` and `status_one_of: [200, 201]`
WHEN the scenario is validated against the Pydantic model
THEN validation fails with a clear error

#### Scenario: rows_gte validates minimum row count
WHEN a DB step expects `rows_gte: 3`
AND the query returns 5 rows
THEN the assertion passes

#### Scenario: array_contains matches element in array
WHEN a step expects `array_contains: { path: "$.memories", match: { tags: ["deadlines"] } }`
AND the response has `memories: [{ id: 1, tags: ["deadlines", "q2"] }, { id: 2, tags: ["meetings"] }]`
THEN the assertion passes because at least one element matches the criteria

### Requirement: Side-Effect Declaration and Verification

The `ActionStep` model SHALL support an optional `side_effects` block with two sub-sections:

- `verify`: A list of verification steps that MUST succeed after the main step executes. Each verification step specifies a transport, query/request, and expectations using the same `ExpectBlock` assertion types.
- `prohibit`: A list of verification steps where the expectations describe states that MUST NOT exist. If any prohibit step's expectations match, the side-effect verification fails.

The evaluator SHALL execute `side_effects.verify` steps immediately after the main step succeeds. If the main step fails, side-effect verification SHALL be skipped.

The evaluator SHALL execute `side_effects.prohibit` steps after `verify` steps. A `prohibit` step passes when its query returns results that do NOT match the expectations (i.e., the prohibited state does not exist).

Side-effect verification results SHALL be reported as sub-verdicts within the parent `StepVerdict`, using a new `side_effect_verdicts` field.

The evaluator SHALL support variable interpolation (`{{ var }}`) in side-effect steps, including `{{ step_start_time }}` which is auto-captured before main step execution.

#### Scenario: Verify side effects after successful operation
WHEN a step has `side_effects.verify` with a DB query checking audit_log
AND the main step succeeds
THEN the evaluator runs the verification query and includes the result in `side_effect_verdicts`

#### Scenario: Prohibit detects unintended mutation
WHEN a step has `side_effects.prohibit` checking for new rows in a table
AND the main step creates an unintended row
THEN the prohibit verification fails and the step verdict becomes `fail`

#### Scenario: Side effects skipped on main step failure
WHEN a step's main execution fails (status mismatch, transport error)
THEN the `side_effects` block is NOT executed and `side_effect_verdicts` is empty

#### Scenario: Step start time auto-captured for side-effect queries
WHEN a step has `side_effects.verify` using `{{ step_start_time }}`
THEN the evaluator injects the timestamp from before the main step executed

### Requirement: Semantic Evaluation with LLM-as-Judge

The `ActionStep` model SHALL support an optional `semantic` block with the following fields:

- `judge`: boolean — whether to invoke LLM judgment (default: `false`)
- `criteria`: string — natural language description of what correct behavior looks like
- `min_confidence`: float — minimum confidence threshold for a pass verdict (default: `0.7`)
- `fields`: list of JSONPath expressions identifying which response fields to evaluate

When `semantic.judge` is `true`, the evaluator SHALL invoke the existing CLI-powered LLM judgment pathway (`claude --print`) with the criteria, extracted field values, and scenario context.

The LLM judgment SHALL return a structured response: `{ verdict: "pass"|"fail", confidence: float, reasoning: str }`.

If the LLM confidence is below `min_confidence`, the step verdict SHALL be `fail` with the reasoning included in the diff.

Semantic evaluation SHALL be opt-in only — no scenario is forced to use it. When the LLM backend is unavailable, semantic evaluation SHALL produce a `skip` sub-verdict with a warning, not a failure.

The evaluator SHALL report semantic verdicts separately in the `StepVerdict` via a new `semantic_verdict` field.

#### Scenario: Semantic evaluation judges search relevance
WHEN a memory search step has `semantic: { judge: true, criteria: "Results should be relevant to project deadlines", fields: ["$.memories[*].summary"] }`
AND the LLM judges the results as relevant with confidence 0.85
THEN the semantic verdict is `pass` with `confidence: 0.85`

#### Scenario: Low confidence produces semantic failure
WHEN the LLM judges results with confidence 0.4 and `min_confidence` is 0.7
THEN the semantic verdict is `fail` with reasoning explaining why confidence was low

#### Scenario: Unavailable LLM produces skip, not failure
WHEN `semantic.judge` is `true` but the LLM backend is unreachable
THEN the semantic verdict is `skip` with a warning message
AND the step's overall verdict is NOT changed to `fail`

### Requirement: Scenario Pack Manifest

The gen-eval framework SHALL support a machine-readable scenario-pack manifest that classifies scenarios by visibility, provenance, determinism, and ownership.

The manifest SHALL support at minimum:
- `visibility`: `public` or `holdout`
- `source`: `spec`, `contract`, `doc`, `incident`, `archive`, or `manual`
- `determinism`: `deterministic`, `bounded-nondeterministic`, or `exploratory`
- `owner`: responsible team or change-id
- `promotion_status`: `draft`, `candidate`, `approved`

#### Scenario: Manifest validates public vs holdout classification
WHEN a scenario-pack manifest containing both public and holdout entries is loaded
THEN each entry is validated against the allowed visibility enum

#### Scenario: Manifest preserves provenance metadata
WHEN a scenario-pack manifest entry derived from an incident is loaded
THEN the framework records `source=incident` and preserves the linked incident reference

#### Scenario: Invalid visibility is rejected
WHEN a manifest entry with `visibility=private` is validated
THEN validation fails with a clear enum error

### Requirement: Visibility-Aware Scenario Execution

The framework SHALL support visibility-aware scenario filtering and reporting.

Implementation-visible workflows SHALL execute `public` scenarios only unless explicitly overridden for diagnostic use. Validation and cleanup gates SHALL support executing both `public` and `holdout` scenarios, with separate reporting for each visibility bucket.

#### Scenario: Implementation run excludes holdout scenarios
WHEN gen-eval runs in implementation context with a manifest containing public and holdout scenarios
THEN only public scenarios are selected for execution

#### Scenario: Cleanup gate includes holdout scenarios
WHEN cleanup validation runs with holdout scenarios available
THEN the holdout scenarios are executed and reported separately from public scenarios

#### Scenario: Report includes visibility coverage
WHEN the report is generated after a completed evaluation run
THEN it includes pass/fail counts and coverage percentages grouped by visibility

### Requirement: Multi-Source Scenario Bootstrap

The framework SHALL support bootstrapping scenarios from OpenSpec spec deltas, contract artifacts, incidents, archived exemplars, and public docs in addition to hand-authored templates.

Bootstrapped scenarios SHALL preserve source metadata in the scenario-pack manifest so downstream users can distinguish normative scenarios from mined or inferred ones.

#### Scenario: Bootstrap from spec deltas
WHEN an OpenSpec change with requirement scenarios triggers the bootstrap flow
THEN it emits scenario seeds linked to the originating requirement refs

#### Scenario: Bootstrap from contract artifact
WHEN an OpenAPI or schema contract triggers scenario bootstrap
THEN it emits scenario seeds that reference the contract path in their metadata

#### Scenario: Bootstrap from empty spec delta produces no scenarios
WHEN a spec delta with no requirement scenarios defined triggers the bootstrap flow
THEN it produces zero scenario seeds and logs a warning indicating no source material

### Requirement: End-to-End User Scenario Templates

The framework SHALL include reusable end-to-end scenario templates that demonstrate full user journey validation using extended assertions, side-effect declarations, and optional semantic evaluation.

Templates SHALL cover at minimum:
- Memory lifecycle (store → search → verify correctness → verify audit → verify no unintended writes)
- Lock-task workflow (acquire → submit → claim → complete → verify state transitions → verify audit)
- Policy enforcement (attempt denied → verify no side effects → escalate → retry → verify correct side effects)
- Handoff integrity (write → read from different agent → verify content → verify audit)
- Cross-interface consistency (HTTP → MCP → CLI → DB → all agree)

Each template SHALL use at least one `side_effects` block and one `array_contains` or `body_contains` assertion.

#### Scenario: Memory lifecycle template validates search correctness
WHEN the memory lifecycle template executes against a live service
THEN it stores test memories, searches with criteria, validates returned results match structurally, and verifies the audit trail recorded the operations

#### Scenario: Lock-task template verifies intermediate state transitions
WHEN the lock-task workflow template executes
THEN it verifies the task status at each stage (pending → claimed → completed) via DB side-effect checks

#### Scenario: Policy enforcement template confirms no side effects on denial
WHEN the policy enforcement template executes a denied operation
THEN the `side_effects.prohibit` block confirms no state changes occurred

# gen-eval-framework Specification Delta

**Change ID**: `side-effects-validation-v2`

## ADDED Requirements

### Requirement: Extended Assertion Types

The `ExpectBlock` model SHALL support the following additional assertion types beyond the base set (status, exit_code, body, rows, row, error_contains, not_empty):

- `body_contains`: Recursive deep subset matching on the response body. A dict matches if every key in expected exists in actual with a matching value (recursive). A list matches if every expected item has a matching distinct actual item (order-independent). Scalars match by equality.
- `body_excludes`: Negative assertion -- the response body MUST NOT contain the specified structure. Uses the same deep matching algorithm as `body_contains`; if the structure IS found, the assertion fails.
- `status_one_of`: Accept any of several HTTP status codes (e.g., `[200, 201]`). `status` and `status_one_of` SHALL be mutually exclusive -- specifying both MUST raise a validation error.
- `rows_gte`: The row count MUST be greater than or equal to the specified value.
- `rows_lte`: The row count MUST be less than or equal to the specified value.
- `array_contains`: Assert that a JSON array at the specified path contains at least one element matching the specified field criteria.

All extended assertions SHALL be optional fields (default `None`). Existing scenarios using only base assertions SHALL continue to work without modification.

#### Scenario: body_contains matches partial structure
WHEN an HTTP step returns `{"result": {"id": 1, "name": "test", "extra": true}}`
AND the expect block specifies `body_contains: {"result": {"id": 1}}`
THEN the assertion passes because the expected structure is a subset of the actual

#### Scenario: body_excludes detects unwanted content
WHEN an HTTP step returns `{"error": "forbidden", "code": 403}`
AND the expect block specifies `body_excludes: {"error": "forbidden"}`
THEN the assertion fails because the excluded structure was found in the response

#### Scenario: status_one_of accepts any listed code
WHEN an HTTP step returns status 201
AND the expect block specifies `status_one_of: [200, 201, 204]`
THEN the assertion passes

#### Scenario: status and status_one_of are mutually exclusive
WHEN an expect block specifies both `status: 200` and `status_one_of: [200, 201]`
THEN model validation raises a ValueError

#### Scenario: rows_gte validates minimum row count
WHEN a DB step returns 5 rows
AND the expect block specifies `rows_gte: 3`
THEN the assertion passes

#### Scenario: rows_lte validates maximum row count
WHEN a DB step returns 5 rows
AND the expect block specifies `rows_lte: 10`
THEN the assertion passes

#### Scenario: array_contains matches element in array
WHEN an HTTP step returns `{"items": [{"id": 1, "tag": "a"}, {"id": 2, "tag": "b"}]}`
AND the expect block specifies `array_contains: {"path": "$.items", "match": {"tag": "b"}}`
THEN the assertion passes because an element matching the criteria exists

---

### Requirement: Side-Effect Declaration and Verification

The `ActionStep` model SHALL support an optional `side_effects` block with two sub-lists:

- `verify`: A list of `SideEffectStep` entries whose expectations MUST succeed. These confirm that expected side effects (audit entries, state transitions, downstream writes) occurred after the main step.
- `prohibit`: A list of `SideEffectStep` entries whose expectations MUST NOT match. If the expectations DO match (the prohibited state exists), the prohibit step SHALL fail with reason "prohibited state detected". This implements inverse matching (D3).

`SideEffectStep` SHALL use the same transport/query model as `ActionStep` (transport, method, endpoint, body, headers, tool, params, command, args, sql, expect, capture, timeout_seconds) but scoped to verification.

Side-effect steps SHALL only execute after the main step succeeds. If the main step fails, all side-effect steps SHALL be skipped with status `skip`.

The evaluator SHALL automatically inject a `step_start_time` variable (ISO 8601 timestamp captured before the main step executes) available for interpolation in side-effect step SQL queries.

Side-effect results SHALL be recorded as `SideEffectVerdict` sub-verdicts on the parent `StepVerdict`, with fields: step_id, mode (verify/prohibit), status (pass/fail/error/skip), actual, expected, diff, error_message.

If any side-effect verdict is `fail`, the parent step's overall status SHALL be `fail` regardless of the main step's structural assertion result.

#### Scenario: Verify side effects after successful operation
WHEN a main step executes successfully
AND a `verify` side-effect step checks that an audit log entry was created
THEN the verify step executes and its verdict is recorded as a sub-verdict

#### Scenario: Prohibit detects unintended mutation
WHEN a main step executes successfully
AND a `prohibit` side-effect step checks for rows in a table that should not have been modified
AND the prohibit expectations MATCH (rows exist)
THEN the prohibit verdict is `fail` with reason "prohibited state detected"

#### Scenario: Side effects skipped on main step failure
WHEN a main step fails (structural assertion failure)
AND `side_effects.verify` and `side_effects.prohibit` are defined
THEN all side-effect steps are skipped with status `skip`

#### Scenario: Step start time auto-captured
WHEN a main step has side-effect steps referencing `{{ step_start_time }}`
THEN the evaluator injects the step's start timestamp before executing side-effect steps

---

### Requirement: Semantic Evaluation

The `ActionStep` model SHALL support an optional `semantic` block with fields:

- `judge`: Boolean (default false). When true, LLM-as-judge evaluation is invoked.
- `criteria`: Natural-language description of what constitutes a correct response.
- `min_confidence`: Float (default 0.7). The LLM verdict MUST meet this confidence threshold to pass.
- `fields`: List of JSONPath expressions identifying which response fields to evaluate.

Semantic verdicts SHALL be additive -- they enhance but never override structural verdicts. If structural assertions pass but semantic evaluation fails, the step SHALL fail. If structural assertions fail, semantic evaluation SHALL be skipped.

When the LLM is unavailable (CLI not installed, rate limited, or error), semantic evaluation SHALL produce a `skip` verdict with reasoning, NOT a `fail`. This prevents LLM unavailability from causing false failures in CI.

Semantic evaluation SHALL invoke the LLM via the CLI pathway (`claude --print`) and parse a structured `{verdict, confidence, reasoning}` response.

The `SemanticVerdict` model SHALL have fields: status (pass/fail/skip), confidence (float), reasoning (string).

#### Scenario: Semantic evaluation judges search relevance
WHEN a step returns search results with `semantic.judge: true`
AND the LLM judges the results as relevant with confidence 0.85
AND `min_confidence` is 0.7
THEN the semantic verdict is `pass` with confidence 0.85

#### Scenario: Low confidence produces semantic failure
WHEN the LLM judges results with confidence 0.5
AND `min_confidence` is 0.7
THEN the semantic verdict is `fail` with the LLM's reasoning

#### Scenario: Unavailable LLM produces skip not failure
WHEN semantic evaluation is configured but the LLM CLI is not available
THEN the semantic verdict is `skip` with reasoning explaining unavailability

---

### Requirement: End-to-End User Scenario Templates

The framework SHALL provide reusable E2E scenario templates that demonstrate multi-step user journeys using extended assertions, side-effect verification, and semantic evaluation.

Templates SHALL cover at minimum:
- Memory lifecycle (store -> search -> verify correctness -> verify audit trail -> verify no unintended writes)
- Lock-task workflow (acquire -> submit -> claim -> complete -> verify state transitions at each step -> verify audit trail consistency)
- Policy enforcement (attempt with insufficient permissions -> verify denial -> verify no side effects -> escalate -> retry -> verify success + correct side effects)
- Handoff integrity (write handoff -> read from different agent -> verify content matches -> verify audit trail)
- Cross-interface consistency (operation via HTTP -> verify via MCP -> verify via CLI -> verify via DB)

Each template SHALL be a valid Scenario YAML parseable by the Pydantic model, using at least one extended assertion type and one side-effect block.

#### Scenario: Memory lifecycle template validates search correctness
WHEN the memory lifecycle E2E template executes
THEN it uses `body_contains` to verify search results AND `side_effects.verify` to check audit trail AND `side_effects.prohibit` to verify no unintended writes

#### Scenario: Lock-task template verifies intermediate state transitions
WHEN the lock-task workflow template executes
THEN it uses `side_effects.verify` after each state-changing step to confirm the expected intermediate state

#### Scenario: Policy enforcement template confirms no side effects on denial
WHEN the policy enforcement template executes a denied operation
THEN it uses `side_effects.prohibit` to verify that no state mutations occurred despite the attempt

## MODIFIED Requirements

### Requirement: Evaluation

The evaluator MUST execute scenario steps sequentially through the transport client specified by each step's `transport` field and compare actual responses against expected values using programmatic assertion matching, including extended assertion types (body_contains, body_excludes, status_one_of, rows_gte, rows_lte, array_contains).

After executing a step's main structural assertions, the evaluator SHALL execute any declared `side_effects.verify` and `side_effects.prohibit` steps and compose their results as `SideEffectVerdict` sub-verdicts on the parent `StepVerdict`.

After structural and side-effect evaluation, the evaluator SHALL execute semantic evaluation if `semantic.judge` is true, and record the result as `semantic_verdict` on the `StepVerdict`.

The evaluation order for each step SHALL be: (1) transport execution, (2) structural assertions (ExpectBlock), (3) side-effect verify/prohibit steps, (4) semantic evaluation. Each phase only runs if the previous phase passed (except prohibit steps which always run if the main step succeeded).

#### Scenario: Extended assertions evaluated alongside base assertions
WHEN a step has both `status: 200` and `body_contains: {"result": {"id": 1}}`
AND the response matches both
THEN the step verdict is `pass`

#### Scenario: Side-effect sub-verdicts composed into step verdict
WHEN a step passes structural assertions and has `side_effects.verify` steps
AND one verify step fails
THEN the parent step verdict is `fail` with the side-effect sub-verdict recorded

#### Scenario: Semantic evaluation runs after side-effect checks
WHEN a step passes structural and side-effect assertions
AND `semantic.judge` is true
THEN semantic evaluation invokes the LLM and records the result on the step verdict

### Requirement: Feedback Loop

The evaluator's findings MUST be synthesized into structured `EvalFeedback` identifying: failing interfaces, under-tested categories, near-miss scenarios, side-effect failure patterns, semantic evaluation gaps, and suggested focus areas.

Steps with side-effect failures SHALL be surfaced as a distinct focus area category ("side-effect failures") alongside failing interfaces and under-tested categories.

Steps where semantic evaluation was skipped due to LLM unavailability SHALL be surfaced as "semantic gaps" in suggested focus areas.

#### Scenario: Side-effect failures surfaced in feedback
WHEN an evaluation run has steps where side-effect verify/prohibit assertions failed
THEN `EvalFeedback.suggested_focus` includes those steps' interfaces under a "side-effect failures" category

#### Scenario: Semantic gaps surfaced in feedback
WHEN an evaluation run has steps where semantic evaluation was skipped
THEN `EvalFeedback.suggested_focus` includes those steps' interfaces under a "semantic gaps" category

### Requirement: Scenario Pack Manifest

The gen-eval framework SHALL support a machine-readable scenario-pack manifest that classifies scenarios by visibility, provenance, determinism, and ownership.

Manifest files SHALL be organized as per-category files (`<category>.manifest.yaml`) co-located with scenario directories, rather than a single monolithic manifest file. The manifest loader SHALL support loading and merging manifests from multiple directories.

The `ManifestEntry` and `ScenarioPackManifest` models SHALL be defined in `manifest.py` as the single source of truth.

#### Scenario: Per-category manifests loaded and merged
WHEN the manifest loader scans a directory containing `lock-lifecycle.manifest.yaml` and `memory-crud.manifest.yaml`
THEN it loads both files and merges their entries into a single `ScenarioPackManifest`

#### Scenario: Monolithic manifest replaced by per-category files
WHEN the framework starts with per-category manifest files
THEN all 97 existing scenario entries are preserved with correct visibility and provenance metadata

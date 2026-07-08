# agent-trajectory-harness — Spec Delta

## ADDED Requirements

### Requirement: Agent scenario model with reused gen-eval goal-gate vocabulary

The harness SHALL define an `AgentScenario` model, loaded from YAML, declaring a
`task_prompt`, a `fixture` (starting repo state and setup), a `skill_under_test`,
a non-empty `vendors` list, and a non-empty `goal_gates` block. The `goal_gates`
block SHALL reuse gen-eval's vocabulary: it SHALL mirror `SideEffectsBlock`'s
`verify`/`prohibit` split, and any `command` goal gate SHALL carry gen-eval's
`ExpectBlock` (imported, not re-implemented) for its assertions. Scenario loading
SHALL reject a scenario with no vendors or no goal gates, and SHALL record the
source file path for provenance.

#### Scenario: a valid scenario YAML loads and validates

- **WHEN** a `*.scenario.yaml` declaring a task prompt, fixture, skill under
  test, at least one vendor, and at least one goal gate is loaded
- **THEN** an `AgentScenario` SHALL be produced with its `source_path` set to the
  file
- **AND** every `command` goal gate's `expect` field SHALL be a gen-eval
  `ExpectBlock` instance

#### Scenario: a scenario missing vendors or gates is rejected

- **WHEN** a scenario is loaded that declares an empty `vendors` list or no goal
  gates
- **THEN** loading SHALL raise a validation error naming the missing requirement

### Requirement: Deterministic goal-gate scoring without an LLM

The harness SHALL provide a scorer that, given a post-run workspace state,
evaluates every goal gate to a pass/fail/error verdict using only filesystem
inspection, git queries, reported PR state, and subprocess execution — with no
LLM involved. A `verify` gate SHALL pass when its condition holds; a `prohibit`
gate SHALL pass when its condition does NOT hold. The scorer SHALL support gate
kinds `file`, `branch`, `commit`, `pr`, `artifact`, and `command`, and SHALL roll
per-gate verdicts up to a single deterministic status that is `error` if any gate
errored, else `fail` if any gate failed, else `pass`.

#### Scenario: verify and prohibit gates are scored against workspace state

- **WHEN** the scorer evaluates a `verify` file gate against a workspace where
  the file exists, and a `prohibit` file gate against a workspace where the
  prohibited file is absent
- **THEN** both gates SHALL be scored `pass`
- **AND** a `prohibit` gate whose prohibited outcome IS present SHALL be scored
  `fail`

#### Scenario: a command gate is scored via the reused ExpectBlock

- **WHEN** a `command` goal gate runs an argv in the workspace and declares an
  `ExpectBlock` with an `exit_code`
- **THEN** the gate SHALL pass only when the process exit code matches the
  `ExpectBlock`

### Requirement: Injectable per-vendor executor and structural parity loop

The harness SHALL define a `ScenarioExecutor` protocol with a
`run(scenario, vendor, workdir) -> RunResult` method, and the runner SHALL loop
over `scenario.vendors`, invoking the injected executor once per vendor, so the
cross-vendor parity matrix is produced structurally. The harness SHALL ship a
real CLI-shelling executor that materializes the fixture and invokes a per-vendor
command, and a fake executor for tests. The real executor SHALL degrade to an
error `RunResult` (never raise) when a vendor is unconfigured or its CLI is
absent, so one broken vendor cannot abort the parity loop.

#### Scenario: the runner produces one result per declared vendor

- **WHEN** a scenario declaring three vendors is run with an injected executor
- **THEN** the resulting parity matrix SHALL contain exactly one vendor result
  per declared vendor, in order
- **AND** each result SHALL carry its own deterministic goal-gate status

#### Scenario: the real executor degrades cleanly with no vendor CLI

- **WHEN** the CLI executor runs a vendor whose configured binary is absent
- **THEN** it SHALL return a `RunResult` with a non-zero exit code and an error
  message rather than raising

### Requirement: Injectable additive LLM-judge trajectory review

The harness SHALL provide an LLM-judge that reviews the normalized transcript
(the `collect-transcripts` event shape) for trajectory quality — inefficiency,
unnecessary actions, and wrong-but-passed. The judge SHALL depend only on an
injected backend protocol (never a hardcoded SDK) and SHALL return a `skip`
verdict — never a `fail` — when no backend is injected or the backend is
unavailable. The judge verdict SHALL be additive and SHALL NOT override the
deterministic goal-gate status.

#### Scenario: the judge skips cleanly with no backend

- **WHEN** the trajectory review runs with no judge backend injected
- **THEN** it SHALL return a `skip` verdict and SHALL NOT fail the run

#### Scenario: the judge contributes findings when a backend is injected

- **WHEN** the trajectory review runs with a backend that reports trajectory
  problems
- **THEN** the verdict SHALL carry the judge's status and its trajectory findings
- **AND** those findings SHALL be additive to, not a replacement for, the
  deterministic goal-gate status

### Requirement: Findings emitter conforming to the review-findings schema

The harness SHALL emit findings conforming to
`openspec/schemas/review-findings.schema.json` from the parity results. Each
deterministic goal-gate failure SHALL produce one finding of a type in the
schema enum (e.g. `behavioral_failure`) with an `axis` and `severity`. Judge
trajectory findings SHALL be emitted additively at a lower severity mapped to an
appropriate schema type. The emitted document SHALL validate against the schema
before it is written.

#### Scenario: emitted findings validate against the schema

- **WHEN** the emitter builds a findings document from a parity matrix containing
  a failed goal gate and a judge finding
- **THEN** the document SHALL conform to `review-findings.schema.json` (validated
  with a JSON-schema validator)
- **AND** each finding SHALL include `id`, `type`, `criticality`, `description`,
  `disposition`, `axis`, and `severity`

#### Scenario: a fully-passing run emits no findings

- **WHEN** the emitter builds a document from a parity matrix where every vendor
  passed every goal gate and the judge reported no findings
- **THEN** the document SHALL conform to the schema with an empty `findings` array

### Requirement: Seed scenarios exercising plan and implement skills

The harness SHALL ship at least two seed scenarios: one exercising a planning
skill and one exercising an implementation skill. Each seed SHALL declare a
fixture repo, at least one `verify` goal gate and at least one `prohibit` goal
gate, and at least two vendors, so the seeds demonstrate the parity model and the
prohibited-side-effect model.

#### Scenario: seed scenarios load and declare parity and prohibitions

- **WHEN** the shipped seed scenarios are loaded
- **THEN** at least one SHALL target a planning skill and at least one an
  implementation skill
- **AND** each SHALL declare multiple vendors and at least one prohibited goal
  gate

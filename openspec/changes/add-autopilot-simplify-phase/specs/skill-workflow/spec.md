# skill-workflow — delta

## MODIFIED Requirements

### Requirement: State Machine Phases

The state machine SHALL support phases: INIT, PLAN, PLAN_REVIEW, PLAN_FIX, IMPLEMENT, IMPL_REVIEW, IMPL_FIX, SIMPLIFY (opt-in), VALIDATE, VAL_REVIEW (optional), VAL_FIX, SUBMIT_PR, DONE, ESCALATE. The state machine SHALL persist its state to `loop-state.json` after every state transition, enabling resumability.

#### Scenario: Normal phase progression (simple feature)

- **GIVEN** a simple feature with no review findings and no complexity checkpoints
- **WHEN** the loop runs to completion
- **THEN** phases SHALL progress: INIT -> PLAN -> PLAN_REVIEW -> IMPLEMENT -> IMPL_REVIEW -> VALIDATE -> SUBMIT_PR -> DONE

#### Scenario: Phase progression with fixes needed

- **GIVEN** a feature where plan review finds medium-severity issues
- **WHEN** the loop processes plan review
- **THEN** phases SHALL progress: PLAN_REVIEW -> PLAN_FIX -> PLAN_REVIEW (re-review)

#### Scenario: Resume after interruption

- **GIVEN** the loop was interrupted during IMPL_REVIEW phase at iteration 2
- **WHEN** the loop is re-invoked with the same change-id
- **THEN** the system SHALL load state from `loop-state.json` and resume from IMPL_REVIEW iteration 2

#### Scenario: Complex feature with VAL_REVIEW

- **GIVEN** a feature that triggered complexity gate checkpoints (e.g., database migrations)
- **WHEN** validation passes
- **THEN** phases SHALL include VAL_REVIEW before SUBMIT_PR

#### Scenario: Opt-in SIMPLIFY phase after implementation review

- **GIVEN** autopilot was invoked with `--simplify`
- **WHEN** IMPL_REVIEW converges
- **THEN** phases SHALL progress: IMPL_REVIEW -> SIMPLIFY -> VALIDATE
- **AND** VALIDATE SHALL run against the head produced by SIMPLIFY

#### Scenario: SIMPLIFY still runs when review is skipped

- **GIVEN** autopilot was invoked with both `--simplify` and `--no-review`
- **WHEN** IMPL_ITERATE completes
- **THEN** phases SHALL progress: IMPL_ITERATE -> SIMPLIFY -> VALIDATE

#### Scenario: Default trace is unchanged without the flag

- **GIVEN** autopilot was invoked without `--simplify`
- **WHEN** the loop runs to completion
- **THEN** `phase_history` SHALL contain no SIMPLIFY entry
- **AND** the sequence of phases and outcomes SHALL equal the pre-change sequence for the same inputs

### Requirement: Per-Phase Archetype Resolution in Autopilot

The autopilot state machine SHALL resolve an archetype for every non-terminal phase before dispatching phase work, SHALL build a provider-neutral phase dispatch payload for sub-agent-capable phases, and SHALL apply the resolved archetype on the production execution path.

The resolution SHALL:

1. Be performed inside `skills/autopilot/scripts/phase_agent.py:_build_options(phase, state_dict)` or a compatibility wrapper that preserves that public behavior.
2. Extract per-phase signals from `state_dict` based on the `signals` field of the phase mapping.
3. Call the coordinator endpoint `POST /archetypes/resolve_for_phase` via `coordination_bridge.try_resolve_archetype_for_phase(phase, signals)`.
4. Resolve a logical archetype and model tier to a provider-specific model identifier for the selected provider.
5. Record the resolved archetype name in `state_dict["_resolved_archetype"]` for downstream use by `LoopState.phase_archetype`.

The 14 non-terminal phases SHALL be: `INIT`, `PLAN`, `PLAN_ITERATE`, `PLAN_REVIEW`, `PLAN_FIX`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `IMPL_FIX`, `SIMPLIFY`, `VALIDATE`, `VAL_REVIEW`, `VAL_FIX`, `SUBMIT_PR`. `SIMPLIFY` is opt-in and resolves to the `implementer` archetype by default.

The `skills/autopilot/SKILL.md` orchestration prose SHALL dispatch the following 8 phases through the provider-neutral dispatch adapter when an adapter is available: `PLAN_ITERATE`, `PLAN_REVIEW`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `SIMPLIFY` (when enabled), `VALIDATE`, `VAL_REVIEW` (when enabled). For these phases the dispatch SHALL pass the provider-specific model ID and SHALL fold the resolved `system_prompt` into the prompt text using the fixed separator `\n\n---\n\n`.

State-only phases (`INIT`, `PLAN`, `SUBMIT_PR`) SHALL still record `LoopState.phase_archetype` for their resolved archetype via a state-only resolver, even though they do not dispatch a phase sub-agent.

Convergence-loop-driven phases (`PLAN_FIX`, `IMPL_FIX`, `VAL_FIX`) SHALL inherit or record `LoopState.phase_archetype` for audit purposes via the convergence loop's existing path, but SHALL NOT receive a separate provider-adapter dispatch block in SKILL.md.

#### Scenario: PLAN phase resolves to provider-specific architect model

- **GIVEN** autopilot is running under provider `codex`
- **AND** `phase_mapping.PLAN.archetype` is `"architect"`
- **AND** the provider model map resolves `architect` or its tier to `gpt-5.5`
- **WHEN** autopilot enters the `PLAN` phase
- **THEN** the resolved phase metadata SHALL contain `"archetype": "architect"`
- **AND** the dispatch metadata SHALL contain `"model": "gpt-5.5"`
- **AND** the dispatch metadata SHALL NOT contain Claude-only model aliases unless the Codex mapping explicitly declares them

#### Scenario: IMPLEMENT phase resolves with provider-specific escalation

- **GIVEN** autopilot is running under provider `antigravity`
- **AND** a work package with `loc_estimate=250` is being processed
- **WHEN** autopilot enters the `IMPLEMENT` phase
- **THEN** the phase resolver SHALL extract `loc_estimate` from `state_dict` and pass it as a signal
- **AND** the resolved archetype SHALL be `"implementer"`
- **AND** the model tier SHALL escalate from `standard` to `premium`
- **AND** the provider-specific model SHALL be an antigravity model ID from the configured antigravity mapping

#### Scenario: Production autopilot run dispatches through provider adapter

- **GIVEN** a real autopilot run executing from `/autopilot <change-id>` against an available coordinator
- **AND** the active provider is `codex`
- **WHEN** the run reaches the `IMPLEMENT` phase
- **THEN** the SKILL.md dispatch block SHALL invoke the provider-neutral dispatch adapter
- **AND** the adapter SHALL receive a payload conforming to `contracts/phase-dispatch-contract.md`
- **AND** the payload's `model` SHALL be provider-specific for Codex
- **AND** the prompt passed to the adapter SHALL begin with the resolved `system_prompt` followed by `\n\n---\n\n` followed by the per-phase task prompt
- **AND** after the adapter returns, `LoopState.phase_archetype` in `loop-state.json` SHALL equal `"implementer"`
- **AND** `LoopState.last_handoff_id` SHALL be updated to the `handoff_id` returned from the dispatched provider result

#### Scenario: Claude remains supported

- **GIVEN** autopilot is running under provider `claude_code`
- **AND** the Claude dispatch adapter is available
- **WHEN** autopilot dispatches a phase that previously used `Agent(...)`
- **THEN** the provider-neutral adapter MAY invoke the existing Claude harness `Agent(...)` surface internally
- **AND** the public SKILL.md contract SHALL still describe the provider-neutral adapter rather than requiring non-Claude providers to expose `Agent(...)`

#### Scenario: SIMPLIFY phase resolves an archetype and is dispatched

- **GIVEN** autopilot is running with `--simplify` under any configured provider
- **WHEN** autopilot enters the `SIMPLIFY` phase
- **THEN** `phase_mapping.SIMPLIFY` SHALL resolve (default archetype `implementer`)
- **AND** the phase SHALL be dispatched through the provider-neutral adapter with the resolved model
- **AND** `LoopState.phase_archetype` SHALL record the resolved archetype for the SIMPLIFY entry

### Requirement: Autopilot Write-Capable Phases Use Worktree Isolation

Autopilot SHALL dispatch every write-capable phase with worktree isolation in
local CLI execution.

#### Scenario: Planning phase writes artifacts

- **WHEN** autopilot runs `PLAN`, `PLAN_ITERATE`, `PLAN_FIX`, or a
  checkpoint-writing `PLAN_REVIEW`
- **THEN** the phase MUST run in a managed worktree or isolated harness checkout
- **AND** plan artifacts MUST land on the feature branch

#### Scenario: Implementation phase writes artifacts

- **WHEN** autopilot runs `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_FIX`, or a
  checkpoint-writing `IMPL_REVIEW`
- **THEN** the phase MUST run in a managed worktree or isolated harness checkout
- **AND** implementation artifacts MUST land on the feature branch

#### Scenario: Simplify phase writes artifacts

- **WHEN** autopilot runs `SIMPLIFY`
- **THEN** the phase MUST run in a managed worktree or isolated harness checkout
- **AND** its `test(...)` and `refactor(...)` commits MUST land on the feature branch

#### Scenario: Validation phase writes artifacts

- **WHEN** autopilot runs `VALIDATE`, `VAL_FIX`, or an artifact-writing
  `VAL_REVIEW`
- **THEN** validation reports, evidence, and fixes MUST be written in a managed
  worktree or isolated harness checkout
- **AND** those artifacts MUST be reviewable in the PR

### Requirement: Simplify Skill Behavior-Preservation Contract

The `simplify-implementation` skill SHALL preserve observable behavior of the code under edit. Before modifying production source, the skill SHALL apply a **coverage gate**:

1. Identify the behavioral surface (public inputs, outputs, errors, and side-effect ordering relevant to the candidate change).
2. Determine whether existing **state-based** tests pin that surface.
3. If the surface is not pinned, the skill SHALL write **characterization tests** that pass against the **current** code (green-on-baseline), commit them separately (conventional `test` type), and only then apply simplifications.

Simplification commits SHALL NOT modify test expectation bodies (`assert` / `expect` arguments or equivalent) to make the suite pass. If expectations must change for the suite to pass, the simplification SHALL be reverted and re-evaluated — the change is treated as a behavior change outside this skill's scope.

The skill SHALL perform **dual-run verification**: the selected test suite SHALL pass on the pre-simplify baseline tip and on the post-simplify tip. Primary invoke remains `/simplify-implementation`; invocation SHALL NOT be default-on in autopilot. An explicit `--simplify` flag on `/autopilot` is an operator request and SHALL enable the opt-in `SIMPLIFY` phase.

#### Scenario: Unpinned surface blocks production edits

- **GIVEN** a module with no tests covering the function under consideration
- **WHEN** an agent runs `/simplify-implementation` on that module
- **THEN** the agent SHALL write characterization tests that pass on the baseline code before editing production source
- **AND** the characterization tests SHALL be committed separately from refactor commits

#### Scenario: Assertion mutation is rejected

- **GIVEN** a simplification that changes return values or error messages
- **WHEN** existing tests fail unless their expectations are edited
- **THEN** the agent SHALL revert the simplification
- **AND** SHALL NOT land expectation-body edits as part of the simplify workflow

#### Scenario: Dual-run proves preservation

- **GIVEN** characterization coverage (existing or newly added) for the surface
- **WHEN** simplifications are complete
- **THEN** the test suite SHALL pass on the commit immediately before the first simplify production edit
- **AND** the test suite SHALL pass on HEAD after all simplify commits

#### Scenario: Not default-on

- **GIVEN** an autopilot or implement-feature run
- **WHEN** no operator explicitly requests `/simplify-implementation` and `--simplify` was not passed
- **THEN** the orchestrator SHALL NOT run a simplify phase

#### Scenario: Flag is the operator request

- **GIVEN** an autopilot run invoked with `--simplify`
- **WHEN** implementation review converges (or IMPL_ITERATE completes under `--no-review`)
- **THEN** the orchestrator SHALL run the `SIMPLIFY` phase
- **AND** the phase SHALL honor this requirement's coverage gate, assertion contract, and dual-run unchanged

### Requirement: Optional Post-Implementation Simplify Polish

The `implement-feature` and `iterate-on-implementation` skills SHALL document an **optional** next step to invoke `/simplify-implementation` for behavior-preserving polish after the suite is green. Any such polish SHALL land as separate `refactor` commits and SHALL NOT mix with `feat` / `fix` commits from the feature work. Both skills SHALL name `/autopilot --simplify` as the orchestrated alternative rather than stating that autopilot never runs simplify.

#### Scenario: Optional polish is not required for implement completion

- **GIVEN** implement-feature has created a PR with a green suite
- **WHEN** the operator does not request simplify
- **THEN** implement-feature completion remains valid without a simplify pass

#### Scenario: Polish paragraphs name the flag

- **WHEN** `implement-feature/SKILL.md` or `iterate-on-implementation/SKILL.md` is read
- **THEN** the optional-polish paragraph SHALL reference `/autopilot --simplify`
- **AND** SHALL NOT state that autopilot never runs simplify

### Requirement: Review Findings Schema Extension

The schema at `openspec/schemas/review-findings.schema.json` (mirrored at
`skills/parallel-infrastructure/install_assets/openspec/schemas/review-findings.schema.json`
and inlined in `agent-coordinator/agents.yaml`) SHALL encode an 8-axis review
categorization and the 5 severity prefixes.

The schema SHALL define:

- An `axis` field on each finding with enum values: `correctness`, `readability`,
  `architecture`, `security`, `performance`, `observability`, `resilience`,
  `compatibility`
- A `severity` field on each finding with enum values: `critical`, `nit`, `optional`,
  `fyi`, `none`
- A `type` enum that includes `test_quality` for read-only findings about tests that
  assert implementation rather than behavior, or production seams that exist only for
  tests (see the `simplify-implementation` Delete catalog and seam catalog)

Both fields SHALL be required for new findings. Findings produced before this change
SHALL be migratable by setting `axis: "correctness"` and `severity: "fyi"` as defaults.
All copies of the schema (canonical, install-assets mirror, `agents.yaml` inline) SHALL
carry the identical enum. The `type` enum SHALL also be identical in
`openspec/schemas/consensus-report.schema.json` and in the hand-maintained fallback enums of
`skills/merge-pull-requests/scripts/vendor_review.py`.

#### Scenario: New finding includes axis and severity

**WHEN** a parallel-review skill produces a finding
**THEN** the finding JSON SHALL include both `axis` and `severity` fields
**AND** the values SHALL match the schema enums

#### Scenario: NFR axes accepted by the schema

**WHEN** a finding with `axis` set to `observability`, `resilience`, or `compatibility`
is validated against the schema
**THEN** validation SHALL pass

#### Scenario: Schema validation rejects missing fields

**WHEN** a finding without `axis` or `severity` is validated against the updated schema
**THEN** validation SHALL fail with a clear error identifying the missing field

#### Scenario: Existing schema fields preserved

**WHEN** the updated schema is loaded
**THEN** all pre-existing required fields SHALL remain required
**AND** all pre-existing enum values SHALL remain valid

#### Scenario: Schema copies stay identical

**WHEN** the canonical schema, the install-assets mirror, and the `agents.yaml` inline
copy are compared
**THEN** their `axis` and `severity` enums SHALL be identical

#### Scenario: test_quality finding validates

**WHEN** a finding with `type: "test_quality"`, `axis: "readability"`, `criticality: "low"`
is validated against the schema
**THEN** validation SHALL pass

#### Scenario: type enum identical across all copies

**WHEN** the canonical schema, the install-assets mirror, the consensus-report schema,
and `vendor_review.py`'s fallback enums are compared
**THEN** their `type` enums SHALL be identical and SHALL include `test_quality`

## ADDED Requirements

### Requirement: Autopilot SIMPLIFY Phase

`/autopilot` SHALL accept a `--simplify` flag. When present, the state machine SHALL run a
`SIMPLIFY` phase after implementation has stabilized and before `VALIDATE`: after
`IMPL_REVIEW` converges, or after `IMPL_ITERATE` completes when `--no-review` skipped
review. Both edges SHALL resolve through one dynamic transition target
(`SIMPLIFY_OR_VALIDATE`) so that the flag's absence leaves the existing edges unchanged.

The phase SHALL run the `simplify-implementation` skill over the change's diff in a managed
worktree, honoring that skill's phase order (characterize → prune → simplify) and its gates
(coverage gate, `check_test_prune.py`, `check_test_contract.py`, `check_scope.py`,
`verify_behavior_preservation.py`).

The phase SHALL be **soft**. Its outcomes SHALL be `complete`, `skipped`, and `failed`:

- `skipped` SHALL be reported, with a `skipped_reason`, when the Rule of 500 is exceeded,
  the surface cannot be pinned, the prune gate exits non-zero, the assertion contract
  exits non-zero, the dual-run exits non-zero, or there is nothing to simplify. On
  `skipped` after any production edit, the phase SHALL reset the branch to the post-prune
  baseline `B1` before transitioning. `skipped` SHALL transition to `VALIDATE`.
- `failed` SHALL be reserved for failure of the dispatch itself and SHALL transition to
  `ESCALATE`.
- `complete` SHALL transition to `VALIDATE`.

Commits produced by the phase SHALL be split by kind — `test(<scope>): pin …`,
`test(<scope>): remove …`, `refactor(<scope>): …` — and SHALL NOT be squashed together
by the phase.

`LoopState` SHALL gain `simplify_enabled: bool` (default `false`), `simplify_baselines`
(`{"b0": sha, "b1": sha}` or `null`), and `simplify_report_path` (`str` or `null`), bumping
`LOOP_STATE_SCHEMA_VERSION` to 6. Files written at schema version 5 SHALL load with the new
fields at their defaults and no other field changed.

The phase SHALL write `simplify-report.json` to `openspec/changes/<change-id>/` (passing
`--report` explicitly) and, whenever any test is removed, the prune ledger to
`openspec/changes/<change-id>/test-prune-ledger.md`.

`SIMPLIFY` SHALL be registered in every phase enumeration that gates dispatch or validation:
`TRANSITIONS`, `_HANDOFF_BOUNDARIES`, `phase_agent` worktree/signal/task tables,
`token_budget_check` dispatching phases, `audit_log_validator` phase model,
`agents_config.WRITE_CAPABLE_PHASES` and `NON_TERMINAL_PHASES`, `archetypes.yaml`
`phase_mapping`, and both copies of `convergence-state.schema.json`.

#### Scenario: Flag enables the phase

- **WHEN** `/autopilot <change-id> --simplify` is invoked
- **THEN** `loop-state.json` SHALL record `simplify_enabled: true`
- **AND** the transition from IMPL_REVIEW `converged` SHALL resolve to `SIMPLIFY`

#### Scenario: Flag absent leaves the edge unchanged

- **WHEN** `/autopilot <change-id>` is invoked without `--simplify`
- **THEN** the transition from IMPL_REVIEW `converged` SHALL resolve to `VALIDATE`
- **AND** the transition from IMPL_ITERATE `complete` under `--no-review` SHALL resolve to `VALIDATE`

#### Scenario: Rule of 500 exceeded is a skip, not a failure

- **GIVEN** `check_scope.py` exits 2 for the change's diff
- **WHEN** the SIMPLIFY phase runs
- **THEN** the phase outcome SHALL be `skipped` with `skipped_reason` naming the Rule of 500
- **AND** the next phase SHALL be `VALIDATE`
- **AND** no `refactor(...)` commit SHALL exist on the feature branch from this phase

#### Scenario: Dual-run failure reverts to the post-prune baseline

- **GIVEN** SIMPLIFY produced `refactor(...)` commits
- **AND** `verify_behavior_preservation.py --baseline <B1>` exits 2
- **WHEN** the phase concludes
- **THEN** the feature branch head SHALL equal `B1`
- **AND** the outcome SHALL be `skipped` with `skipped_reason: dual_run_failed`

#### Scenario: Prune commits are test-only and ledgered

- **GIVEN** SIMPLIFY removed at least one test
- **WHEN** the phase concludes with `complete`
- **THEN** `check_test_prune.py --base <B0> --head <B1> --ledger openspec/changes/<change-id>/test-prune-ledger.md` SHALL exit 0
- **AND** `check_test_contract.py --base <B1>` SHALL exit 0

#### Scenario: Schema v5 loop-state loads under v6

- **GIVEN** a `loop-state.json` written at schema version 5
- **WHEN** `load_state` reads it
- **THEN** `simplify_enabled` SHALL be `false`, `simplify_baselines` and `simplify_report_path` SHALL be `null`
- **AND** every pre-existing field SHALL be unchanged

#### Scenario: Resume mid-SIMPLIFY reconstructs the dual-run

- **GIVEN** the loop was interrupted during SIMPLIFY after characterization and prune commits
- **WHEN** the loop is re-invoked with the same change-id
- **THEN** the phase SHALL read `simplify_baselines.b1` from `loop-state.json`
- **AND** SHALL run the dual-run against that baseline rather than recomputing it from the current head

### Requirement: Autopilot SIMPLIFY Phase Evidence

Every SIMPLIFY run SHALL record, in its `phase_history` entry and in `simplify-report.json`,
the measurables a later default-on decision is judged against: `lines_removed`,
`files_touched`, `tests_pruned`, `seams_removed`, `dual_run_passed` (bool), and
`skipped_reason` (string or `null`). The autopilot Convergence Report SHALL include a
SIMPLIFY line carrying these counters when the phase ran.

#### Scenario: Counters present on every outcome

- **WHEN** SIMPLIFY concludes with any outcome
- **THEN** the `phase_history` entry SHALL contain all six fields
- **AND** on `skipped` the counters SHALL be `0`, `dual_run_passed` SHALL be `false`, and `skipped_reason` SHALL be non-null

#### Scenario: Report lands in the change directory

- **WHEN** SIMPLIFY reaches the dual-run step
- **THEN** `openspec/changes/<change-id>/simplify-report.json` SHALL exist
- **AND** `loop-state.json` `simplify_report_path` SHALL point at it

### Requirement: Implementation Review Test-Quality Findings

`parallel-review-implementation` SHALL include a **Test quality** checklist under its Code
Quality Review step that flags, as findings of `type: test_quality`, new or modified tests
matching the `simplify-implementation` Delete catalog (source-mirroring, change-detector,
self-mocking, duplicative, accessor-only, vacuous) and new production seams that exist only
for tests (mock-only interface, test-only constructor parameter, factory-of-one,
`_for_testing` hook). Such findings SHALL carry `criticality: low` and an `axis` of
`readability` (structure-coupled tests) or `correctness` (vacuous or self-mocking tests),
and SHALL cite the offending test or seam by path. They are read-only: the reviewer SHALL
NOT delete tests or seams. The targeted fix path MAY act on them like any other finding.

#### Scenario: Self-mocking test is flagged

- **GIVEN** a PR adds a test that mocks the unit under test and asserts the mock was called
- **WHEN** implementation review runs
- **THEN** the findings SHALL include a `test_quality` finding citing that test
- **AND** its `criticality` SHALL be `low` and its `axis` SHALL be `correctness`

#### Scenario: Test-quality findings do not block convergence alone

- **GIVEN** a review round whose only findings are `test_quality` at `criticality: low`
- **WHEN** the convergence loop evaluates blocking findings
- **THEN** the round SHALL converge

#### Scenario: Checklist present in the skill

- **WHEN** `parallel-review-implementation/SKILL.md` is read
- **THEN** it SHALL contain a Test quality checklist naming the Delete catalog smells and the seam patterns
- **AND** its Finding Types list SHALL include `test_quality`

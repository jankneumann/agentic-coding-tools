# skill-workflow — delta

## MODIFIED Requirements

### Requirement: State Machine Phases

The state machine SHALL support phases: INIT, PLAN, PLAN_REVIEW, PLAN_FIX, IMPLEMENT, IMPL_REVIEW, IMPL_FIX, SIMPLIFY_REVIEW (opt-in), SIMPLIFY_APPLY (opt-in), VALIDATE, VAL_REVIEW (optional), VAL_FIX, SUBMIT_PR, DONE, ESCALATE. The state machine SHALL persist its state to `loop-state.json` after every state transition, enabling resumability.

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

#### Scenario: Opt-in simplify phases after implementation review

- **GIVEN** autopilot was invoked with `--simplify`
- **WHEN** IMPL_REVIEW converges and the simplify review finds at least one applicable finding
- **THEN** phases SHALL progress: IMPL_REVIEW -> SIMPLIFY_REVIEW -> SIMPLIFY_APPLY -> VALIDATE
- **AND** VALIDATE SHALL run against the head produced by SIMPLIFY_APPLY

#### Scenario: Clean simplify review skips apply

- **GIVEN** autopilot was invoked with `--simplify`
- **WHEN** SIMPLIFY_REVIEW finds no finding with `disposition: fix`
- **THEN** phases SHALL progress: SIMPLIFY_REVIEW -> VALIDATE

#### Scenario: Simplify phases still run when review is skipped

- **GIVEN** autopilot was invoked with both `--simplify` and `--no-review`
- **WHEN** IMPL_ITERATE completes
- **THEN** the next phase SHALL be SIMPLIFY_REVIEW

#### Scenario: Default trace is unchanged without the flag

- **GIVEN** autopilot was invoked without `--simplify`
- **WHEN** the loop runs to completion
- **THEN** `phase_history` SHALL contain no SIMPLIFY_REVIEW or SIMPLIFY_APPLY entry
- **AND** the sequence of phases and outcomes SHALL equal the pre-change sequence for the same inputs

### Requirement: Per-Phase Archetype Resolution in Autopilot

The autopilot state machine SHALL resolve an archetype for every non-terminal phase before dispatching phase work, SHALL build a provider-neutral phase dispatch payload for sub-agent-capable phases, and SHALL apply the resolved archetype on the production execution path.

The resolution SHALL:

1. Be performed inside `skills/autopilot/scripts/phase_agent.py:_build_options(phase, state_dict)` or a compatibility wrapper that preserves that public behavior.
2. Extract per-phase signals from `state_dict` based on the `signals` field of the phase mapping.
3. Call the coordinator endpoint `POST /archetypes/resolve_for_phase` via `coordination_bridge.try_resolve_archetype_for_phase(phase, signals)`.
4. Resolve a logical archetype and model tier to a provider-specific model identifier for the selected provider.
5. Record the resolved archetype name in `state_dict["_resolved_archetype"]` for downstream use by `LoopState.phase_archetype`.

The 15 non-terminal phases SHALL be: `INIT`, `PLAN`, `PLAN_ITERATE`, `PLAN_REVIEW`, `PLAN_FIX`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `IMPL_FIX`, `SIMPLIFY_REVIEW`, `SIMPLIFY_APPLY`, `VALIDATE`, `VAL_REVIEW`, `VAL_FIX`, `SUBMIT_PR`. `SIMPLIFY_REVIEW` and `SIMPLIFY_APPLY` are opt-in and resolve by default to the `reviewer` and `implementer` archetypes respectively.

The `skills/autopilot/SKILL.md` orchestration prose SHALL dispatch the following 9 phases through the provider-neutral dispatch adapter when an adapter is available: `PLAN_ITERATE`, `PLAN_REVIEW`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `SIMPLIFY_REVIEW` (when enabled), `SIMPLIFY_APPLY` (when enabled), `VALIDATE`, `VAL_REVIEW` (when enabled). For these phases the dispatch SHALL pass the provider-specific model ID and SHALL fold the resolved `system_prompt` into the prompt text using the fixed separator `\n\n---\n\n`.

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

#### Scenario: Simplify phases resolve distinct archetypes

- **GIVEN** autopilot is running with `--simplify` under any configured provider
- **WHEN** autopilot enters `SIMPLIFY_REVIEW`
- **THEN** `phase_mapping.SIMPLIFY_REVIEW` SHALL resolve (default archetype `reviewer`)
- **WHEN** autopilot enters `SIMPLIFY_APPLY`
- **THEN** `phase_mapping.SIMPLIFY_APPLY` SHALL resolve (default archetype `implementer`)
- **AND** each phase SHALL be dispatched through the provider-neutral adapter with its own resolved model
- **AND** `LoopState.phase_archetype` SHALL record each resolution

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

#### Scenario: Simplify review writes only the artifact

- **WHEN** autopilot runs `SIMPLIFY_REVIEW`
- **THEN** the phase MUST run in a managed worktree or isolated harness checkout
- **AND** the only file it writes MUST be `openspec/changes/<change-id>/simplify-review.json`

#### Scenario: Simplify apply writes commits

- **WHEN** autopilot runs `SIMPLIFY_APPLY`
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

The skill SHALL perform **dual-run verification**: the selected test suite SHALL pass on the pre-simplify baseline tip and on the post-simplify tip. Primary invoke remains `/simplify-implementation`; invocation SHALL NOT be default-on in autopilot. An explicit `--simplify` flag on `/autopilot` is an operator request and SHALL enable the opt-in `SIMPLIFY_REVIEW` and `SIMPLIFY_APPLY` phases.

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
- **THEN** the orchestrator SHALL run `SIMPLIFY_REVIEW`
- **AND** the phases SHALL honor this requirement's coverage gate, assertion contract, and dual-run unchanged

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
- A `review_type` enum that includes `simplify`, for the simplify review artifact
- A `type` enum that includes `test_quality` (a test that asserts implementation rather
  than behavior, or a production seam that exists only for tests) and `simplification`
  (a behavior-preserving simplification candidate from the `simplify-implementation`
  catalog)

Both fields SHALL be required for new findings. Findings produced before this change
SHALL be migratable by setting `axis: "correctness"` and `severity: "fyi"` as defaults.
All copies of the schema (canonical, install-assets mirror, `agents.yaml` inline) SHALL
carry the identical enum. The `type` and `review_type` enums SHALL also be identical in
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

#### Scenario: Simplify findings validate

**WHEN** a finding with `type: "test_quality"` or `type: "simplification"`, `axis: "readability"`,
`criticality: "low"` is validated against the schema inside a `review_type: "simplify"` envelope
**THEN** validation SHALL pass

#### Scenario: type and review_type enums identical across all copies

**WHEN** the canonical schema, the install-assets mirror, the consensus-report schema,
and `vendor_review.py`'s fallback enums are compared
**THEN** their `type` and `review_type` enums SHALL be identical
**AND** SHALL include `test_quality`, `simplification`, and `simplify` respectively

### Requirement: Simplify Mechanical Helper Scripts

The `simplify-implementation` skill SHALL ship optional helper scripts under `skills/simplify-implementation/scripts/`:

| Script | Behavior |
|---|---|
| `check_scope.py` | Compares a git diff range to the Rule of 500 / 5-file limit; exits non-zero when exceeded unless `--allow-codemod` is set |
| `check_test_contract.py` | Examines a git diff for changes to assertion/expect bodies in test paths; exits non-zero when expectation bodies change |
| `verify_behavior_preservation.py` | Runs a configured test command at a baseline ref and at HEAD (or records dual-run results); writes a machine-readable report |
| `check_test_prune.py` | Verifies a prune range is test-only and every removed test is justified in the prune ledger; exits non-zero otherwise |
| `simplify_review.py` | `validate` checks a simplify review artifact against the contract and the canonical review-findings schema; `render-ledger` emits `test-prune-ledger.md` from the artifact's `test_quality` findings |

Scripts SHALL be invocable via `<skill-base-dir>/scripts/...` and MUST NOT require agent-coordinator. The skill remains valid when scripts are unavailable; Verification SHOULD recommend running them when git history is present.

#### Scenario: Scope check fails oversized manual diff

- **GIVEN** a diff touching more than 5 files or more than 500 lines
- **WHEN** `check_scope.py` runs without `--allow-codemod`
- **THEN** the process exits non-zero
- **AND** the message references Rule of 500

#### Scenario: Test contract check fails expectation edits

- **GIVEN** a diff that changes `assert result == 1` to `assert result == 2` in a test file
- **WHEN** `check_test_contract.py` runs on that diff
- **THEN** the process exits non-zero

#### Scenario: Ledger rendered from the artifact is accepted by the prune gate

- **GIVEN** a valid simplify review artifact with a `test_quality` finding of `disposition: fix`
- **AND** a prune range that removes exactly that test
- **WHEN** `simplify_review.py render-ledger` writes the ledger and `check_test_prune.py` runs with it
- **THEN** `check_test_prune.py` SHALL exit 0

#### Scenario: Invalid artifact is rejected

- **GIVEN** an artifact whose `change-detector` prune has `covered_by: null`
- **WHEN** `simplify_review.py validate` runs
- **THEN** the process SHALL exit non-zero and name the failing finding

## ADDED Requirements

### Requirement: Simplify Skill Review and Apply Roles

The `simplify-implementation` skill SHALL be structured as two roles sharing one artifact.
The **Review role** (workflow steps 0–4: scope, Chesterton's Fence, coverage-gate
decision, candidate list, Rule of 500) SHALL be read-only with respect to production and
test code, SHALL write only the simplify review artifact, and SHALL end by validating it.
The **Apply role** (steps 5–8) SHALL begin by validating the artifact, SHALL characterize
per each finding's `coverage.characterize`, SHALL render the prune ledger from the artifact
rather than writing it by hand, SHALL apply only findings with `disposition: fix`, and SHALL
NOT change any finding's `fence.verdict` or `disposition`. A finding the Apply role cannot
land SHALL be reported as skipped with a reason; a verdict it disagrees with SHALL be raised
to a human rather than overwritten. A manual invocation MAY perform both roles in one
session but SHALL write the artifact between them.

#### Scenario: Review role writes nothing but the artifact

- **WHEN** the Review role completes on a surface
- **THEN** `git status` SHALL show no change outside `simplify-review.json`
- **AND** `simplify_review.py validate` on that file SHALL exit 0

#### Scenario: Apply role cannot promote a kept fence

- **GIVEN** an artifact finding with `fence.verdict: keep` and `disposition: accept`
- **WHEN** the Apply role runs
- **THEN** the construct SHALL be unchanged on HEAD
- **AND** the report SHALL list the finding under `findings_kept`

#### Scenario: Skill documents both roles

- **WHEN** `simplify-implementation/SKILL.md` is read
- **THEN** it SHALL contain a Roles section defining Review and Apply, in that order
- **AND** the Workflow section SHALL mark which steps belong to which role

### Requirement: Simplify Review Artifact

The simplify review artifact SHALL be a review-findings document with `review_type: simplify`
conforming to `contracts/events/simplify-review.schema.json` (composed over the canonical
review-findings schema). The envelope SHALL carry `baseline_b0` and `scope`; each finding
SHALL carry `type` (`simplification` | `test_quality`), `pattern` (a catalog entry),
`fence` (verdict, rationale, evidence), `criticality: low`, and `disposition`; `test_quality`
findings with `disposition: fix` SHALL carry `prune.reason` and `file_path`, with a non-null
`prune.covered_by` whenever the reason is `change-detector`, `duplicative`, or
`unreviewed-snapshot`; seam findings SHALL carry `consumer.present` and
`consumer.specified`, and a non-empty value in either SHALL force `fence.verdict: keep`.
In autopilot the artifact SHALL live at `openspec/changes/<change-id>/simplify-review.json`.

#### Scenario: Valid fixture passes both schemas

- **WHEN** `contracts/fixtures/simplify-review.valid.json` is validated against the contract and the canonical review-findings schema
- **THEN** both validations SHALL pass

#### Scenario: Coverage-required prune without covered_by is rejected

- **WHEN** `contracts/fixtures/simplify-review.invalid.json` is validated against the contract
- **THEN** validation SHALL fail on the finding whose `prune.reason` is `change-detector` and `prune.covered_by` is null

#### Scenario: Specified consumer forces keep

- **GIVEN** a seam finding with `consumer.specified: ["<active-change-id>"]`
- **WHEN** the artifact is validated
- **THEN** `fence.verdict` SHALL be `keep` and `disposition` SHALL NOT be `fix`

### Requirement: Autopilot SIMPLIFY_REVIEW Phase

`/autopilot` SHALL accept a `--simplify` flag. When present, after `IMPL_REVIEW` converges,
or after `IMPL_ITERATE` completes when `--no-review` skipped review, the state machine SHALL
run `SIMPLIFY_REVIEW`. Both edges SHALL resolve through one dynamic target
(`SIMPLIFY_OR_VALIDATE`) so the flag's absence leaves the existing edges unchanged.

The phase SHALL dispatch the Review role of `simplify-implementation` over the change's
diff to the `reviewer` archetype, in a managed worktree, writing only
`openspec/changes/<change-id>/simplify-review.json`. When `IMPL_REVIEW` ran, its `test_quality`
findings SHALL be supplied to the reviewer as seeds. `LoopState.simplify_review_path` SHALL
record the artifact path and `simplify_baselines.b0` the pre-simplify tip.

Outcomes SHALL be `findings` (at least one finding with `disposition: fix`) → `SIMPLIFY_APPLY`;
`clean` → `VALIDATE`, with a recorded `skipped_reason` when the review was refused (Rule of
500 exceeded at review scope, nothing to do) or the artifact failed validation
(`invalid_review_artifact`); `failed` (dispatch failure) → `ESCALATE`.

#### Scenario: Flag enables the review phase

- **WHEN** `/autopilot <change-id> --simplify` is invoked
- **THEN** `loop-state.json` SHALL record `simplify_enabled: true`
- **AND** the transition from IMPL_REVIEW `converged` SHALL resolve to `SIMPLIFY_REVIEW`

#### Scenario: Flag absent leaves the edges unchanged

- **WHEN** `/autopilot <change-id>` is invoked without `--simplify`
- **THEN** the transition from IMPL_REVIEW `converged` SHALL resolve to `VALIDATE`
- **AND** the transition from IMPL_ITERATE `complete` under `--no-review` SHALL resolve to `VALIDATE`

#### Scenario: Invalid artifact is visible, not fatal

- **GIVEN** the reviewer wrote an artifact that fails `simplify_review.py validate`
- **WHEN** SIMPLIFY_REVIEW concludes
- **THEN** the outcome SHALL be `clean` with `skipped_reason: invalid_review_artifact`
- **AND** the next phase SHALL be `VALIDATE`

#### Scenario: IMPL_REVIEW test-quality findings seed the review

- **GIVEN** IMPL_REVIEW converged with two `test_quality` findings
- **WHEN** SIMPLIFY_REVIEW is dispatched
- **THEN** the dispatch prompt SHALL include those findings as seeds
- **AND** the artifact MAY refine, keep, or drop each with a recorded fence verdict

### Requirement: Autopilot SIMPLIFY_APPLY Phase

`SIMPLIFY_APPLY` SHALL dispatch the Apply role of `simplify-implementation` to the
`implementer` archetype in a managed worktree, consuming `simplify_review_path`. It SHALL
honor the skill's gates (coverage gate, `check_test_prune.py` on the rendered ledger,
`check_test_contract.py`, `check_scope.py`, `verify_behavior_preservation.py`) and SHALL
record `simplify_baselines.b1` (the tip after characterization and prune commits) before the
first production edit.

Outcomes SHALL be `complete` → `VALIDATE`; `skipped` → `VALIDATE`, with a `skipped_reason`,
for an unpinnable surface, a prune-gate, assertion-contract, or dual-run exit 2, or nothing
applicable, and with the feature branch reset to `B1` first whenever any production edit
exists; `failed` (dispatch failure) → `ESCALATE`. Commits SHALL be split by kind
(`test(<scope>): pin …`, `test(<scope>): remove …`, `refactor(<scope>): …`).
`simplify-report.json` SHALL be written to `openspec/changes/<change-id>/` via an explicit
`--report`, and `test-prune-ledger.md` SHALL be rendered there from the artifact.

`LoopState` SHALL gain `simplify_enabled: bool` (default `false`), `simplify_baselines`
(`{"b0": sha, "b1": sha}` or `null`), `simplify_review_path`, and `simplify_report_path`
(`str` or `null`), bumping `LOOP_STATE_SCHEMA_VERSION` to 6. Files written at version 5 SHALL
load with the new fields at their defaults and no other field changed.

Both phases SHALL be registered in every enumeration that gates dispatch or validation:
`TRANSITIONS`, `_HANDOFF_BOUNDARIES`, `phase_agent` worktree/signal/task tables,
`token_budget_check` dispatching phases, `audit_log_validator` phase model,
`agents_config.WRITE_CAPABLE_PHASES` and `NON_TERMINAL_PHASES`, `archetypes.yaml`
`phase_mapping`, `_PHASE_TO_REVIEW_TYPE` (`SIMPLIFY_REVIEW` → `simplify`), and both copies of
`convergence-state.schema.json`.

#### Scenario: Dual-run failure reverts to the post-prune baseline

- **GIVEN** SIMPLIFY_APPLY produced `refactor(...)` commits
- **AND** `verify_behavior_preservation.py --baseline <B1>` exits 2
- **WHEN** the phase concludes
- **THEN** the feature branch head SHALL equal `B1`
- **AND** the outcome SHALL be `skipped` with `skipped_reason: dual_run_failed`

#### Scenario: Prune commits match the reviewer's ledger

- **GIVEN** the artifact has two `test_quality` findings with `disposition: fix`
- **WHEN** SIMPLIFY_APPLY concludes with `complete`
- **THEN** `test-prune-ledger.md` SHALL contain exactly those two `removed:` entries
- **AND** `check_test_prune.py --base <B0> --head <B1> --ledger <that file>` SHALL exit 0
- **AND** `check_test_contract.py --base <B1>` SHALL exit 0

#### Scenario: Schema v5 loop-state loads under v6

- **GIVEN** a `loop-state.json` written at schema version 5
- **WHEN** `load_state` reads it
- **THEN** `simplify_enabled` SHALL be `false` and the three new path/baseline fields SHALL be `null`
- **AND** every pre-existing field SHALL be unchanged

#### Scenario: Resume at apply reconstructs the dual-run

- **GIVEN** the loop was interrupted during SIMPLIFY_APPLY after prune commits
- **WHEN** the loop is re-invoked with the same change-id
- **THEN** the phase SHALL read `simplify_review_path` and `simplify_baselines.b1` from `loop-state.json`
- **AND** SHALL run the dual-run against that baseline rather than recomputing it from the current head

### Requirement: Autopilot SIMPLIFY Evidence

Every `SIMPLIFY_REVIEW` and `SIMPLIFY_APPLY` run SHALL record, in its `phase_history` entry
and (for apply) in `simplify-report.json`, the measurables a later default-on decision is
judged against: `findings_reviewed`, `findings_applied`, `findings_kept`, `lines_removed`,
`files_touched`, `tests_pruned`, `seams_removed`, `dual_run_passed` (bool), and
`skipped_reason` (string or `null`). `seams_removed` SHALL be the count of applied findings
whose `pattern` is a Test-induced seam entry, not a self-reported number. The autopilot
Convergence Report SHALL include a SIMPLIFY line carrying these counters when the phases ran.

#### Scenario: Counters present on every outcome

- **WHEN** either simplify phase concludes with any outcome
- **THEN** the `phase_history` entry SHALL contain all nine fields
- **AND** on `clean` or `skipped` the change counters SHALL be `0`, `dual_run_passed` SHALL be `false`, and `skipped_reason` SHALL be non-null

#### Scenario: Report lands in the change directory

- **WHEN** SIMPLIFY_APPLY reaches the dual-run step
- **THEN** `openspec/changes/<change-id>/simplify-report.json` SHALL exist
- **AND** `loop-state.json` `simplify_report_path` SHALL point at it

### Requirement: Implementation Review Test-Quality Findings

`parallel-review-implementation` SHALL include a **Test quality** checklist under its Code
Quality Review step that flags, as findings of `type: test_quality`, new or modified tests
matching the `simplify-implementation` Delete catalog (source-mirroring, change-detector,
self-mocking, duplicative, accessor-only, vacuous) and new production seams that exist only
for tests (mock-only interface, test-only constructor parameter, factory-of-one,
`_for_testing` hook). Such findings SHALL carry `criticality: low` and an `axis` of
`readability` (structure-coupled tests and seams) or `correctness` (vacuous or self-mocking
tests), SHALL cite the offending test or seam by `file_path`, and SHALL be read-only: the
reviewer SHALL NOT delete tests or seams. They are the seed input to `SIMPLIFY_REVIEW`
when `--simplify` is set; the targeted fix path MAY act on them like any other finding.

#### Scenario: Self-mocking test is flagged

- **GIVEN** a PR adds a test that mocks the unit under test and asserts the mock was called
- **WHEN** implementation review runs
- **THEN** the findings SHALL include a `test_quality` finding citing that test by `file_path`
- **AND** its `criticality` SHALL be `low` and its `axis` SHALL be `correctness`

#### Scenario: Test-quality findings do not block convergence alone

- **GIVEN** a review round whose only findings are `test_quality` at `criticality: low`
- **WHEN** the convergence loop evaluates blocking findings
- **THEN** the round SHALL converge

#### Scenario: Checklist present in the skill

- **WHEN** `parallel-review-implementation/SKILL.md` is read
- **THEN** it SHALL contain a Test quality checklist naming the Delete catalog smells and the seam patterns
- **AND** its Finding Types list SHALL include `test_quality`

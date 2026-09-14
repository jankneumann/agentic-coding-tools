## ADDED Requirements

### Requirement: Gate-Time Review Ledger

The convergence loop SHALL persist findings to
`openspec/changes/<change-id>/.review-ledger/ledger.json` with statuses
`open`, `addressed`, `retired`, and `parked`. Each item SHALL have a stable
id that survives rounds. New consensus findings SHALL merge into an existing
id when the synthesizer match score meets the threshold or the fingerprint
matches.

#### Scenario: Same defect keeps its id

- **WHEN** round 2 synthesizes a finding that matches a round-1 ledger item
- **THEN** the ledger SHALL keep the same `id`
- **AND** SHALL update `last_seen_round` to 2

#### Scenario: Ledger created on first round

- **WHEN** `converge()` runs and `.review-ledger/` does not exist
- **THEN** the directory and `ledger.json` SHALL be created
- **AND** the loop SHALL NOT fail solely because the ledger was absent

### Requirement: Compact Before New Hunt

Before dispatching round N>1, the loop SHALL compact the ledger against
current `HEAD`: retire items whose file is gone or whose description tokens
no longer appear in the file (or line window); return `addressed` items to
`open` if tokens remain.

#### Scenario: Fixed finding is retired

- **GIVEN** an open finding whose description tokens no longer appear in
  `file_path`
- **WHEN** compact runs
- **THEN** the item status SHALL be `retired`

#### Scenario: Claimed fix that did not take reopens

- **GIVEN** an `addressed` finding whose tokens still appear in `file_path`
- **WHEN** compact runs
- **THEN** the item status SHALL be `open`

### Requirement: Delta Review After Round One

Round N>1 review prompts SHALL include open ledger items and the last-fix
diff, and SHALL forbid re-opening `retired` or `parked` items. Round N>1
SHALL NOT be a cold review of the whole artifact.

#### Scenario: Round 2 prompt carries the ledger

- **WHEN** `build_review_prompt` is called for round 2
- **THEN** the prompt SHALL contain the open ledger item descriptions
- **AND** SHALL contain the last-fix diff or an explicit empty-diff marker
- **AND** SHALL instruct the reviewer not to re-open retired or parked items

### Requirement: Parked Disagreement Does Not Abort

When consensus classifies a finding as `disagreement`, the loop SHALL set
that ledger item to `parked`, append it to
`openspec/changes/<change-id>/reviews/parked-disagreements.json`, and
continue with remaining blocking items. The loop SHALL NOT return
`reason="disagreement"`.

#### Scenario: Disagreement plus agreed blocking continues

- **GIVEN** one disagreement finding and one confirmed high deterministic
  finding
- **WHEN** the round's consensus is processed
- **THEN** `fix_callback` SHALL be invoked with the confirmed finding
- **AND** the disagreement SHALL be written to `parked-disagreements.json`
- **AND** `converge()` SHALL NOT return `reason="disagreement"`

#### Scenario: Only disagreement remaining is convergence with leftovers

- **GIVEN** the only remaining consensus findings are disagreements
- **WHEN** the exit condition is checked
- **THEN** the loop SHALL return `converged=True`
- **AND** `escalate_findings` SHALL contain the parked items

### Requirement: Scoped Fix Cluster

`fix_callback` SHALL receive only current blocking ledger items. Allowed
write paths SHALL be each item's `file_path` (plus the spec file when
`type` is `spec_gap`). The fix prompt SHALL forbid new architecture and
out-of-scope edits. Post-fix Layer A validation SHALL run before the next
vendor panel.

#### Scenario: Fix is scoped to cited files

- **GIVEN** a blocking finding with `file_path=src/api.py`
- **WHEN** `fix_callback` is invoked
- **THEN** the allowed-path list SHALL contain `src/api.py`
- **AND** SHALL NOT contain unrelated package paths

#### Scenario: Out of scope fix is rejected

- **GIVEN** a fix dispatch scoped to `src/api.py`
- **WHEN** the fix modifies `src/frontend/app.tsx`
- **THEN** the system SHALL reject the fix as a scope violation

## MODIFIED Requirements

### Requirement: Review Convergence Loop

The convergence loop SHALL dispatch reviews to all available vendors via
`ReviewOrchestrator.dispatch_and_wait()`, merge results into the gate-time
ledger, compact before round N>1, synthesize findings via
`ConsensusSynthesizer.synthesize()`, and exit when no blocking ledger items
remain AND quorum is met. Blocking means `deterministic` open items, or
`confirmed` open items with criticality `high` or `critical`. Unconfirmed
medium items SHALL NOT block. The loop SHALL enforce a maximum iteration
cap (default 3 rounds per phase). PLAN_FIX and IMPL_FIX SHALL run as the
loop's `fix_callback`, not as an outer state machine that re-dispatches a
cold review.

#### Scenario: Multi-vendor review dispatch

- **GIVEN** 3 vendors are available (claude, codex, grok)
- **WHEN** a convergence review round begins
- **THEN** the system SHALL dispatch review requests to all 3 vendors

#### Scenario: Convergence achieved with quorum

- **GIVEN** compact leaves 0 blocking ledger items
- **AND** at least 2 vendors returned valid results
- **WHEN** the exit condition is checked
- **THEN** convergence SHALL be declared and the loop SHALL advance to the
  next phase

#### Scenario: Unconfirmed medium does not block

- **GIVEN** a single-vendor medium-severity judgment finding
- **WHEN** the exit condition is checked
- **THEN** the finding SHALL NOT block convergence
- **AND** `fix_callback` SHALL NOT receive it

#### Scenario: Convergence blocked by insufficient quorum

- **GIVEN** only 1 vendor returned valid results with 0 findings
- **WHEN** the exit condition is checked
- **THEN** convergence SHALL NOT be declared
- **AND** the system SHALL pause with reason "quorum_lost"

#### Scenario: Max iterations reached

- **GIVEN** the plan review has run 3 rounds without zero blocking items
- **WHEN** the 3rd round completes with remaining blocking items
- **THEN** the system SHALL transition to ESCALATE state

### Requirement: Finding Trend Tracking and Stall Detection

The convergence loop SHALL track **post-compact blocking** counts per round
and escalate if the count is not strictly decreasing versus the previous
round. Unconfirmed medium findings SHALL NOT block in any round.
Disagreement SHALL park rather than stall or abort.

#### Scenario: Decreasing blocking continues

- **GIVEN** round 1 has 4 blocking items and round 2 has 2
- **WHEN** trend analysis runs after round 2
- **THEN** the system SHALL NOT escalate

#### Scenario: Non-decreasing blocking stalls

- **GIVEN** round 1 has 3 blocking items and round 2 has 3
- **WHEN** trend analysis runs after round 2
- **THEN** the system SHALL escalate with reason `stalled`

#### Scenario: Decreasing trend continues (no stall)

- **GIVEN** round 1 has 10 blocking findings, round 2 has 5, and round 3 has 3
- **WHEN** trend analysis runs after round 3
- **THEN** the system SHALL NOT escalate because post-compact blocking is strictly decreasing

#### Scenario: Flat trend triggers stall

- **GIVEN** round 1 has 5 blocking findings, round 2 has 5, and round 3 has 5
- **WHEN** trend analysis runs after round 3
- **THEN** the system SHALL escalate because post-compact blocking is not strictly decreasing

#### Scenario: Unconfirmed finding in final round

- **GIVEN** a single-vendor medium-severity judgment finding in round 3 (final round)
- **WHEN** the exit condition is checked
- **THEN** the finding SHALL NOT block convergence

#### Scenario: Vendor disagreement

- **GIVEN** claude recommends "fix" and codex recommends "accept" for the same finding
- **WHEN** consensus synthesis classifies this as "disagreement"
- **THEN** the finding SHALL be parked rather than aborting the loop

### Requirement: Disagreement Classification

When vendors disagree on disposition (e.g., `fix` vs `accept`), the finding
SHALL be classified as `disagreement` in the consensus report and **parked**
on the ledger. Parking SHALL NOT abort the convergence loop.

#### Scenario: Vendors disagree on disposition

- **GIVEN** Codex says disposition=`fix` and grok says disposition=`accept`
  for matched findings
- **WHEN** consensus is computed
- **THEN** the finding status is `disagreement`
- **AND** the recommended disposition is `escalate`
- **AND** the ledger item status is `parked`

### Requirement: Disagreement Findings Escalate

`Disagreement` findings SHALL be parked for human review. At SUBMIT_PR, if
parked items remain, the merge-authorization path MAY surface them as
`BLOCKED_ESCALATE`. Mid-loop `converge()` SHALL NOT stop solely because a
disagreement exists.

#### Scenario: Disagreement finding is parked not a loop abort

- **GIVEN** a consensus report with a disagreement finding and no blocking
  items
- **WHEN** the convergence exit condition is checked
- **THEN** the loop SHALL return converged with parked leftovers
- **AND** `parked-disagreements.json` SHALL contain the finding

#### Scenario: Disagreement finding escalates

- **GIVEN** a consensus report with a disagreement finding
- **WHEN** the integration gate checks at SUBMIT_PR
- **THEN** the gate MAY return BLOCKED_ESCALATE for parked leftovers
- **AND** mid-loop `converge()` SHALL NOT abort solely because a disagreement exists

### Requirement: State Machine Phases

The state machine SHALL support phases: INIT, PLAN, PLAN_REVIEW, PLAN_FIX,
IMPLEMENT, IMPL_REVIEW, IMPL_FIX, VALIDATE, VAL_REVIEW (optional), VAL_FIX,
SUBMIT_PR, DONE, ESCALATE. PLAN_FIX and IMPL_FIX SHALL be recorded as
fix-steps of the surrounding review phase (observability in `phase_history`)
and SHALL NOT re-enter PLAN_REVIEW or IMPL_REVIEW as a cold multi-vendor
review of the whole artifact. The state machine SHALL persist its state to
`loop-state.json` after every state transition, enabling resumability.

#### Scenario: Plan review with fixes stays in one engine

- **GIVEN** a feature where plan review finds blocking issues
- **WHEN** the loop processes plan review
- **THEN** `converge()` SHALL apply fixes via `fix_callback` and re-review
  as compact+delta inside the same PLAN_REVIEW phase
- **AND** the outer machine SHALL NOT bounce PLAN_REVIEW → PLAN_FIX →
  PLAN_REVIEW as a second engine

#### Scenario: Normal phase progression (simple feature)

- **GIVEN** a simple feature with no review findings and no complexity checkpoints
- **WHEN** the loop runs to completion
- **THEN** phases SHALL progress: INIT -> PLAN -> PLAN_REVIEW -> IMPLEMENT -> IMPL_REVIEW -> VALIDATE -> SUBMIT_PR -> DONE

#### Scenario: Phase progression with fixes needed

- **GIVEN** a feature where plan review finds medium-severity issues
- **WHEN** the loop processes plan review
- **THEN** `converge()` SHALL apply fixes via `fix_callback` inside PLAN_REVIEW
- **AND** the outer machine SHALL NOT bounce PLAN_REVIEW -> PLAN_FIX -> PLAN_REVIEW as a second engine

#### Scenario: Complex feature with VAL_REVIEW

- **GIVEN** a feature that triggered complexity gate checkpoints (e.g., database migrations)
- **WHEN** validation passes
- **THEN** phases SHALL include VAL_REVIEW before SUBMIT_PR

#### Scenario: Resume after interruption

- **GIVEN** the loop was interrupted during IMPL_REVIEW phase at iteration 2
- **WHEN** the loop is re-invoked with the same change-id
- **THEN** the system SHALL load state from `loop-state.json` and resume from
  IMPL_REVIEW iteration 2

### Requirement: Fix Dispatch

Fix dispatch SHALL differ by phase:

- **PLAN_FIX**: The conductor SHALL apply fixes **inline** (directly editing
  plan artifacts) since it already has full context. No CLI subprocess
  dispatch. Allowed paths SHALL be the blocking items' `file_path`s.
- **IMPL_FIX**: Fixes SHALL be dispatched to the **recorded lead vendor**
  for the package (stored in `LoopState.package_authors`), scoped to the
  intersection of the package's `write_allow` paths and the finding
  `file_path`s. Post-fix verification SHALL reject edits outside that
  intersection.
- **VAL_FIX**: Fixes SHALL be applied inline for configuration/test changes,
  or targeted to the relevant package's author for code changes.

The fix prompt SHALL forbid adding architecture and expanding scope.

#### Scenario: Plan fix applied inline

- **GIVEN** plan review found 2 confirmed-high findings in design.md
- **WHEN** fix dispatch runs
- **THEN** the conductor SHALL edit design.md directly and re-validate with
  `openspec validate`

#### Scenario: Implementation fix targeted to lead vendor

- **GIVEN** implementation review found a blocking finding in wp-api
  authored by codex
- **WHEN** fix dispatch runs
- **THEN** the system SHALL dispatch the fix to codex in alternative mode,
  scoped to the intersection of wp-api's write_allow and the finding
  `file_path`

#### Scenario: Fix scope enforcement

- **GIVEN** a fix dispatch to wp-api with write_allow of `["src/api/**"]`
- **WHEN** the fix modifies `src/frontend/app.tsx`
- **THEN** the system SHALL reject the fix as a scope violation

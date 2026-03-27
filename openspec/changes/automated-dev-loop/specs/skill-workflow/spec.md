# Spec Delta: skill-workflow — Automated Development Loop

## ADDED Requirements

### Requirement: Auto Dev Loop Skill

The system SHALL provide an `/auto-dev-loop` skill that orchestrates the full plan-review-implement-validate-PR lifecycle as a state machine. The skill SHALL accept either a `change-id` (existing proposal) or a feature description (creates proposal first via `/parallel-plan-feature` or `/linear-plan-feature`).

#### Scenario: Invoke with existing change-id

- **WHEN** the user invokes `/auto-dev-loop test-feature`
- **THEN** the system SHALL load the proposal artifacts and begin the state machine at INIT phase

#### Scenario: Invoke with feature description

- **WHEN** the user invokes `/auto-dev-loop "add user authentication"`
- **THEN** the system SHALL delegate to `/parallel-plan-feature` (or `/linear-plan-feature` if coordinator unavailable) to create proposal artifacts
- **AND** transition to PLAN_REVIEW once artifacts exist

### Requirement: State Machine Phases

The state machine SHALL support phases: INIT, PLAN, PLAN_REVIEW, PLAN_FIX, IMPLEMENT, IMPL_REVIEW, IMPL_FIX, VALIDATE, VAL_REVIEW (optional), VAL_FIX, SUBMIT_PR, DONE, ESCALATE. The state machine SHALL persist its state to `loop-state.json` after every state transition, enabling resumability.

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

### Requirement: Review Convergence Loop

The convergence loop SHALL dispatch reviews to all available vendors via `ReviewOrchestrator.dispatch_and_wait()`, synthesize findings via `ConsensusSynthesizer.synthesize()`, and exit when no confirmed or unconfirmed findings at medium or higher severity remain AND quorum is met. The loop SHALL enforce a maximum iteration cap (default 3 rounds per phase).

#### Scenario: Multi-vendor review dispatch

- **GIVEN** 3 vendors are available (claude, codex, gemini)
- **WHEN** a convergence review round begins
- **THEN** the system SHALL dispatch review requests to all 3 vendors

#### Scenario: Convergence achieved with quorum

- **GIVEN** consensus shows 3 low-severity findings and 0 medium+ findings
- **AND** at least 2 vendors returned valid results
- **WHEN** the exit condition is checked
- **THEN** convergence SHALL be declared and the loop SHALL advance to the next phase

#### Scenario: Convergence blocked by insufficient quorum

- **GIVEN** only 1 vendor returned valid results with 0 findings
- **WHEN** the exit condition is checked
- **THEN** convergence SHALL NOT be declared
- **AND** the system SHALL pause with reason "quorum_lost"

#### Scenario: Max iterations reached

- **GIVEN** the plan review has run 3 rounds without convergence
- **WHEN** the 3rd round completes with remaining medium+ findings
- **THEN** the system SHALL transition to ESCALATE state

### Requirement: Finding Trend Tracking and Stall Detection

The convergence loop SHALL track finding counts per round and escalate if findings are not decreasing over a 3-round sliding window (i.e., count at round N >= count at round N-2). Unconfirmed findings (single-vendor, medium+) SHALL block in rounds 1 through N-1 but SHALL NOT block in the final round. Findings with `disagreement` status SHALL always trigger escalation.

#### Scenario: Stalled convergence (3-point window)

- **GIVEN** round 1 has 10 blocking findings, round 2 has 5, and round 3 has 6
- **WHEN** trend analysis runs after round 3
- **THEN** the system SHALL escalate because round 3 count (6) >= round 1 count (10) is false, so it continues
- **BUT** if round 1=5, round 2=5, round 3=5, the system SHALL escalate because round 3 (5) >= round 1 (5)

#### Scenario: Unconfirmed finding in final round

- **GIVEN** a single-vendor medium-severity finding in round 3 (final round)
- **WHEN** the exit condition is checked
- **THEN** the finding SHALL NOT block convergence

#### Scenario: Vendor disagreement

- **GIVEN** claude recommends "fix" and codex recommends "accept" for the same finding
- **WHEN** consensus synthesis classifies this as "disagreement"
- **THEN** the system SHALL transition to ESCALATE state

### Requirement: Fix Dispatch

Fix dispatch SHALL differ by phase:
- **PLAN_FIX**: The conductor SHALL apply fixes **inline** (directly editing plan artifacts) since it already has full context. No CLI subprocess dispatch.
- **IMPL_FIX**: Fixes SHALL be dispatched to the **recorded lead vendor** for the package (stored in `LoopState.package_authors`), scoped to the package's `write_allow` paths. Post-fix verification SHALL reject edits outside declared scope.
- **VAL_FIX**: Fixes SHALL be applied inline for configuration/test changes, or targeted to the relevant package's author for code changes.

#### Scenario: Plan fix applied inline

- **GIVEN** plan review found 2 medium-severity confirmed findings in design.md
- **WHEN** fix dispatch runs
- **THEN** the conductor SHALL edit design.md directly and re-validate with `openspec validate`

#### Scenario: Implementation fix targeted to lead vendor

- **GIVEN** implementation review found a medium-severity finding in wp-api authored by codex
- **WHEN** fix dispatch runs
- **THEN** the system SHALL dispatch the fix to codex in alternative mode, scoped to wp-api's write_allow paths

#### Scenario: Fix scope enforcement

- **GIVEN** a fix dispatch to wp-api with write_allow of `["src/api/**"]`
- **WHEN** the fix modifies `src/frontend/app.tsx`
- **THEN** the system SHALL reject the fix as a scope violation

### Requirement: Implementation Strategy Selection

The system SHALL select an implementation strategy per work package: `alternatives` (3 independent implementations + synthesis) or `lead_review` (1 implements + others review). Selection SHALL consume structured metadata from `work-packages.yaml` (`metadata.loc_estimate`, `metadata.alternatives_count`, `metadata.package_kind`) when available, falling back to description inference.

#### Scenario: Small ambiguous package with metadata

- **GIVEN** a package with metadata `loc_estimate: 100, alternatives_count: 3, package_kind: algorithm`
- **WHEN** strategy selection runs with 3 vendors available
- **THEN** the strategy SHALL be "alternatives"

#### Scenario: Large straightforward package

- **GIVEN** a package with metadata `loc_estimate: 400, alternatives_count: 0, package_kind: crud`
- **WHEN** strategy selection runs
- **THEN** the strategy SHALL be "lead_review"

#### Scenario: Fallback when metadata absent

- **GIVEN** a package without metadata fields
- **WHEN** strategy selection runs
- **THEN** the strategy SHALL default to "lead_review"

### Requirement: Complexity Gate

The system SHALL assess feature complexity at INIT phase. Thresholds SHALL be configurable via `work-packages.yaml` defaults (`defaults.auto_loop.max_loc`, etc.) with built-in defaults (LOC > 500, packages > 4, external deps > 2). Features exceeding thresholds SHALL require `--force` or inject manual review checkpoints (including enabling VAL_REVIEW). Features touching database migrations or security-sensitive paths SHALL inject checkpoints regardless.

#### Scenario: Simple feature passes

- **GIVEN** a feature with 200 LOC, 2 packages, 0 external deps
- **WHEN** complexity gate runs
- **THEN** the gate SHALL pass without warnings and VAL_REVIEW SHALL be skipped

#### Scenario: Complex feature with checkpoints

- **GIVEN** a feature with 800 LOC and 6 packages without --force
- **WHEN** complexity gate runs
- **THEN** the gate SHALL reject with a warning listing exceeded thresholds

#### Scenario: Database migration enables VAL_REVIEW

- **GIVEN** a feature with 200 LOC but includes a database migration
- **WHEN** complexity gate runs
- **THEN** the gate SHALL pass but inject VAL_REVIEW as a checkpoint

#### Scenario: Custom thresholds from work-packages.yaml

- **GIVEN** work-packages.yaml contains `defaults.auto_loop.max_loc: 1000`
- **WHEN** complexity gate evaluates a 700 LOC feature
- **THEN** the gate SHALL pass (below custom threshold)

### Requirement: Memory and Handoff Integration

The system SHALL write coordinator episodic memory (via `remember(event_type, summary, details, tags)`) at each convergence round, storing the returned `memory_id` in `LoopState.memory_ids`. The system SHALL write handoff documents at each major state transition. At completion, the system SHALL write strategic memory summarizing vendor effectiveness and convergence patterns.

#### Scenario: Episodic memory at convergence round

- **GIVEN** a convergence round completes with 3 findings and 75% vendor agreement
- **WHEN** the round ends
- **THEN** a memory entry SHALL be written with event_type="convergence_round" and tags including the change-id and phase

#### Scenario: Handoff at phase boundary

- **GIVEN** plan review converges
- **WHEN** transitioning to IMPLEMENT
- **THEN** a handoff document SHALL be written with summary, decisions, and implementation context

#### Scenario: Strategic memory at completion

- **GIVEN** the loop completes successfully
- **WHEN** entering DONE state
- **THEN** a memory entry SHALL be written with event_type="loop_completion" including vendor effectiveness stats

### Requirement: ESCALATE Resolution Protocol

When entering ESCALATE, the system SHALL persist `previous_phase` and `escalation_reason` in `LoopState`, write a diagnostic handoff, and exit. On re-invocation, the system SHALL detect ESCALATE state, re-evaluate the escalation condition, and transition to `previous_phase` if resolved.

#### Scenario: Escalation and resume

- **GIVEN** the loop escalated during IMPL_REVIEW due to vendor disagreement
- **AND** the human manually resolved the disagreement
- **WHEN** the human re-invokes `/auto-dev-loop <change-id>`
- **THEN** the system SHALL load state, detect ESCALATE, re-run IMPL_REVIEW gate check
- **AND** transition to IMPL_REVIEW if the disagreement is resolved

#### Scenario: Escalation not yet resolved

- **GIVEN** the loop escalated and the human re-invokes without fixing the issue
- **WHEN** the system re-evaluates the escalation condition
- **THEN** the system SHALL remain in ESCALATE with updated diagnostic

### Requirement: Graceful Degradation

If coordinator unavailable, the system SHALL fall back to linear workflow. If a vendor drops mid-loop, the system SHALL continue with reduced quorum (minimum 2 for convergence). If quorum drops below 2, the system SHALL pause with reason "quorum_lost" and alert.

#### Scenario: No coordinator

- **GIVEN** coordinator health check returns unavailable
- **WHEN** `/auto-dev-loop` is invoked
- **THEN** the system SHALL emit a warning and delegate to sequential skill invocation

#### Scenario: Vendor drops mid-loop

- **GIVEN** 3 vendors at PLAN_REVIEW but only 2 at IMPL_REVIEW
- **WHEN** the convergence loop dispatches reviews
- **THEN** the system SHALL continue with 2-vendor quorum and log a warning

### Requirement: Convergence State Schema

The convergence state SHALL conform to `convergence-state.schema.json` including: current_phase, iteration, max_iterations, findings_trend, blocking_findings, vendor_availability, packages_status, package_authors, implementation_strategy, memory_ids, handoff_ids, timestamps, previous_phase, escalation_reason, and error.

#### Scenario: State validates

- **GIVEN** a loop-state.json file produced by the state machine
- **WHEN** validated against convergence-state.schema.json
- **THEN** validation SHALL pass

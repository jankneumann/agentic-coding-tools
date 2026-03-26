# Spec Delta: skill-workflow — Automated Development Loop

## ADDED Requirements

### Requirement: Auto Dev Loop Skill

The system SHALL provide an `/auto-dev-loop` skill that orchestrates the full plan-review-implement-validate-PR lifecycle as a state machine. The skill SHALL accept either a `change-id` (existing proposal) or a feature description (creates proposal first).

#### Scenario: Invoke with existing change-id

- **WHEN** the user invokes `/auto-dev-loop test-feature`
- **THEN** the system SHALL load the proposal artifacts and begin the state machine at INIT phase

#### Scenario: Invoke with feature description

- **WHEN** the user invokes `/auto-dev-loop "add user authentication"`
- **THEN** the system SHALL create a new proposal from the description before entering the state machine

### Requirement: State Machine Phases

The state machine SHALL support phases: INIT, PLAN_REVIEW, PLAN_FIX, IMPLEMENT, IMPL_REVIEW, IMPL_FIX, VALIDATE, VAL_FIX, SUBMIT_PR, DONE, ESCALATE. The state machine SHALL persist its state to `loop-state.json` after every state transition, enabling resumability.

#### Scenario: Normal phase progression

- **GIVEN** a simple feature with no review findings
- **WHEN** the loop runs to completion
- **THEN** phases SHALL progress: INIT -> PLAN_REVIEW -> IMPLEMENT -> IMPL_REVIEW -> VALIDATE -> SUBMIT_PR -> DONE

#### Scenario: Phase progression with fixes needed

- **GIVEN** a feature where plan review finds medium-severity issues
- **WHEN** the loop processes plan review
- **THEN** phases SHALL progress: PLAN_REVIEW -> PLAN_FIX -> PLAN_REVIEW (re-review)

#### Scenario: Resume after interruption

- **GIVEN** the loop was interrupted during IMPL_REVIEW phase at iteration 2
- **WHEN** the loop is re-invoked with the same change-id
- **THEN** the system SHALL load state from `loop-state.json` and resume from IMPL_REVIEW iteration 2

### Requirement: Review Convergence Loop

The convergence loop SHALL dispatch reviews to all available vendors via `review_dispatcher.dispatch_and_wait()`, synthesize findings via `consensus_synthesizer.synthesize()`, and exit when no confirmed or unconfirmed findings at medium or higher severity remain. The loop SHALL enforce a maximum iteration cap (default 3 rounds per phase).

#### Scenario: Multi-vendor review dispatch

- **GIVEN** 3 vendors are available (claude, codex, gemini)
- **WHEN** a convergence review round begins
- **THEN** the system SHALL dispatch review requests to all 3 vendors

#### Scenario: Convergence achieved

- **GIVEN** consensus shows 3 low-severity findings and 0 medium+ findings
- **WHEN** the exit condition is checked
- **THEN** convergence SHALL be declared and the loop SHALL advance to the next phase

#### Scenario: Max iterations reached

- **GIVEN** the plan review has run 3 rounds without convergence
- **WHEN** the 3rd round completes with remaining medium+ findings
- **THEN** the system SHALL transition to ESCALATE state

### Requirement: Finding Trend Tracking and Stall Detection

The convergence loop SHALL track finding counts per round and escalate if findings are not decreasing over 2 consecutive rounds. Unconfirmed findings (single-vendor, medium+) SHALL block in rounds 1-2 but SHALL NOT block in round 3. Findings with `disagreement` status SHALL always trigger escalation.

#### Scenario: Stalled convergence

- **GIVEN** round 1 has 5 blocking findings and round 2 has 6 blocking findings
- **WHEN** trend analysis runs after round 2
- **THEN** the system SHALL escalate due to non-decreasing trend

#### Scenario: Unconfirmed finding in final round

- **GIVEN** a single-vendor medium-severity finding in round 3 (final round)
- **WHEN** the exit condition is checked
- **THEN** the finding SHALL NOT block convergence

#### Scenario: Vendor disagreement

- **GIVEN** claude recommends "fix" and codex recommends "accept" for the same finding
- **WHEN** consensus synthesis classifies this as "disagreement"
- **THEN** the system SHALL transition to ESCALATE state

### Requirement: Fix Dispatch

When convergence has not been reached, the system SHALL dispatch fixes to the authoring agent using `alternative` dispatch mode, including the original artifact, review context, and specific finding descriptions with suggested resolutions. After fixes, the system SHALL re-validate artifacts before re-entering the review loop.

#### Scenario: Fix dispatch after review

- **GIVEN** plan review found 2 medium-severity confirmed findings
- **WHEN** fix dispatch runs
- **THEN** the system SHALL send findings to the authoring agent in alternative mode

#### Scenario: Post-fix re-validation

- **GIVEN** fixes have been applied
- **WHEN** re-validation runs
- **THEN** the system SHALL verify artifacts pass schema validation before re-entering review

### Requirement: Implementation Strategy Selection

The system SHALL select an implementation strategy per work package: `alternatives` (3 independent implementations + synthesis) or `lead_review` (1 implements + others review). Selection SHALL consider LOC estimate, design alternatives count, package type, and available vendor count.

#### Scenario: Small ambiguous package

- **GIVEN** a package with LOC estimate 100 and 3 design alternatives
- **WHEN** strategy selection runs with 3 vendors available
- **THEN** the strategy SHALL be "alternatives"

#### Scenario: Large straightforward package

- **GIVEN** a package with LOC estimate 400 and 0 design alternatives
- **WHEN** strategy selection runs
- **THEN** the strategy SHALL be "lead_review"

### Requirement: Complexity Gate

The system SHALL assess feature complexity at INIT phase. Features exceeding thresholds (LOC > 500, packages > 4, external deps > 2) SHALL require `--force` or inject manual review checkpoints. Features touching database migrations or security-sensitive paths SHALL inject checkpoints regardless.

#### Scenario: Simple feature passes

- **GIVEN** a feature with 200 LOC, 2 packages, 0 external deps
- **WHEN** complexity gate runs
- **THEN** the gate SHALL pass without warnings

#### Scenario: Complex feature rejected

- **GIVEN** a feature with 800 LOC and 6 packages without --force
- **WHEN** complexity gate runs
- **THEN** the gate SHALL reject with a warning listing exceeded thresholds

### Requirement: Memory and Handoff Integration

The system SHALL write coordinator memory at each convergence round and handoff documents at each major state transition. At completion, the system SHALL write strategic memory summarizing vendor effectiveness and convergence patterns.

#### Scenario: Memory at convergence round

- **GIVEN** a convergence round completes with 3 findings and 75% vendor agreement
- **WHEN** the round ends
- **THEN** a memory entry SHALL be written with key pattern "convergence:{change-id}:{phase}:round-{n}"

#### Scenario: Handoff at phase boundary

- **GIVEN** plan review converges
- **WHEN** transitioning to IMPLEMENT
- **THEN** a handoff document SHALL be written with summary, decisions, and implementation context

### Requirement: Graceful Degradation

If coordinator unavailable, the system SHALL fall back to linear workflow. If a vendor drops mid-loop, the system SHALL continue with reduced quorum (minimum 2 for convergence). If quorum drops below 2, the system SHALL pause and alert.

#### Scenario: No coordinator

- **GIVEN** coordinator health check returns unavailable
- **WHEN** `/auto-dev-loop` is invoked
- **THEN** the system SHALL emit a warning and delegate to sequential skill invocation

#### Scenario: Vendor drops mid-loop

- **GIVEN** 3 vendors at PLAN_REVIEW but only 2 at IMPL_REVIEW
- **WHEN** the convergence loop dispatches reviews
- **THEN** the system SHALL continue with 2-vendor quorum and log a warning

### Requirement: Convergence State Schema

The convergence state SHALL conform to `convergence-state.schema.json` including: current_phase, iteration, max_iterations, findings_trend, blocking_findings, vendor_availability, packages_status, implementation_strategy, memory_keys, handoff_ids, timestamps, and error.

#### Scenario: State validates

- **GIVEN** a loop-state.json file produced by the state machine
- **WHEN** validated against convergence-state.schema.json
- **THEN** validation SHALL pass

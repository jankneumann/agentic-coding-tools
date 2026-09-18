## ADDED Requirements

### Requirement: Phase Outcome Shadow Adjudication

`phase_agent.apply_phase_outcome` SHALL, on every non-replay call, attempt a
second, calibrated adjudication of the claimed phase outcome using whichever
of the following signals are available: `expected_outcomes` (from
`_expected_outcomes_for_phase`), a `git diff --stat` of the phase's worktree,
the tail of any recorded test output, and the local-fallback handoff record
for that phase when one exists.

The claimed outcome recorded to `state["phase_history"]` and every field
`transition()` reads SHALL be unaffected by this adjudication, for every
call, whether or not the adjudication is available.

#### Scenario: A shadow record per phase transition appends claimed and judged outcomes with the evidence Noul

- **GIVEN** a non-replay `apply_phase_outcome` call with at least one
  available signal
- **WHEN** the call completes
- **THEN** exactly one `"PHASE_OUTCOME_SHADOW"` entry is appended to
  `state["phase_history"]` carrying the claimed outcome, the judged
  `Choice` outcome, its distribution, and the evidence `Noul` answer

#### Scenario: transition() runs on the claimed outcome unchanged

- **GIVEN** a shadow adjudication whose judged outcome differs from the
  claimed outcome
- **WHEN** `transition(state, outcome)` is subsequently called with the
  claimed outcome
- **THEN** it returns the same next phase it would have returned had the
  shadow adjudication never run

#### Scenario: The adjudication degrades silently on unavailability

- **GIVEN** `system_one_decisions` is not installed, `decide()` returns
  `None`, or every one of `expected_outcomes`, the diff stat, the test
  output tail, and the handoff record is unavailable
- **WHEN** `apply_phase_outcome` runs
- **THEN** no `"PHASE_OUTCOME_SHADOW"` entry is appended, and the claimed
  outcome and existing `phase_history` entry are recorded exactly as they
  are today; this degradation SHALL NOT be recorded via `record_degraded`,
  which marks a different, unrelated acting-decision signal

#### Scenario: A replayed apply-outcome call does not duplicate the shadow entry

- **GIVEN** `apply_phase_outcome` is called twice with the same
  `handoff_id` for the same phase (a retried `apply-outcome` invocation)
- **WHEN** the second call is recognized as a replay
- **THEN** no additional `decide()` call is made and no second
  `"PHASE_OUTCOME_SHADOW"` entry is appended

#### Scenario: Disagreement attribution is exercised against a fixture shadow period

- **GIVEN** a constructed set of `"PHASE_OUTCOME_SHADOW"` entries and a
  caller-supplied mapping of which claimed outcomes a later review round
  found wrong
- **WHEN** `attribute_disagreements` is run over them
- **THEN** it reports, for each disagreement, which side — claimed or
  judged — the review round vindicated

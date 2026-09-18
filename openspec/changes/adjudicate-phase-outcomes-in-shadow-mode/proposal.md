# Adjudicate phase outcomes in shadow mode

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `adjudicate-phase-outcomes-in-shadow-mode`
> Effort: L
> Priority: 1

## Summary

Insert a decision step between a phase sub-agent's return and apply_phase_outcome that asks Choice(outcome, the phase's allowed outcomes) and Noul("the evidence supports the claimed outcome") over the handoff record, expected_outcomes, worktree diff stat, test-output tail and the claimed outcome, recording judged versus claimed without changing the reducer.

## Dependencies

- `ri-06`

## Acceptance Outcomes

- Each phase transition appends a record with claimed outcome, judged outcome, the outcome distribution and the evidence Noul to loop-state.json phase_history.
- transition(state, outcome) still runs on the claimed outcome for the whole shadow period, proven by a replay test showing identical phase sequences.
- The disagreement report attributes each disagreement to the side the next review round vindicated, over at least one sprint of recorded autopilot runs.
- A degraded decision (helper returns None) is recorded via record_degraded and leaves the existing behaviour unchanged, covered by a test.

## Rationale

Pilot step 3's correctness half, from the companion note. Today the reducer trusts the label the actor chose for itself, so a fixer that says "fixed" costs a full review dispatch to disprove. Shadow mode measures how often claimed and judged disagree, and which side the next review round vindicated, before the reducer is allowed to act on the judgment.

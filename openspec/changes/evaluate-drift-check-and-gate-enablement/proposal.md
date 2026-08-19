# Evaluate drift check and gate enablement

> Parent roadmap: `closed-loop-learning`
> Change ID: `evaluate-drift-check-and-gate-enablement`
> Effort: S
> Priority: 4

## Summary

Add a gen-eval scenario with a seeded drifting session and an on-track control session, and gate default-on enablement of the drift monitor on a recorded pass against the no-drift-check baseline.

## Dependencies

- `ri-12`

## Acceptance Outcomes

- The seeded drifting session receives an off-track verdict and a bounded course correction in the gen-eval scenario.
- The on-track control session receives no injection.
- Default-on enablement is recorded only after a pass against the no-drift-check baseline; until then the flag stays off.

## Rationale

The repo's injection-evidence norm requires the drift check to beat a baseline before default-on; the paired scenario proves both detection of real drift and silence on on-track sessions.

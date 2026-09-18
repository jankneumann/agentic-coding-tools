# Add a judged first stage to coordinator audit triage

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `add-a-judged-first-stage-to-coordinator-audit-triage`
> Effort: M
> Priority: 3

## Summary

In audit_triage.drain_and_classify, ask per session batch Noul("This session shows a capability gap in the harness"), Choice(failure_type, the six enum values plus none) and Score(severity, [low, medium, high, critical]); run the current LLM prompt only for sessions above the recall-oriented threshold, seeded with the stage-one labels so its output is constrained.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- The recall-oriented threshold lives in config and a replay over recorded audit batches shows recall no lower than the current prompt's, with both numbers recorded.
- Sessions below the threshold produce no LLM call, asserted by a call-count test over a clean-session fixture.
- Stage-two findings are seeded with the stage-one failure_type and severity and still pass validate_finding unchanged.
- The hot-path ring buffer write path is unmodified and its latency test is unchanged.

## Rationale

Pilot step 5. The prompt's own instruction to "prefer recall over precision" is a calibration statement that a threshold on a calibrated probability expresses directly. capability_gap is prose and must stay with an LLM, which makes this the two-stage shape; validate_finding and the hot-path ring buffer are untouched.

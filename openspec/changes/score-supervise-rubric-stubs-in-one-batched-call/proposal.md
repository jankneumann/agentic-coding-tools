# Score supervise rubric stubs in one batched call

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `score-supervise-rubric-stubs-in-one-batched-call`
> Effort: M
> Priority: 4

## Summary

Replace the analyst-archetype rubric dispatch with up to 100 Score questions over one manifest state (five factors for up to 20 stubs) in a single call, and resolve the justification blocker by relaxing justification to optional in the rubric-score contract so the digest renders the Score legend level instead.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- The rubric-score contract marks justification optional and the digest renders the Score legend level when it is absent, covered by a digest snapshot test.
- Twenty stubs are scored on five factors in one call and the result validates against the updated schema, asserted over a manifest fixture.
- Structural-error handling (missing, partial, invalid, late) is exercised by a test showing the analyst-archetype dispatch remains the fallback.
- Scores over a recorded manifest agree with the archived analyst output above a recorded agreement rate, cited in the change artifacts.

## Rationale

Pilot step 5. The current prompt runs under a 120-second timeout with one retry and rejects "missing, partial, invalid, or late output" — a description of the failure mode this primitive removes. The schema decision must land with the change because rubric-score.schema.json marks justification required per factor; the digest is deterministic by design, so this is a contract change rather than an architecture change.

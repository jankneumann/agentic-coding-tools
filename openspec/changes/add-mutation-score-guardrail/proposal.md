# Add the mutation-score guardrail

> Parent roadmap: `skill-rightsizing`
> Change ID: `add-mutation-score-guardrail`
> Effort: M
> Priority: 2

## Summary

Score the test suites produced during a replay by mutation, so a run that raises its pass rate by writing weaker tests is detected rather than rewarded.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- Every replay emits a mutation score alongside its acceptance-scenario pass rate.
- A deliberately weakened test suite is demonstrated to lower the score.
- The guardrail is wired into the accept/reject rule as a non-regression condition.

## Rationale

A model-written test suite is only a valid grader if it is not vacuous, and vacuity is objectively measurable. This closes the one gaming path the acceptance-rate metric cannot see.

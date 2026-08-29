# Convert the failure record into executable regression scenarios

> Parent roadmap: `skill-rightsizing`
> Change ID: `convert-failure-record-to-regression-scenarios`
> Effort: L
> Priority: 1

## Summary

Turn the Observations and Follow-ups sections of the 18 files in docs/merge-logs/ and the entries in docs/lessons-learned.md into runnable regression scenarios under the gen-eval scenario format, each tagged with the defect category it represents.

## Dependencies

- None

## Acceptance Outcomes

- Every Observation and Follow-up in docs/merge-logs/ is either converted to a scenario or explicitly marked not-reproducible with a reason.
- The scenario suite runs from a single command and reports pass/fail per scenario.
- Each scenario carries a defect-category tag drawn from a documented closed vocabulary.
- At least one converted scenario fails against the current codebase, proving the suite has teeth rather than encoding only already-fixed behaviour.

## Rationale

These are human-witnessed defects with rationale attached — the least circular evidence in the repository, and currently inert prose. They also supply the real defect categories that the seeded-defect harness needs, so this gates ri-06.

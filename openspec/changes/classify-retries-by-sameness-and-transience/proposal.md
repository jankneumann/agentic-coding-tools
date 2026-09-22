# Classify retries by sameness and transience

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `classify-retries-by-sameness-and-transience`
> Effort: M
> Priority: 4

## Summary

In phase_fixer and the roadmap dispatcher, replace the consecutive-failure count as the sole retry signal with Noul("this error is the same failure as the previous attempt"), Noul("this error is transient and retrying without change is likely to succeed") and Choice(failure_type, the existing failure-type enum), stopping early when a failure is the same and not transient.

## Dependencies

- `ri-05`
- `ri-20`

## Acceptance Outcomes

- A same-and-not-transient failure stops retrying before the ceiling, asserted by a test that counts attempts against the current count-only baseline.
- The retry ceiling is unchanged and still terminates, covered by a test where both Nouls are inconclusive.
- The emitted failure_type uses the existing enum values consumed by improve-harness, validated against that consumer's schema.
- With the helper returning None the consecutive-failure count governs and existing phase_fixer retry tests pass unchanged.

## Rationale

Pilot step 6 and companion section 8, factor 9. Counting to N spends N attempts discovering what the first repeat already showed. The failure_type choice also compacts each error into the vocabulary the improve-harness pipeline already mines, so the labels arrive for free.

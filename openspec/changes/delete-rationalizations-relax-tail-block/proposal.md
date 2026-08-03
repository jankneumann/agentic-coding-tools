# Delete the Common Rationalizations block and relax the tail-block invariants

> Parent roadmap: `skill-rightsizing`
> Change ID: `delete-rationalizations-relax-tail-block`
> Effort: M
> Priority: 2

## Summary

Remove Common Rationalizations from the skill tail template and from all 20 skills carrying it, drop the minimum-row thresholds, and retain Verification only where its items are machine-checkable and Red Flags only where they name a failure this codebase has actually seen.

## Dependencies

- `ri-09`

## Acceptance Outcomes

- No SKILL.md contains a Common Rationalizations section.
- The tail-block invariant test no longer enforces minimum row counts.
- Every retained Verification item names a file path, command or artifact that can be checked.
- Replay results are non-inferior to the ri-09 baseline.

## Rationale

The Rationalizations table argues pre-emptively against excuses a frontier model does not make, costs 578 lines, and sits behind a test-enforced minimum that forces padding on every new skill.

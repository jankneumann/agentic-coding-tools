# Assert in CI that skill-generated artifacts pass their own validators

> Parent roadmap: `skill-rightsizing`
> Change ID: `assert-generated-artifacts-validate-in-ci`
> Effort: S
> Priority: 1

## Summary

For every skill that emits a structured artifact — OpenSpec change directories, roadmap.yaml, spec deltas, work-packages.yaml — add a test that generates the artifact and runs the real validator against it, wired into CI.

## Dependencies

- None

## Acceptance Outcomes

- Every artifact-generating skill has a test that runs its artifact through the real validator, not a structural approximation.
- Bypassing the scaffolder's spec-delta writer makes that test fail.
- The checks run in CI on every push and block merge on failure.
- Each generator documents which validator is authoritative for its output.

## Rationale

plan-roadmap's scaffolder created specs/ and never wrote a delta into it, so it shipped changes openspec validate --strict rejects, and its 17 tests never caught it because they asserted the output contained the right strings rather than that it was valid. This is the shape-not-behaviour gap in its cheapest, most targeted form, and unlike ri-18 it can land immediately without waiting on the holdout decision.

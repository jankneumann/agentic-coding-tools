# Publish the arm-A baseline scorecard

> Parent roadmap: `skill-rightsizing`
> Change ID: `publish-arm-a-baseline-scorecard`
> Effort: M
> Priority: 1

## Summary

Run the current skills across the development split and publish the baseline scorecard covering acceptance pass rate, SHALL/MUST clause coverage, mutation score and process telemetry, with the accept/reject rule pre-registered before any cut lands.

## Dependencies

- `ri-03`
- `ri-05`
- `ri-07`

## Acceptance Outcomes

- A committed scorecard reports every metric for the current skills across the development split.
- The accept/reject rule is recorded before any rightsizing change is merged.
- Run-to-run variance is reported per metric so later deltas can be read against noise.

## Rationale

Without a committed before-number every later deletion is a hope rather than a measurement. Pre-registering the decision rule prevents the threshold moving to fit the result.

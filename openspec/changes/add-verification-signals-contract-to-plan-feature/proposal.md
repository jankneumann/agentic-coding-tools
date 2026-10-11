# Add verification-signals contract to plan-feature

> Parent roadmap: `evidence-grounded-debugging`
> Change ID: `add-verification-signals-contract-to-plan-feature`
> Effort: M
> Priority: 3

## Summary

Make plan-feature emit a required verification-signals section in proposals, naming each quantitative signal, its emitting layer, its control or baseline, and its tolerance, with an explicit opt-out marker for docs-only changes. Add a repo-local proposal check and an iterate-on-plan finding for signals that are missing or lack an emitting layer or baseline.

## Dependencies

- None

## Acceptance Outcomes

- The proposal check reports a new proposal that lacks a verification-signals section and lacks the docs-only opt-out marker, and fails it when run in blocking mode.
- The check ships in advisory mode by default, and its mode and observed false-positive count are recorded before it can be set to blocking.
- iterate-on-plan reports a finding when a declared signal names no emitting layer or no baseline.

## Rationale

Signal-parity verification needs correctness observation decided at design time; this contract is the input the snapshot capture and baseline-diff gate read, so default data collection becomes a planning obligation.

# Add verification-signals contract to plan-feature

> Parent roadmap: `evidence-grounded-debugging`
> Change ID: `add-verification-signals-contract-to-plan-feature`
> Effort: M
> Priority: 3

## Summary

Make plan-feature emit a required verification-signals section in proposals, naming each quantitative signal, its emitting layer, its control or baseline, and its tolerance. The section is always present; planning-only and documentation-only changes state not applicable together with the reason instead of omitting it. Add a blocking proposal check for that structure (changes already in flight are grandfathered) and an advisory iterate-on-plan finding for declared signals that lack an emitting layer or baseline.

## Dependencies

- None

## Acceptance Outcomes

- The proposal check fails a new proposal whose verification-signals section is absent, empty, or marked not applicable without a stated reason.
- A planning-only or documentation-only proposal whose section reads not applicable with a reason passes, and changes in flight before the check landed are not failed.
- iterate-on-plan reports a finding when a declared signal names no emitting layer or no baseline.

## Rationale

Signal-parity verification needs correctness observation decided at design time; this contract is the input the snapshot capture and baseline-diff gate read, so default data collection becomes a planning obligation.

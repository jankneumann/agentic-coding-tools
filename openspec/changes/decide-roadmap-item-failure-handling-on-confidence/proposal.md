# Decide roadmap item failure handling on confidence

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `decide-roadmap-item-failure-handling-on-confidence`
> Effort: M
> Priority: 4

## Summary

Replace the replan boolean derived from _normalize_outcome in orchestrator._handle_failure with Choice(next, {retry_same_vendor, retry_other_vendor, skip_item, request_replan, escalate}) over the failure reason, the item's acceptance outcomes and the attempt history.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- request_replan still traverses the REPLAN_REQUIRED gate unchanged, asserted by an existing gate test passing unmodified.
- Each decision and its distribution are appended to the roadmap checkpoint's event log.
- The attempt-count ceiling still terminates retries regardless of the chosen label, covered by a test.
- With the helper returning None, _normalize_outcome's replan boolean governs and current orchestrator failure tests pass unchanged.

## Rationale

Pilot step 6 and companion section 4. The current path collapses a five-way decision into one boolean, so a transient vendor failure and a genuinely under-specified item are handled the same way. The decision only chooses which existing gate to reach for; request_replan still passes through the REPLAN_REQUIRED gate.

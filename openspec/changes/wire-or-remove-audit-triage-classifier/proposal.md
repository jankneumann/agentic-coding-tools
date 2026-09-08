# Wire or remove the coordinator audit-triage classifier

> Parent roadmap: `backpass-memory-alignment`
> Change ID: `wire-or-remove-audit-triage-classifier`
> Effort: S
> Priority: 3

## Summary

Decide whether agent-coordinator/src/audit_triage.py is wired to a background task that runs over audit events or removed, record the decision, and implement it so the classifier is no longer documented-but-uncalled.

## Dependencies

- None

## Acceptance Outcomes

- Either a background task invokes the classifier and an integration test shows an audit event producing a classification, or the module and its docs references are deleted and the test suite passes.
- The decision is recorded in docs/decisions/ or the coordinator README with the reason.
- GitHub issue #496 is closed by the merged change.

## Rationale

Section 6 defect 5, filed as GitHub issue #496. A classifier with no caller outside its tests is dead code that misleads the pipeline documentation; resolving it either adds a fourth working emitter to the capability-gap contract or removes a false claim.

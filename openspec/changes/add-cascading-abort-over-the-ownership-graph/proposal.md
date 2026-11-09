# Add cascading abort over the ownership graph

> Parent roadmap: `durable-execution`
> Change ID: `add-cascading-abort-over-the-ownership-graph`
> Effort: L
> Priority: 2

## Summary

Add an abort operation for roadmap items and changes that durably records intent in the owning canonical artifact first, then cascades to work packages, supervised dispatches and phase sub-agents, queue projection rows, and effects, leaving each node terminal (aborted with reason) or parked and resumable per operator choice, and skipping detached work.

## Dependencies

- `ri-01`
- `ri-05`

## Acceptance Outcomes

- abort <roadmap-id>:<item-id> and the change-level form cancel every owned queue row through the reconcile path, interrupt or quarantine every owned dispatch, cancel requested effects, and write aborted state to the owning canonical artifact, asserted by a recorded integration test.
- Aborting during a started never_replay effect leaves the effect quarantined and the node parked, not aborted, with the effect named in the escalation.
- Re-running abort on a partially aborted tree completes the remaining nodes and changes nothing already terminal.
- Abort works in all three tiers; in coordinator-free tiers it operates only on loop-state and local sub-agent handles, and detached work is skipped and reported.
- Leases are released only where death or completion is proven; an expired heartbeat alone results in quarantine.

## Rationale

Phase 2 control; stopping in-flight work today is a manual multi-artifact operation, and abort must resolve started effects by replay policy and keep the supervisor's unknown-to-quarantine rule rather than inferring death from heartbeats.

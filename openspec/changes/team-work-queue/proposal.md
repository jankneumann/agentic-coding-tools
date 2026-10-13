# Make the work queue a shared team execution surface

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `team-work-queue`
> Effort: L
> Priority: 1

## Summary

Extend work_queue.py, /supervise, and /autopilot-roadmap so queue entries carry the owning principal, the originating roadmap item, and its dependencies, any eligible agent can claim any ready entry, and ordering across principals follows an explicit owned priority policy, with entries remaining rebuildable projections of roadmap.yaml and loop-state.json.

## Dependencies

- `ri-02`

## Acceptance Outcomes

- Roadmap items from two principals' roadmaps appear in one queue, each entry attributed to its owner and source item.
- An agent claims the highest-priority ready entry under the declared priority policy, independent of entry owner.
- Deleting all queue rows and re-running reconciliation reproduces the same entries from git state.
- A change to the cross-principal priority policy is accepted only from the policy's owner.
- With a single principal and no owners.yaml, queue ordering and claim behavior match the pre-change behavior in the existing work-queue tests.

## Rationale

The execution model makes the shared queue the primary execution surface (P10) and implementation a commons (P2); cross-principal ordering is an intent decision (P3). This is the foundation for queue-dispatched implementation and escalation parking.

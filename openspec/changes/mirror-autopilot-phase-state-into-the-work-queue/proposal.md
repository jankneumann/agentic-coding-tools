# Mirror autopilot phase state into the work queue

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `mirror-autopilot-phase-state-into-the-work-queue`
> Effort: M
> Priority: 2

## Summary

Have autopilot mirror phase transitions into the coordinator work queue using the idempotent submission contract, so `apps/kanban-viz` shows live truth instead of an empty board. Supervisor-dispatched runs inherit the mirroring automatically since they drive autopilot through the same seam.

## Dependencies

- `ri-08`

## Acceptance Outcomes

- kanban-viz reflects a live autopilot run's phase transitions within one poll interval.
- Every mirrored queue entry is derivable from the corresponding loop-state.json, verified by a reconciliation check after a run.
- Killing and resuming a run leaves no orphaned or duplicate queue entries.

## Rationale

Closes the observability gap; the queue projection only earns its keep if it reflects live execution, and kanban-viz is the frontend that proves it.

# Proposal: Mirror Autopilot Phase State into the Work Queue

## Why

Ri-08 made queue projection idempotent and crash-repairable, but left its callback optional and unregistered. Consequently a real coordinated Autopilot run can advance authoritative `loop-state.json` while the coordinator queue—and therefore `apps/kanban-viz`—shows no current phase.

## What Changes

Add one coordinated projection adapter that derives a work-queue task exclusively from the just-persisted `LoopState`, using `(change_id, current_phase, total_iterations)` as the projection identity. Register it at the Autopilot host boundary for coordinated execution and reconcile it from durable loop-state on resume. Local-parallel and sequential execution continue supplying no callback and make no coordinator request.

Make the host-driven CLI protocol use the same adapter after its canonical state writes, so supervised runs inherit phase mirroring without a supervise-specific publisher. Projection results remain observability-only: failures are reported, and queue responses never advance or repair loop-state.

## Scope

- coordinated Autopilot projection adapter and host/CLI registration;
- live transition, duplicate replay, outage, and crash/resume tests;
- coordinator-backed behavioral proof that queue rows remain derivable from loop-state and visible through the existing kanban data path;
- documentation of latency and degradation behavior.

## Out of Scope

- changing kanban-viz polling or treating the board as authoritative;
- changing work-queue persistence, projection identity, or claim semantics landed by ri-08;
- requiring a coordinator in local-parallel or sequential tiers;
- adding a second phase-state store.

## Dependencies

- ri-07: work-queue truth/projection contract.
- ri-08: idempotent submit/reconcile APIs and persist-before-project callback seam.

## Acceptance

- A coordinated live run projects each durable phase generation within one existing kanban poll interval.
- Every projected row is reproducible from the corresponding `loop-state.json` tuple and bounded metadata.
- Restart reconciliation cancels stale active rows and ensures exactly one current row without duplicates.
- Coordinator failure never changes loop-state and is surfaced as degraded projection.
- Coordinator-free tiers perform zero bridge imports, probes, or queue requests.

# Tasks: Mirror Autopilot Phase State into the Work Queue

## Phase 1 — RED contract tests

- [ ] 1.1 Write adapter RED tests for exact projection identity, bounded allowlisted payload, submit/reconcile mode mapping, non-success envelopes, and response non-authority.
- [ ] 1.2 Write host-driven CLI RED tests proving a coordinated state mutation saves before projection and resume reconciles before phase work.
- [ ] 1.3 Write regressions proving local-parallel/sequential execution causes zero bridge imports, probes, or calls.

## Phase 2 — Coordinated adapter and registration

- [ ] 2.1 Implement the shared LoopState-to-bridge projection adapter with explicit connection/configuration injection.
- [ ] 2.2 Register it at the coordinated in-process and host-driven CLI boundaries without changing the state-machine default.
- [ ] 2.3 Update the Autopilot skill protocol to perform post-write submit and pre-work resume reconciliation through the shared CLI boundary.

## Phase 3 — Behavioral and crash recovery proof

- [ ] 3.1 Add a coordinator-backed test for successive live phase rows, idempotent replay, stale-row cancellation, and exactly one current generation.
- [ ] 3.2 Simulate termination after loop-state save but before submit; resume and prove reconciliation derives solely from the file.
- [ ] 3.3 Verify the existing kanban queue/status query exposes the current projected phase within one configured poll interval; do not modify frontend polling.

## Phase 4 — Integration and validation

- [ ] 4.1 Update the work-queue truth/projection guide and Autopilot documentation with registration, degradation, and latency behavior.
- [ ] 4.2 Synchronize runtime skill mirrors and verify scope.
- [ ] 4.3 Run focused Autopilot/bridge/coordinator/kanban tests, real PostgreSQL projection tests when available, Ruff, the AST truth-direction invariant, strict OpenSpec, context-drift, and scope validation.

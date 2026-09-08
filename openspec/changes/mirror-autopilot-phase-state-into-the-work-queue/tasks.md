# Tasks: Mirror Autopilot Phase State into the Work Queue

## Phase 1 — RED contract tests

- [ ] 1.1 Write adapter RED tests for exact projection identity, stricter-id rejection, bounded allowlisted payload, three successive generations with `reconciliation_required` head advancement, direct reconcile mode, `task_type=issue`/priority-1 board visibility, coordinator-only canonical-row label correlation, interrupted cleanup/idempotency, non-success envelopes, and response non-authority.
- [ ] 1.2 Write host-driven CLI RED tests for canonical `init` and `transition` writers plus explicit `project-state --mode submit|reconcile`; cover every runner state-mutating command and gate exit 0/3/4, proving save-before-project, save-failure suppression, and reconcile-before-gate/work ordering.
- [ ] 1.3 Write import/module and fail-fast call-spy regressions proving local-parallel/sequential execution neither imports the new projection module nor constructs/registers it nor calls submit, reconcile, or coordinator-only projection-label helpers; exclude pre-existing detection/archetype bridge use.

## Phase 2 — Coordinated adapter and registration

- [ ] 2.1 Implement the shared LoopState-to-bridge projection adapter with explicit connection/configuration injection, submit-to-reconcile head advancement, `task_type=issue`, and adapter-owned two-label repair through additive coordinator-only issue list/update bridge helpers that bypass GitHub routing.
- [ ] 2.2 Add `runner.py init`, `runner.py transition`, and the read-only `project-state` boundary; register the adapter explicitly in coordinated in-process and host-driven execution without changing the state-machine default or `apply-outcome` semantics.
- [ ] 2.3 Update the Autopilot skill protocol to use canonical CLI writers, perform submit after every durably successful state mutation (including gate exit 4 parks), suppress projection after failed saves, and reconcile before resume gate handling/work.

## Phase 3 — Behavioral and crash recovery proof

- [ ] 3.1 Add a coordinator-backed test for at least three successive live phase rows, head advancement, idempotent replay, canonical-label failure, interrupted stale-label cleanup and retry, stale-row cancellation, GitHub-backend override resistance, and exactly one active current board-visible projection generation.
- [ ] 3.2 Simulate termination after loop-state save but before submit; resume and prove reconciliation derives solely from the file.
- [ ] 3.3 Verify the existing label-only `/issues/list` query exposes the priority-1 current projected phase within one configured poll interval after seeding more than 50 ordinary lower-priority issues; do not modify frontend polling or ordinary issue labels.

## Phase 4 — Integration and validation

- [ ] 4.1 Update the work-queue truth/projection guide and Autopilot documentation with registration, degradation, and latency behavior.
- [ ] 4.2 Synchronize runtime skill mirrors and verify scope.
- [ ] 4.3 Run focused Autopilot/bridge/coordinator/kanban tests, real PostgreSQL projection tests when available, Ruff, the AST truth-direction and projection-import invariants, strict OpenSpec, context-drift, and scope validation.

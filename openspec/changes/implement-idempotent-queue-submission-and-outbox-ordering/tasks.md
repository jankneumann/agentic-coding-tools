# Tasks — Idempotent Queue Submission and Outbox Ordering

Tasks use the plan-feature sizing scale. Test tasks precede the behavior they verify. No task is XL; the largest tasks are M.

## Phase 0 — Contract gate (wp-contracts)

- [ ] 0.1 (S) Validate the OpenAPI and SQL contracts against the approved projection tuple, additive response, and ri-09 exclusion.
  **Spec scenarios**: agent-coordinator (Concurrent projection replay creates one task; Resume converges stale projection rows), coordination-bridge (Bridge reports a deduplicated replay), skill-workflow (State persists before projection)
  **Contracts**: contracts/openapi/v1.yaml, contracts/db/schema.sql
  **Design decisions**: D1, D2, D3, D4
  **Dependencies**: None

## Phase 1 — Coordinator persistence boundary (wp-coordinator-queue)

- [ ] 1.1 (M) Write PostgreSQL RED tests for concurrent replay, canonical task identity, unkeyed compatibility, stale-row cancellation, terminal-row preservation, and reconciliation replay.
  **Spec scenarios**: agent-coordinator (Concurrent projection replay creates one task; Unkeyed tasks remain independent; Resume converges stale projection rows; Reconciliation replay is idempotent)
  **Contracts**: contracts/db/schema.sql
  **Design decisions**: D1, D2, D3
  **Dependencies**: 0.1
- [ ] 1.2 (M) Add migration `035_work_queue_projection.sql` with the partial unique expression index plus submit/reconcile RPC behavior.
  **Spec scenarios**: agent-coordinator (Concurrent projection replay creates one task; Unkeyed tasks remain independent; Resume converges stale projection rows; Reconciliation replay is idempotent)
  **Contracts**: contracts/db/schema.sql
  **Design decisions**: D1, D2, D3
  **Dependencies**: 1.1
- [ ] 1.3 (S) Write service RED tests for complete-key validation, canonical response fields, and legacy submission behavior.
  **Spec scenarios**: agent-coordinator (Concurrent projection replay creates one task; Unkeyed tasks remain independent)
  **Contracts**: contracts/openapi/v1.yaml
  **Design decisions**: D1, D2
  **Dependencies**: 0.1
- [ ] 1.4 (M) Extend `WorkQueueService` result models, keyed submission validation, and reconciliation method.
  **Spec scenarios**: agent-coordinator (Concurrent projection replay creates one task; Unkeyed tasks remain independent; Reconciliation replay is idempotent)
  **Contracts**: contracts/openapi/v1.yaml, contracts/db/schema.sql
  **Design decisions**: D1, D2, D3
  **Dependencies**: 1.2, 1.3
- [ ] Checkpoint: run coordinator migration and service tests, review cumulative diff, verify package scope
- [ ] 1.5 (S) Write API RED tests for additive submit results, reconcile request validation, authentication, and machine-readable cancellation results.
  **Spec scenarios**: agent-coordinator (Resume converges stale projection rows), coordination-bridge (Bridge reports a deduplicated replay)
  **Contracts**: contracts/openapi/v1.yaml
  **Design decisions**: D2, D3
  **Dependencies**: 1.4
- [ ] 1.6 (M) Add `/work/reconcile` plus additive `/work/submit` response fields in `coordination_api.py`.
  **Spec scenarios**: agent-coordinator (Resume converges stale projection rows), coordination-bridge (Bridge reports a deduplicated replay)
  **Contracts**: contracts/openapi/v1.yaml
  **Design decisions**: D2, D3
  **Dependencies**: 1.5
- [ ] Checkpoint: run coordinator API and PostgreSQL integration tests, review cumulative diff, verify package scope

## Phase 2 — Outbox projection seam (wp-bridge-projection)

- [ ] 2.1 (S) Write bridge RED tests for deduplicated submit results, reconciliation payload derivation, and no-raise transport failure.
  **Spec scenarios**: coordination-bridge (Bridge reports a deduplicated replay; Reconcile transport failure preserves caller truth)
  **Contracts**: contracts/openapi/v1.yaml
  **Design decisions**: D2, D6
  **Dependencies**: 0.1
- [ ] 2.2 (S) Extend coordination-bridge queue helpers with the reconciliation operation and additive result envelope.
  **Spec scenarios**: coordination-bridge (Bridge reports a deduplicated replay; Reconcile transport failure preserves caller truth)
  **Contracts**: contracts/openapi/v1.yaml
  **Design decisions**: D2, D6
  **Dependencies**: 2.1
- [ ] 2.3 (M) Write autopilot RED tests for save-before-project ordering, save failure short-circuit, projection failure durability, resume reconciliation, and response non-authority.
  **Spec scenarios**: skill-workflow (State persists before projection; Crash window repairs on resume)
  **Contracts**: contracts/openapi/v1.yaml
  **Design decisions**: D4, D6
  **Dependencies**: 0.1
- [ ] 2.4 (M) Add the optional post-persistence projection helper plus resume reconciliation injection seam.
  **Spec scenarios**: skill-workflow (State persists before projection; Crash window repairs on resume)
  **Design decisions**: D4, D6
  **Dependencies**: 2.2, 2.3
- [ ] Checkpoint: run bridge and autopilot focused tests, review cumulative diff, verify package scope
- [ ] 2.5 (S) Write regression tests proving callback absence makes zero coordinator imports, probes, or requests across local-parallel and sequential execution.
  **Spec scenarios**: skill-workflow (Fallback tiers remain coordinator-free)
  **Design decisions**: D5
  **Dependencies**: 2.4
- [ ] 2.6 (S) Finalize coordinator-free default behavior and preserve existing tier-selection call sites.
  **Spec scenarios**: skill-workflow (Fallback tiers remain coordinator-free)
  **Design decisions**: D5
  **Dependencies**: 2.5
- [ ] Checkpoint: run all affected skill tests plus the ri-07 AST invariant, review cumulative diff, verify package scope

## Phase 3 — Integration (wp-integration)

- [ ] 3.1 (S) Update the work-queue truth/projection guide with the implemented interfaces, failure recovery, and explicit ri-09 live-mirroring boundary.
  **Spec scenarios**: skill-workflow (Crash window repairs on resume; Fallback tiers remain coordinator-free)
  **Design decisions**: D4, D5, D6
  **Dependencies**: 1.6, 2.6
- [ ] 3.2 (M) Run contract parsing, strict OpenSpec validation, PostgreSQL integration tests, coordinator tests, bridge tests, autopilot tests, tier tests, and the truth-direction invariant.
  **Spec scenarios**: all scenarios in this change
  **Contracts**: contracts/openapi/v1.yaml, contracts/db/schema.sql
  **Design decisions**: D1, D2, D3, D4, D5, D6
  **Dependencies**: 3.1
- [ ] Checkpoint: full affected suites green, cumulative diff maps to tasks, no ri-09 live mirroring present

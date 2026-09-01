# Tasks — Idempotent Queue Submission and Outbox Ordering

Tasks use the plan-feature sizing scale. Test tasks precede the behavior they verify. No task is XL; the largest tasks are M.

## Phase 0 — Contract gate (wp-contracts)

- [ ] 0.1 (S) Validate the OpenAPI and SQL contracts against the approved projection tuple, additive response, and ri-09 exclusion.
  **Spec scenarios**: agent-coordinator (Concurrent projection replay creates one task; Resume converges stale projection rows), coordination-bridge (Bridge reports a deduplicated replay), skill-workflow (State persists before projection)
  **Contracts**: contracts/openapi/v1.yaml, contracts/db/schema.sql
  **Design decisions**: D1, D2, D3, D4
  **Dependencies**: None

## Phase 1 — Coordinator persistence boundary (wp-coordinator-queue)

- [ ] 1.1 (M) Write real PostgreSQL RED tests for same-key replay, different-sequence submit/reconcile races, canonical identity, unkeyed compatibility, all terminal-current statuses, stale-row cancellation, malformed legacy preflight, rollback, remediation retry, and reconciliation replay.
  **Spec scenarios**: agent-coordinator (Concurrent projection replay creates one task; Unkeyed tasks remain independent; Resume converges stale projection rows; Reconciliation replay is idempotent)
  **Contracts**: contracts/db/schema.sql
  **Design decisions**: D1, D2, D3
  **Dependencies**: 0.1
- [ ] 1.2 (M) Add migration `035_work_queue_projection.sql` with non-throwing text expressions, deterministic locked preflight, exact conflict target/lookup, per-change advisory transaction locks, and terminal-aware submit/reconcile RPC behavior.
  **Spec scenarios**: agent-coordinator (Concurrent projection replay creates one task; Unkeyed tasks remain independent; Resume converges stale projection rows; Reconciliation replay is idempotent)
  **Contracts**: contracts/db/schema.sql
  **Design decisions**: D1, D2, D3
  **Dependencies**: 1.1
- [ ] 1.3 (S) Write service RED tests for one authoritative `projection_key`, reserved embedded-key rejection, strict change/phase/sequence bounds including int-not-bool, canonical success and terminal fields, and legacy unkeyed behavior.
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
- [ ] 1.5 (S) Write HTTP RED tests for additive success results, reconcile validation, reserved keys, 401/403/422 Problem responses, authentication/policy denial, and machine-readable cancellation results.
  **Spec scenarios**: agent-coordinator (Resume converges stale projection rows), coordination-bridge (Bridge reports a deduplicated replay)
  **Contracts**: contracts/openapi/v1.yaml
  **Design decisions**: D2, D3
  **Dependencies**: 1.4
- [ ] 1.6 (M) Add `/work/reconcile` plus additive `/work/submit` success fields and RFC 7807 failure mappings in `coordination_api.py`.
  **Spec scenarios**: agent-coordinator (Resume converges stale projection rows), coordination-bridge (Bridge reports a deduplicated replay)
  **Contracts**: contracts/openapi/v1.yaml
  **Design decisions**: D2, D3
  **Dependencies**: 1.5
- [ ] 1.7 (S) Write RED tests for direct MCP, HTTP-proxy MCP, and `coordination-cli work submit|reconcile` parity and discriminated failure envelopes.
  **Spec scenarios**: agent-coordinator (Direct and proxy MCP mappings agree; CLI exposes projection operations; Policy denial is not a success payload)
  **Dependencies**: 1.6
- [ ] 1.8 (M) Implement direct/proxy MCP and CLI keyed submit/reconcile mappings with one explicit projection key.
  **Spec scenarios**: agent-coordinator (Direct and proxy MCP mappings agree; CLI exposes projection operations)
  **Dependencies**: 1.7
- [ ] Checkpoint: run coordinator API, MCP, CLI, and real PostgreSQL integration tests; review cumulative diff; verify package scope

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
- [ ] 2.3 (M) Write autopilot RED tests for save-before-project ordering, save failure short-circuit, projection failure durability, resume reconciliation, and response non-authority, phase-local iteration mismatch, and phase revisits.
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
  **Dependencies**: 1.8, 2.6
- [ ] 3.2 (M) Run OpenAPI semantic validation, strict OpenSpec validation, real PostgreSQL same-key/different-key concurrency and migration tests, coordinator API/MCP/CLI tests, bridge tests, autopilot tests, tier tests, and the truth-direction invariant.
  **Spec scenarios**: all scenarios in this change
  **Contracts**: contracts/openapi/v1.yaml, contracts/db/schema.sql
  **Design decisions**: D1, D2, D3, D4, D5, D6
  **Dependencies**: 3.1
- [ ] Checkpoint: full affected suites green, cumulative diff maps to tasks, no ri-09 live mirroring present

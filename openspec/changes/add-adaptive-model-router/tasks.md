# Tasks: add-adaptive-model-router (dg-00 wiring tranche)

> Canonical execution record for dispatch-governance item dg-00. The exact prior
> full-proposal task record is preserved in `tasks-full-proposal.md`; excluded work
> is indexed with rationale and migration targets in `deferred-tasks.md`.

## Phase 1 — Reconciliation and contracts

- [x] 1.1 Reconcile current main, PR 237 landed core, and stale plan-only PR 417 [S]
- [x] 1.2 Preserve the full proposal artifacts and narrow canonical dg-00 specs/DAG [S]
- [x] 1.3 Validate the five-path OpenAPI, four-table DB contract, and generated models [S]
- [x] Checkpoint: strict OpenSpec validation passes for the bounded tranche

## Phase 2 — Catalog storage and scheduled substrate (wp-db-catalog)

- [x] 2.1 Prove migration apply/re-apply behavior and additive-only DDL [S]
  **Spec scenarios**: agent-coordinator.2
- [x] 2.2 Add migration `040_model_routing.sql` for all four routing tables [S]
  **Spec scenarios**: agent-coordinator.2
- [x] 2.3 Test and implement catalog insert/read/update/delete, storage-only reads, and staleness [M]
  **Spec scenarios**: model-routing.1
- [x] 2.5 Test and implement OpenRouter refresh; failures preserve stored rows [M]
  **Spec scenarios**: model-routing.2
- [x] 2.7 Test and implement local endpoint registration and health probing [M]
  **Spec scenarios**: model-routing.3
- [x] 2.9 Test and implement actual/counterfactual spend ledger and reconciliation [M]
  **Spec scenarios**: model-routing.5
- [x] 2.11 Schedule refresher, local probe, and ledger rollup independently in WatchdogService [S]
  **Spec scenarios**: agent-coordinator.3
- [x] Checkpoint: catalog/watchdog focused tests, Ruff, and mypy pass

## Phase 3 — Routing transports and bounded delegation (wp-resolver)

- [x] 3.7 Test all five routing HTTP paths and MCP selection parity [M]
  **Spec scenarios**: agent-coordinator.1
- [x] 3.8 Expose the merged resolver through one transport-neutral RoutingService [M]
  **Spec scenarios**: model-routing.4
- [x] 3.9 Test default-off exact equality, escalation-signal forwarding, enabled delegation, errors, and bounded timeout [M]
  **Spec scenarios**: agent-archetypes.1, model-routing.6
- [x] 3.10 Implement `ROUTING_ADAPTIVE` delegation without blocking the coordinator event loop [M]
  **Spec scenarios**: agent-archetypes.1, model-routing.6
- [x] 3.11 Add and serialize `endpoint_kind`/`base_url`, including endpoint-only agents [S]
  **Spec scenarios**: agent-archetypes.2
- [x] Checkpoint: routing/API/config focused tests, Ruff, and mypy pass

## Phase 4 — Dispatcher discovery (wp-dispatch)

- [x] 4.1 Retain the merged OpenAI-compatible adapter tests and adapter implementation [S]
  **Spec scenarios**: parallel-infrastructure.1
- [x] 4.2 Make local/OpenRouter endpoints reachable after CLI and SDK discovery, with CLI precedence [M]
  **Spec scenarios**: parallel-infrastructure.1
- [x] Checkpoint: review-dispatcher tests and Ruff pass

## Phase 8 — Integrated review and validation (wp-integration)

- [ ] 8.1 Run the full affected coordinator and skills test suites [S]
  **Dependencies**: all implemented dg-00 tasks
- [ ] 8.2 Validate the package DAG/overlap, strict OpenSpec, architecture freshness/scoped
  flows, and schema-valid multi-vendor plan/implementation consensus with quorum and zero
  blocking findings [S]
  **Dependencies**: 8.1

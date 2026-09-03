# Tasks: standardize-port-leases

Sizing follows the plan-feature Task Sizing Reference. No task is XL; the two L-sized
items (2.4, 3.3) are each decomposed into the M/S tasks that follow them, so no L task
survives as a single unit of work.

## 1. Contracts (wp-contracts)

- [ ] 1.1 Write the port-lease env contract schema — every key from the `port-lease-client` spec, with types, examples, and the origin/URL formats
  **Spec scenarios**: port-lease-client.2 (Contract is backend-independent), port-lease-client.2 (Shell format), port-lease-client.2 (JSON format)
  **Contracts**: contracts/schemas/port-lease-env.schema.json
  **Design decisions**: D9, D10
  **Dependencies**: None
  **Files**: openspec/changes/standardize-port-leases/contracts/schemas/port-lease-env.schema.json
  **Size**: S

- [ ] 1.2 Write the OpenAPI delta for `/ports/allocate`, `/ports/release`, `/ports/conflict`, `/ports/reconcile`, `/ports/status` — request and response schemas with examples, RFC 7807 errors, `isolation_provided` and `ui_port` fields
  **Spec scenarios**: agent-coordinator.1 (Successful port allocation), agent-coordinator.8 (Client reports a bound port), agent-coordinator.9 (Isolated session requests ports), agent-coordinator.10 (Orphaned lease is released)
  **Contracts**: contracts/openapi/v1.yaml
  **Design decisions**: D1, D5, D6
  **Dependencies**: 1.1
  **Files**: openspec/changes/standardize-port-leases/contracts/openapi/v1.yaml
  **Size**: S

- [ ] 1.3 Write the `port_leases` DB contract — table, indexes on `expires_at` and `agent_id`, blocked-slot rows, seed rows for tests
  **Spec scenarios**: agent-coordinator.7 (Leases reload on startup), agent-coordinator.7 (Expired rows are pruned on startup)
  **Contracts**: contracts/db/schema.sql, contracts/db/seed.sql
  **Design decisions**: D2
  **Dependencies**: None
  **Files**: openspec/changes/standardize-port-leases/contracts/db/schema.sql, openspec/changes/standardize-port-leases/contracts/db/seed.sql
  **Size**: S

- [ ] 1.4 Validate contracts — JSON Schema self-check, OpenAPI parse, SQL applies to a scratch Postgres
  **Dependencies**: 1.1, 1.2, 1.3
  **Files**: openspec/changes/standardize-port-leases/contracts/README.md
  **Size**: XS

- [ ] Checkpoint: run tests, review diff, verify scope

## 2. Coordinator allocator (wp-coordinator)

- [ ] 2.1 Write tests for the five-port block, `ui_port`, minimum range 5, and `conflict_block_minutes` config
  **Spec scenarios**: agent-coordinator.1 (Successful port allocation), agent-coordinator.3 (Default configuration), agent-coordinator.3 (Invalid configuration values)
  **Contracts**: contracts/openapi/v1.yaml
  **Design decisions**: D4
  **Dependencies**: 1.4
  **Files**: agent-coordinator/tests/test_port_allocator.py
  **Size**: S

- [ ] 2.2 Extend `PortAllocation`, `PortAllocatorConfig`, and slot arithmetic to five ports; extend `env_snippet` with `UI_PORT`, `API_BASE_URL`, `UI_ORIGIN`, `COORDINATOR_CORS_ALLOWED_ORIGINS`
  **Dependencies**: 2.1
  **Files**: agent-coordinator/src/port_allocator.py, agent-coordinator/src/config.py
  **Size**: S

- [ ] 2.3 Write tests for concurrent allocation disjointness (20 sessions x 50 iterations) and blocked-slot skipping
  **Spec scenarios**: agent-coordinator.1 (Port range exhaustion), agent-coordinator.8 (Blocked slot is skipped)
  **Design decisions**: D6
  **Dependencies**: 2.2
  **Files**: agent-coordinator/tests/test_port_allocator.py
  **Size**: S

> Note 2.4 (L, decomposed): persistence for `PortAllocatorService` is delivered as 2.4a-2.4c below; there is no single 2.4 task.

- [ ] 2.4a Write integration tests for persistence — restart survival, expired-row pruning, write-failure abort, allocate p95 under 200 ms
  **Spec scenarios**: agent-coordinator.7 (Leases reload on startup), agent-coordinator.7 (Expired rows are pruned on startup), agent-coordinator.7 (Persistence write fails), agent-coordinator.4 (Database configured and port allocator used)
  **Contracts**: contracts/db/schema.sql
  **Design decisions**: D2
  **Dependencies**: 2.3
  **Files**: agent-coordinator/tests/integration/test_port_leases_persist.py
  **Size**: M

- [ ] 2.4b Add migration `035_port_leases.sql` from the DB contract
  **Dependencies**: 2.4a
  **Files**: agent-coordinator/database/migrations/035_port_leases.sql
  **Size**: XS

- [ ] 2.4c Implement write-through persistence, startup load, prune, and `backend` reporting in `PortAllocatorService`
  **Dependencies**: 2.4b
  **Files**: agent-coordinator/src/port_allocator.py
  **Size**: M

- [ ] Checkpoint: run tests, review diff, verify scope

- [ ] 2.5 Write tests for session tie-in — `agent_id` recorded, heartbeat refreshes `expires_at`, `cleanup_dead_agents` releases leases and reports `ports_released`, active agents untouched
  **Spec scenarios**: agent-coordinator.2 (Heartbeat refreshes lease), agent-coordinator.6 (Dead agent detection and cleanup), agent-coordinator.6 (Active agent not affected by cleanup)
  **Design decisions**: D3
  **Dependencies**: 2.4c
  **Files**: agent-coordinator/tests/integration/test_cleanup_releases_ports.py, agent-coordinator/tests/test_discovery.py
  **Size**: S

- [ ] 2.6 Record `agent_id` on allocate, refresh lease on heartbeat, release leases in `cleanup_dead_agents`, add `ports_released` to `CleanupResult`
  **Dependencies**: 2.5
  **Files**: agent-coordinator/src/port_allocator.py, agent-coordinator/src/discovery.py, agent-coordinator/src/coordination_api.py
  **Size**: M

- [ ] 2.7 Write tests for the isolation gate — refuse when true, downgrade-only, legacy client omits flag, audit entry on downgrade attempt
  **Spec scenarios**: agent-coordinator.9 (Isolated session requests ports), agent-coordinator.9 (Self-reported isolation may only tighten), agent-coordinator.9 (Legacy client omits the flag)
  **Contracts**: contracts/openapi/v1.yaml
  **Design decisions**: D5
  **Dependencies**: 2.6
  **Files**: agent-coordinator/tests/test_port_allocator_api.py
  **Size**: S

- [ ] 2.8 Implement the isolation gate in `allocate_ports` and store `isolation_provided` on the session
  **Dependencies**: 2.7
  **Files**: agent-coordinator/src/port_allocator.py, agent-coordinator/src/coordination_api.py, agent-coordinator/src/discovery.py
  **Size**: S

- [ ] Checkpoint: run tests, review diff, verify scope

- [ ] 2.9 Write API tests for `POST /ports/conflict` and `POST /ports/reconcile` — block slot, unknown session, orphan release, adopted blocks, isolated caller refused, status columns
  **Spec scenarios**: agent-coordinator.8 (Client reports a bound port), agent-coordinator.8 (Conflict report for unknown session), agent-coordinator.10 (Orphaned lease is released), agent-coordinator.10 (Running project without a lease), agent-coordinator.10 (Reconciliation from an isolated session)
  **Contracts**: contracts/openapi/v1.yaml
  **Design decisions**: D1, D6
  **Dependencies**: 2.8
  **Files**: agent-coordinator/tests/test_port_allocator_api.py
  **Size**: S

- [ ] 2.10 Implement `/ports/conflict` and `/ports/reconcile` endpoints, MCP tools `report_port_conflict` and `reconcile_ports`, and proxy functions
  **Dependencies**: 2.9
  **Files**: agent-coordinator/src/coordination_api.py, agent-coordinator/src/coordination_mcp.py, agent-coordinator/src/http_proxy.py, agent-coordinator/src/port_allocator.py
  **Size**: M

- [ ] 2.11 Write a CORS test — leased `UI_ORIGIN` from `COORDINATOR_CORS_ALLOWED_ORIGINS` accepted, unknown origin rejected
  **Spec scenarios**: coordinator-kanban-viz.2 (Leased UI origin is accepted by CORS)
  **Design decisions**: D9
  **Dependencies**: 2.10
  **Files**: agent-coordinator/tests/test_cors_origins.py
  **Size**: XS

- [ ] 2.12 Keep the CORS env extension and document it in the help service alongside the new port tools
  **Dependencies**: 2.11
  **Files**: agent-coordinator/src/coordination_api.py, agent-coordinator/src/help_service.py
  **Size**: XS

- [ ] Checkpoint: run tests, review diff, verify scope

## 3. Shared client (wp-skills-client)

- [ ] 3.1 Write tests for backend selection — override, isolated short-circuit, coordinator reachable, refused connection falls back within 2 s
  **Spec scenarios**: port-lease-client.1 (Coordinator reachable), port-lease-client.1 (Coordinator unreachable), port-lease-client.1 (Isolated environment), port-lease-client.1 (Explicit override)
  **Design decisions**: D8
  **Dependencies**: 1.4
  **Files**: skills/tests/shared/test_port_lease.py
  **Size**: S

- [ ] 3.2 Write tests for env contract parity across backends against the JSON schema, shell and JSON output formats
  **Spec scenarios**: port-lease-client.2 (Contract is backend-independent), port-lease-client.2 (Shell format), port-lease-client.2 (JSON format)
  **Contracts**: contracts/schemas/port-lease-env.schema.json
  **Design decisions**: D9
  **Dependencies**: 3.1
  **Files**: skills/tests/shared/test_port_lease.py
  **Size**: S

> Note 3.3 (L, decomposed): `skills/shared/port_lease.py` is delivered as 3.3a-3.3d below; there is no single 3.3 task.

- [ ] 3.3a Implement `LeaseEnv` and the `none` backend with fixed compose defaults and contract emission in shell and JSON
  **Dependencies**: 3.2
  **Files**: skills/shared/port_lease.py
  **Size**: S

- [ ] 3.3b Implement `CoordinatorBackend` on new `try_allocate_ports`, `try_release_ports`, `try_report_port_conflict`, `try_reconcile_ports` bridge helpers
  **Dependencies**: 3.3a
  **Files**: skills/shared/port_lease.py, skills/coordination-bridge/scripts/coordination_bridge.py
  **Size**: M

- [ ] 3.3c Implement `FileBackend` — move the registry from `docker_stack.py`, adopt coordinator slot arithmetic and `PORT_ALLOC_*` config, keep fcntl lock and atomic replace, add blocked slots
  **Spec scenarios**: port-lease-client.6 (Same slot arithmetic), port-lease-client.6 (Registry lock contention)
  **Design decisions**: D7
  **Dependencies**: 3.3a
  **Files**: skills/shared/port_lease.py
  **Size**: M

- [ ] 3.3d Implement the `port-lease` CLI — `acquire`, `release`, `reconcile`, `status` with `--format shell|json`
  **Dependencies**: 3.3b, 3.3c
  **Files**: skills/shared/port_lease.py
  **Size**: S

- [ ] Checkpoint: run tests, review diff, verify scope

- [ ] 3.4 Write tests for bind probe and conflict retry — all free, one bound, three conflicts raise, context-managed release on normal and exception exit, release failure swallowed
  **Spec scenarios**: port-lease-client.3 (All ports free), port-lease-client.3 (One port already bound), port-lease-client.3 (Three consecutive conflicts), port-lease-client.4 (Normal exit), port-lease-client.4 (Exception exit), port-lease-client.4 (Release failure)
  **Design decisions**: D6
  **Dependencies**: 3.3d
  **Files**: skills/tests/shared/test_port_lease.py
  **Size**: S

- [ ] 3.5 Implement bind probing, conflict reporting, retry limit, and the context manager
  **Dependencies**: 3.4
  **Files**: skills/shared/port_lease.py
  **Size**: S

- [ ] 3.6 Write tests for `port-lease reconcile` — orphan released, compose CLI missing skips cleanly
  **Spec scenarios**: port-lease-client.5 (Orphaned lease on the host), port-lease-client.5 (Compose CLI unavailable)
  **Design decisions**: D1
  **Dependencies**: 3.5
  **Files**: skills/tests/shared/test_port_lease.py
  **Size**: XS

- [ ] 3.7 Implement reconcile using `docker compose ls --format json` with podman fallback
  **Dependencies**: 3.6
  **Files**: skills/shared/port_lease.py
  **Size**: S

- [ ] Checkpoint: run tests, review diff, verify scope

- [ ] 3.8 Update `docker_stack.py` tests — lease via `PortLease`, acquisition failure raises before compose, teardown releases and is idempotent, runtime-missing releases the lease
  **Spec scenarios**: live-service-testing.1 (Docker stack starts with leased ports), live-service-testing.1 (Lease acquisition fails), live-service-testing.1 (Docker stack teardown releases resources), live-service-testing.1 (No container runtime available)
  **Design decisions**: D9
  **Dependencies**: 3.7
  **Files**: skills/validate-feature/scripts/tests/test_docker_stack.py, skills/validate-feature/scripts/tests/test_stack_launcher.py
  **Size**: S

- [ ] 3.9 Route `DockerStackEnvironment`, `stack_launcher.py`, and `phase_deploy.py` through `PortLease`; delete the local registry
  **Dependencies**: 3.8
  **Files**: skills/validate-feature/scripts/environments/docker_stack.py, skills/validate-feature/scripts/stack_launcher.py, skills/validate-feature/scripts/phase_deploy.py
  **Size**: M

- [ ] Checkpoint: run tests, review diff, verify scope

## 4. Consumers (wp-consumers)

- [ ] 4.1 Write the port-literal regression check with its allowlist file — reports file and line, honours allowlist patterns
  **Spec scenarios**: port-lease-client.7 (New literal introduced), port-lease-client.7 (Allowlisted documentation example)
  **Dependencies**: 1.4
  **Files**: skills/validate-feature/scripts/tests/test_check_port_literals.py, skills/validate-feature/scripts/check_port_literals.py, skills/validate-feature/scripts/port_literal_allowlist.txt
  **Size**: S

- [ ] 4.2 Route the validate-feature deploy phase through `port-lease acquire --format shell`; remove the three literal defaults; build the health URL from `AGENT_COORDINATOR_REST_PORT`; add the Teardown release line
  **Spec scenarios**: agent-coordinator.5 (Deploy phase sources the lease env), agent-coordinator.5 (Teardown releases the lease)
  **Design decisions**: D9
  **Dependencies**: 4.1
  **Files**: skills/validate-feature/SKILL.md
  **Size**: S

- [ ] 4.3 Route smoke, ZAP target, and CORS smoke test through the contract — `API_BASE_URL`, `AGENT_COORDINATOR_REST_PORT`, `UI_ORIGIN`, no literal fallbacks
  **Spec scenarios**: agent-coordinator.5 (Downstream phases read the contract)
  **Dependencies**: 4.2
  **Files**: skills/validate-feature/SKILL.md, skills/validate-feature/scripts/smoke_tests/test_cors.py, skills/validate-feature/scripts/phase_smoke.py
  **Size**: S

- [ ] Checkpoint: run tests, review diff, verify scope

- [ ] 4.4 Route gen-eval and playwright-validator defaults through `API_BASE_URL` and `UI_ORIGIN`
  **Spec scenarios**: agent-coordinator.5 (Downstream phases read the contract)
  **Dependencies**: 4.3
  **Files**: packages/gen-eval/src/gen_eval/coordinator.py, packages/gen-eval/src/gen_eval/orchestrator.py, skills/playwright-validator/scripts/generator.py, skills/playwright-validator/scripts/runner.py
  **Size**: S

- [ ] 4.5 Write kanban-viz tests — `UI_PORT` with `strictPort`, `VITE_COORDINATOR_URL` from env, defaults when unset, e2e orchestrator uses leased `API_BASE_URL`
  **Spec scenarios**: coordinator-kanban-viz.2 (Dev server started from a lease env), coordinator-kanban-viz.2 (Dev server started without a lease env), coordinator-kanban-viz.1 (Two sweeps run concurrently)
  **Dependencies**: 4.4
  **Files**: apps/kanban-viz/src/__tests__/vite-config.test.ts, apps/kanban-viz/src/__tests__/e2e.integration.test.tsx
  **Size**: S

- [ ] 4.6 Implement `UI_PORT` in `vite.config.ts`, align the App and e2e defaults on 8081, and route `make e2e-kanban` through `port-lease acquire`
  **Dependencies**: 4.5
  **Files**: apps/kanban-viz/vite.config.ts, apps/kanban-viz/src/App.tsx, apps/kanban-viz/package.json, agent-coordinator/scripts/e2e_kanban.sh, agent-coordinator/Makefile
  **Size**: S

- [ ] 4.7 Update docs — worktree guide, local migration runbook, kanban README, live-service-testing notes on the lease env
  **Dependencies**: 4.6
  **Files**: docs/guides/worktree-management.md, docs/local-migration.md, docs/kanban-viz/README.md, docs/guides/workflow.md
  **Size**: S

- [ ] Checkpoint: run tests, review diff, verify scope

## 5. Integration (wp-integration)

- [ ] 5.1 Merge package branches and run `install.sh` so `skills/shared/port_lease.py` and changed skills are mirrored
  **Design decisions**: D11
  **Dependencies**: 2.12, 3.9, 4.7
  **Files**: .claude/skills/**, .agents/skills/**
  **Size**: XS

- [ ] 5.2 Add the contract keys to the dispatch env allowlist if `skills/shared/dispatch_env.py` exists, else record the obligation in `deferred-tasks.md`
  **Design decisions**: D10
  **Dependencies**: 5.1
  **Files**: skills/shared/dispatch_env.py, openspec/changes/standardize-port-leases/deferred-tasks.md
  **Size**: XS

- [ ] 5.3 Run the full test suites (coordinator unit and integration, skills, kanban-viz) and the port-literal gate; fix regressions
  **Dependencies**: 5.2
  **Files**: (no new files)
  **Size**: S

- [ ] 5.4 Run a two-agent concurrent `validate-feature` on one host and record the distinct blocks and compose projects in `validation-report.md`
  **Spec scenarios**: coordinator-kanban-viz.1 (Two sweeps run concurrently), agent-coordinator.1 (Successful port allocation)
  **Dependencies**: 5.3
  **Files**: openspec/changes/standardize-port-leases/validation-report.md
  **Size**: S

- [ ] Checkpoint: run tests, review diff, verify scope

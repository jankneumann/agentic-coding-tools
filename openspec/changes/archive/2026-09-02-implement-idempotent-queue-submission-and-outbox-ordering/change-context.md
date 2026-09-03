# Change Context: implement-idempotent-queue-submission-and-outbox-ordering

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| agent-coordinator.1 | specs/agent-coordinator/spec.md — Work Queue | Unkeyed compatibility plus atomic keyed submit/replay and full-generation head | --- | D1, D2 | agent-coordinator/database/migrations/035_work_queue_projection.sql; agent-coordinator/src/work_queue.py | test_work_queue.py; integration/postgres/test_work_queue_postgres.py | pass 59fdb05f — fresh migration, asyncpg retry, and concurrent canonical replay verified live |
| agent-coordinator.2 | specs/agent-coordinator/spec.md — Loop-State Projection Reconciliation | Cancel stale active rows and ensure authoritative current generation | --- | D3 | agent-coordinator/database/migrations/035_work_queue_projection.sql; agent-coordinator/src/work_queue.py; agent-coordinator/src/coordination_api.py | test_coordination_api.py; integration/postgres/test_work_queue_postgres.py | pass 59fdb05f — live reconciliation advanced the head and cancelled the stale UUID |
| agent-coordinator.3 | specs/agent-coordinator/spec.md — Projection Transport Parity | HTTP, direct/proxy MCP, and CLI map one explicit key and failure envelope | --- | D7 | agent-coordinator/src/coordination_api.py; agent-coordinator/src/coordination_mcp.py; agent-coordinator/src/http_proxy.py; agent-coordinator/src/coordination_cli.py | test_mcp_work_projection.py; test_http_proxy.py; test_coordination_cli_axi.py | pass 59fdb05f — live HTTP plus direct/proxy MCP and CLI transport suites passed |
| agent-coordinator.4 | specs/agent-coordinator/spec.md — Projection Migration Preflight | Reject unsafe legacy identities before index/function changes | openspec/contracts/agent-coordinator/openapi/work-queue.yaml | D8 | agent-coordinator/database/migrations/035_work_queue_projection.sql | test_work_queue.py; integration/postgres/test_work_queue_postgres.py | pass 59fdb05f — explicit transaction encloses lock, preflight, and DDL; runner normalization tested |
| coordination-bridge.1 | specs/coordination-bridge/spec.md — Work Projection Helper Envelope | No-raise bounded submit/reconcile bridge helpers preserve caller truth | --- | D2, D6 | skills/coordination-bridge/scripts/coordination_bridge.py | skills/tests/coordination-bridge/test_projection_helpers.py | pass 59fdb05f — affected skill suite 460 passed |
| skill-workflow.1 | specs/skill-workflow/spec.md — Outbox-Ordered Optional Queue Projection | Persist first, reconcile on resume, and remain coordinator-free without callbacks | --- | D4, D5, D6 | skills/autopilot/scripts/autopilot.py | skills/tests/autopilot/test_projection_seam.py | pass 59fdb05f — persist-first and callback-absence regressions passed |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Database owns identity | Migration 035 partial unique expression index | Concurrency invariant is not an application check-then-insert race |
| D2 | Preserve submit compatibility | Optional service/API key and additive result fields | Existing unkeyed callers keep independent inserts |
| D3 | Reconcile atomically | One advisory-locked RPC transaction | Stale cancellation and current-row convergence cannot interleave per change |
| D4 | Project after persistence | `persist_and_project` seam | Durable truth survives callback/process failure |
| D5 | Dependency-injected tier isolation | Callbacks default to `None` | Local-parallel and sequential paths make zero coordinator calls |
| D6 | Queue response is non-authoritative | Resume callback consumes state but cannot mutate it | Preserves the ri-07 direction-of-truth invariant |
| D7 | Explicit transport mappings | HTTP Problems and MCP/CLI discriminated envelopes | Denials cannot masquerade as successful null-ID payloads |
| D8 | Deterministic migration preflight | Locked validation with SQLSTATE 23514/23505 | Operators can remediate and rerun the unchanged migration |

## Coverage Summary

- **Requirements traced**: 6/6
- **Tests mapped**: 6 requirements have at least one test
- **Evidence collected**: 6/6 requirements pass
- **Gaps identified**: none on the ri-08 surface; unrelated legacy PostgreSQL claim-path and architecture-refresh warnings remain
- **Deferred items**: Live phase-mirroring registration remains ri-09 scope

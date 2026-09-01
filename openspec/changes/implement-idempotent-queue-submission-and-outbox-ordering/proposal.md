# Implement Idempotent Queue Submission and Outbox Ordering

## Why

`loop-state.json` is the authoritative execution record, while the coordinator work queue is only a derived distribution projection. The current `submit_task` RPC always inserts, so a retry after a crash can create duplicate work; the current autopilot loop also has no reusable persist-then-project seam or resume reconciliation hook. ri-08 turns ri-07's documented truth/projection contract into enforceable infrastructure without enabling ri-09's live phase mirroring.

## What Changes

- Make projection submissions with a complete `(change_id, phase, iteration)` key atomic and submit-if-absent in PostgreSQL while preserving ordinary queue submission behavior.
- Return the canonical task ID plus whether the call created or deduplicated the task through the service, HTTP API, and coordination bridge.
- Add an atomic reconciliation operation that cancels stale active projection entries for a change and ensures the current loop-state key exists.
- Add an optional autopilot persistence/reconciliation seam whose ordering is always `save_state` first, projection second, including resume re-derivation from the loaded loop-state.
- Keep the default/local-parallel/sequential path coordinator-free; no caller registers live transition mirroring in this change.
- Extend the truth/projection guide with the implemented interfaces and the explicit ri-09 boundary.

## Scope

### In scope

- PostgreSQL migration and RPC behavior for projection-key uniqueness, submit-if-absent, and reconciliation.
- Coordinator service/API and script bridge contracts.
- Optional autopilot outbox/reconciliation seam and failure-tolerant ordering.
- Concurrency, crash-window, resume, and coordinator-free regression tests.

### Out of scope

- Live autopilot phase mirroring or kanban-viz updates (ri-09).
- Changing queue claims into authoritative phase state.
- Adding coordinator requirements to local-parallel or sequential execution.
- General-purpose queue deduplication for submissions without the projection key.

## Non-Functional Requirements

| Attribute | Metric | Target | Verification |
|---|---|---|---|
| Concurrency correctness | Rows for one complete projection key after concurrent submissions | Exactly 1 row and one canonical task ID | PostgreSQL integration test |
| Crash safety | Durable loop-state after a projection callback fails | State transition remains persisted; resume converges to one current row | Autopilot crash-window test |
| Availability | Coordinator calls in default/local-parallel/sequential paths | 0 | Existing tier tests plus explicit no-call regression |
| Compatibility | Existing unkeyed `/work/submit` behavior | Continues to create independent tasks | API and service regression tests |

## Approaches Considered

### Approach 1 — Atomic PostgreSQL submit-if-absent (Recommended)

Create a partial unique expression index over the three JSONB key fields and use one database-side insert-or-conflict operation, followed by canonical-row lookup, inside the RPC. Reconciliation executes in one database transaction and the filesystem-to-queue ordering remains an injected application seam.

**Pros**

- The unique index arbitrates concurrent writers at the only shared authority for queue rows.
- `INSERT ... ON CONFLICT` is documented by PostgreSQL as atomic under concurrency.
- Preserves the existing JSONB payload and unkeyed queue API.
- Makes retry and resume convergence testable against real PostgreSQL.

**Cons**

- Adds a migration and Postgres-specific expression-index contract.
- Filesystem persistence and queue projection cannot share one transaction, so resume reconciliation remains necessary.

**Effort**: L

### Approach 2 — Application check-then-insert

Query for the key in Python before calling the existing insert RPC.

**Pros**

- Small service-layer change.
- No schema migration.

**Cons**

- Races when two submitters observe absence concurrently.
- Cannot provide the roadmap's exactly-one-row integration outcome.

**Effort**: S

### Approach 3 — Advisory lock around the existing RPC

Serialize keyed submissions with a PostgreSQL advisory lock derived from the tuple.

**Pros**

- Avoids an expression index.
- Can serialize broader reconciliation work.

**Cons**

- Session-scoped locks are unsafe through pooled connections and are not exposed cleanly by the current `DatabaseClient` RPC surface.
- Adds lock-key collision and release-failure concerns where a unique index directly models the invariant.

**Effort**: M

### Selected Approach

The approved roadmap direction selects **Approach 1: Atomic PostgreSQL submit-if-absent**. It is the only considered design that makes duplicate prevention a database invariant while preserving coordinator-free fallback tiers.

## Source Basis

- PostgreSQL `INSERT ... ON CONFLICT` supports expression/partial-index inference and atomic conflict handling: https://www.postgresql.org/docs/current/sql-insert.html#SQL-ON-CONFLICT
- Unique expression indexes can enforce constraints derived from JSONB fields: https://www.postgresql.org/docs/current/indexes-expressional.html
- PostgreSQL transaction semantics support a short database transaction for stale-row cancellation plus current-row convergence: https://www.postgresql.org/docs/current/tutorial-transactions.html

## Approval Record

Discovery, direction, and complete-plan authorization are inherited from the approved `roadmap-supervisor-orchestration` ri-08 item. The fixed choices are the ri-07 truth/projection contract, atomic PostgreSQL submit-if-absent semantics, coordinator-free fallback tiers, and ri-09 live mirroring remaining out of scope.

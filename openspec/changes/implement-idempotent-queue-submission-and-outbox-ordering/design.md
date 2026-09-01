# Design — Idempotent Queue Projection Infrastructure

## Context

The queue currently accepts arbitrary `input_data` and always inserts. Autopilot persists `LoopState` after transitions but has no queue-projection dependency by default. ri-07 established that the filesystem state is authoritative and queue rows must be reproducible from it. This design provides the atomic database and ordering seams that ri-09 can later compose into live phase mirroring.

The local coordinator stack uses ParadeDB `v0.22.2` (PostgreSQL-compatible); Python is `>=3.12`, with FastAPI `>=0.136.1`, asyncpg `>=0.31.0`, and httpx `>=0.28.1`. The SQL contract relies on stable PostgreSQL `ON CONFLICT`, JSONB extraction, partial expression indexes, and transaction behavior rather than a ParadeDB extension.

## Decisions

### D1 — A partial unique expression index owns projection identity

Migration `035_work_queue_projection.sql` creates a unique index on:

```sql
(input_data ->> 'change_id'),
(input_data ->> 'phase'),
((input_data ->> 'iteration')::integer)
```

only where all three JSONB fields exist and `iteration` is a JSON number. Unkeyed and partially keyed tasks retain existing independent-insert behavior. The service validates a complete projection key before invoking keyed behavior, so malformed projection attempts fail without relying on a cast error.

PostgreSQL documents expression indexes as constraint-capable and `ON CONFLICT` as an atomic concurrency arbiter:

- https://www.postgresql.org/docs/current/indexes-expressional.html
- https://www.postgresql.org/docs/current/sql-insert.html#SQL-ON-CONFLICT

### D2 — The existing submit surface remains backward compatible

`submit_task` gains conditional submit-if-absent behavior rather than forcing callers onto a second general submission API. A complete projection key returns the canonical row with `created=true|false`; submissions without the complete key keep creating fresh rows and return `created=true`. `SubmitResult`, `/work/submit`, and `try_submit_work` carry `created` and `deduplicated` without removing existing fields.

On conflict the RPC retrieves the row selected by the same three expressions and returns its ID. The database integration test starts concurrent transactions to prove every caller observes the same canonical ID and exactly one row remains.

### D3 — Reconciliation is one short database transaction

`reconcile_work_projection` accepts the desired tuple and task payload. In one RPC transaction it:

1. marks stale `pending`, `claimed`, or `running` projection rows for the same `change_id` as `cancelled`, with a machine-readable `cancelled_by_projection_reconcile` result;
2. submit-if-absent creates or selects the current tuple;
3. returns the canonical current task ID, `created`, and sorted cancelled task IDs.

Terminal rows remain immutable. Lock acquisition follows one statement/order per table and the transaction contains no external calls, following PostgreSQL guidance to keep lock-holding transactions short: https://www.postgresql.org/docs/current/tutorial-transactions.html

### D4 — Projection is an optional post-persistence dependency

Autopilot receives an optional `queue_projection_fn`. A small helper performs:

```text
save_state(state, path)
queue_projection_fn(state)  # only after save succeeds
```

Projection failure never rolls back or rewrites loop-state. The helper surfaces a structured warning/result so callers can observe degradation, while the next resume repairs the projection.

After loading an existing loop-state, the same callback runs in reconciliation mode before any phase execution or gate early-return. It receives only authoritative fields derived from `LoopState`; its result is never used to mutate the state.

### D5 — Tier isolation is dependency injection, not environment inference

The callback defaults to `None`. Autopilot, local-parallel, and sequential paths do not import the coordinator bridge, probe availability, or make HTTP calls when it is absent. Coordinated callers may inject the adapter. ri-09 owns registering that adapter for every live phase transition; ri-08 only establishes and tests the reusable ordering/reconciliation seam.

### D6 — Reconciliation never reads queue truth back into loop-state

The bridge adapter serializes `(change_id, current_phase, total_iterations)` from the passed `LoopState`, calls `/work/reconcile`, and returns projection metadata. It does not expose a phase/iteration result to the state machine and cannot update `LoopState`. The ri-07 AST invariant remains mandatory.

## Failure Matrix

| Failure point | Durable truth | Queue state | Recovery |
|---|---|---|---|
| State save fails | Prior loop-state | Unchanged | Abort before projection |
| Process dies after save | New loop-state | Possibly missing current row | Resume reconciliation submits current row |
| Projection HTTP/RPC fails | New loop-state | Old/missing rows possible | Report degradation; resume retries |
| Duplicate submitters race | Same loop-state-derived key | Unique index admits one row | All callers receive canonical ID |
| Resume finds stale active rows | Loaded loop-state | Stale plus missing/current rows | Atomic reconcile cancels stale and ensures current |

## Compatibility and Migration

- The migration number follows current `034_handoff_supervisor_record.sql`.
- Existing rows are not backfilled; the unique index creation must fail clearly if legacy duplicate complete keys already exist, and the migration test pins the expected preflight behavior.
- Existing response consumers remain compatible because new fields are additive.
- No OpenAPI endpoint is removed.

## Test Strategy

- PostgreSQL integration tests provide RED evidence for concurrent duplicate submission and reconciliation.
- Service/API tests pin additive response fields and legacy unkeyed behavior.
- Autopilot unit tests pin save-before-project call order, no projection after failed save, failure tolerance, and resume reconciliation.
- Existing tier and AST-invariant tests prove coordinator-free fallback and one-way authority.

## Explicit ri-09 Boundary

This change does not register a phase-transition publisher, change kanban-viz polling, or promise live phase latency. ri-09 will inject the adapter at the coordinated execution boundary and verify live mirroring. ri-08 supplies the atomic contract and crash-safe composition seam only.

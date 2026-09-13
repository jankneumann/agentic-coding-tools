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
(input_data ->> 'transition_sequence')
```

only where all three reserved JSONB fields exist and `transition_sequence` is a JSON number. Because every indexed expression is text-valued, malformed fractional or huge legacy numbers cannot throw during index evaluation. Public boundaries accept one optional complete `projection_key`; `change_id` is bounded to 128 lowercase kebab characters, `phase` is an autopilot phase enum, and `transition_sequence` is a strict non-boolean integer in `0..2147483647`. The service alone materializes reserved JSONB identity fields and rejects `change_id`, `phase`, or `transition_sequence` inside caller `input_data`. Unkeyed tasks retain independent-insert behavior.

PostgreSQL documents expression indexes as constraint-capable and `ON CONFLICT` as an atomic concurrency arbiter:

- https://www.postgresql.org/docs/current/indexes-expressional.html
- https://www.postgresql.org/docs/current/sql-insert.html#SQL-ON-CONFLICT

### D2 — The existing submit surface remains backward compatible

`submit_task` gains conditional submit-if-absent behavior rather than forcing callers onto a second general submission API. A complete projection key returns the canonical row with `created=true|false`; submissions without the complete key keep creating fresh rows and return `created=true`. `SubmitResult`, `/work/submit`, and `try_submit_work` carry `created` and `deduplicated` without removing existing fields.

Both keyed `submit_task` and `reconcile_work_projection` first acquire `pg_advisory_xact_lock(hashtextextended(change_id, 0))` and consult the per-change high-water row in `work_queue_projection_heads`. The first keyed submit establishes the full `(phase, transition_sequence)` head. Only an exact same-generation retry may insert-or-select the canonical row. A lower sequence is rejected as `stale_projection`, an equal-sequence/different-phase request as `projection_generation_mismatch`, and a higher sequence as `reconciliation_required`; only reconciliation may advance the head. This prevents a delayed submit for N-1 from recreating active work after reconciliation has committed N. Keyed insert publishes and uses the exact target `ON CONFLICT ((input_data ->> 'change_id'), (input_data ->> 'phase'), (input_data ->> 'transition_sequence')) WHERE input_data ? 'change_id' AND input_data ? 'phase' AND input_data ? 'transition_sequence' AND jsonb_typeof(input_data -> 'transition_sequence') = 'number' DO NOTHING`, then performs canonical lookup with the same expressions and predicate. Real PostgreSQL tests cover same-key, equal-sequence/different-phase, and different-sequence submit/reconcile races plus malformed legacy rows.

### D3 — Reconciliation is one short database transaction

`reconcile_work_projection` accepts the desired tuple and task payload. In one RPC transaction it:

1. rejects a desired sequence below the locked high-water mark, otherwise advances both `phase` and `transition_sequence` in `work_queue_projection_heads` to the authoritative generation;
2. marks stale `pending`, `claimed`, or `running` projection rows for the same `change_id` as `cancelled`, with a machine-readable `cancelled_by_projection_reconcile` result;
3. submit-if-absent creates or selects the current tuple;
4. returns the canonical current task ID, `created`, and sorted cancelled task IDs.

Terminal rows remain immutable. If the canonical current key already has `completed`, `failed`, or `cancelled` status, reconciliation treats that generation as already satisfied and returns it with `created=false`; it never manufactures a second row for the same transition sequence. Lock acquisition follows one statement/order per table and the transaction contains no external calls, following PostgreSQL guidance to keep lock-holding transactions short: https://www.postgresql.org/docs/current/tutorial-transactions.html

### D4 — Projection is an optional post-persistence dependency

Autopilot receives an optional `queue_projection_fn`. A small helper performs:

```text
save_state(state, path)
queue_projection_fn(state)  # only after save succeeds
```

Projection failure never rolls back or rewrites loop-state. The helper surfaces a structured warning/result so callers can observe degradation, while the next resume repairs the projection.

After loading an existing loop-state, the same callback runs in reconciliation mode before any phase execution or gate early-return. It receives `(change_id, current_phase, total_iterations)` from `LoopState`, mapping `total_iterations` to `transition_sequence`; phase-local `iteration` is never projected. Its result is never used to mutate the state. Phase revisits therefore remain distinct generations.

### D5 — Tier isolation is dependency injection, not environment inference

The callback defaults to `None`. Autopilot, local-parallel, and sequential paths do not import the coordinator bridge, probe availability, or make HTTP calls when it is absent. Coordinated callers may inject the adapter. ri-09 owns registering that adapter for every live phase transition; ri-08 only establishes and tests the reusable ordering/reconciliation seam.

### D6 — Reconciliation never reads queue truth back into loop-state

The bridge adapter serializes `(change_id, current_phase, transition_sequence=total_iterations)` from the passed `LoopState`, calls `/work/reconcile`, and returns projection metadata. It does not expose a phase/iteration result to the state machine and cannot update `LoopState`. The ri-07 AST invariant remains mandatory.

### D7 — Transport mappings and failures are explicit

HTTP success is a `ProjectionMutationSuccess` with `success=true`; authentication, policy, and validation failures use 4xx RFC 7807 `Problem` responses and never satisfy the success schema. Direct MCP, HTTP-proxy MCP, the coordination bridge, and `coordination-cli work submit|reconcile` expose the same projection-key fields and success metadata. MCP/CLI no-raise failures use a discriminated `{success:false, reason}` envelope and omit success-only UUID/creation fields.

`/work/reconcile` is authorized with the existing `submit_work` policy operation and adds `context.mode="reconcile"`; reconciliation is the idempotent projection form of queue submission, not a new privilege class. API, direct MCP, proxy MCP, and CLI tests pin this mapping.

### D8 — Migration preflight fails deterministically and retries cleanly

Migration 035 takes a short `SHARE ROW EXCLUSIVE` lock, checks for partial, malformed, out-of-range, or duplicate complete reserved keys, and aborts with documented SQLSTATE/diagnostic queries before creating the index. The transaction rolls back on failure; operators quarantine or normalize reported rows and rerun the unchanged migration. Seeded migration tests cover malformed, duplicate, clean retry, and rollback behavior.

### D9 — Raw SQL bootstrap records the same migration ledger as the Python runner

The official ParadeDB/PostgreSQL init path executes every `*.sql` file directly, so it must also leave the checksum ledger that `ensure_schema` expects. A lexically final executable init helper, `999_record_schema_migrations.sh`, runs only after all earlier SQL files succeed. It discovers every SQL migration, computes the byte-level SHA-256 used by Python `_checksum`, and records the complete set in one fail-fast transaction. Re-execution is idempotent. The Python runner continues to discover only `*.sql`, so it ignores the helper itself.

CI invokes the same helper immediately after its `ON_ERROR_STOP` SQL loop instead of duplicating ledger logic in workflow YAML. A failed SQL file terminates the loop before the helper can run, preventing a partially applied bootstrap from being falsely marked complete.

Migration-specific `UniqueViolationError` suppression was rejected. A live replay of migration 019 showed that its transaction can roll back while three legacy profile names remain, so recording that filename as applied would preserve semantic drift. Historical migrations remain unchanged and every non-recorded failure continues to propagate.


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
- Existing rows are not backfilled. Preflight reports offending task IDs and categories with deterministic SQLSTATE `23514` for malformed/partial/out-of-range keys and `23505` for duplicates; the transaction fully rolls back so remediation and unchanged retry are safe. The short table lock prevents new keyed writes between preflight and index creation.
- Existing response consumers remain compatible because success fields are additive and failures retain the established transport-specific error envelope.
- No OpenAPI endpoint is removed.

- Fresh raw-SQL bootstrap now records the same 38-file checksum ledger consumed by the Python runner. This affects bootstrap bookkeeping only; no historical SQL checksum changes.
## Test Strategy

- PostgreSQL integration tests provide RED evidence for concurrent duplicate submission and reconciliation.
- Service/API tests pin strict bounds, reserved-key rejection, additive success fields, 4xx Problem failures, terminal-current semantics, and legacy unkeyed behavior.
- Direct MCP, proxy MCP, and CLI tests pin keyed submit/reconcile mappings and failure envelopes.
- Autopilot unit tests pin save-before-project call order, no projection after failed save, failure tolerance, and resume reconciliation.
- Existing tier and AST-invariant tests prove coordinator-free fallback and one-way authority.

- Bootstrap tests pin SQL-only discovery, exact checksum parity, idempotent tracking, fail-fast success-only ordering, and the CI call site. Fresh PostgreSQL validation proves `ensure_schema` has no follow-up apply set.
## Explicit ri-09 Boundary

This change does not register a phase-transition publisher, change kanban-viz polling, or promise live phase latency. ri-09 will inject the adapter at the coordinated execution boundary and verify live mirroring. ri-08 supplies the atomic contract and crash-safe composition seam only.

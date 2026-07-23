# Design: Revision-aware semantic index registry

## Context

The existing code-search implementation has two identity assumptions:

1. `code_search_registry.repo_slug` is the only registry key.
2. `chunk_table_name(repo_slug)` yields one mutable table per repository.

That is sufficient for the original disabled-by-default prototype, but it
cannot prove freshness for an exact Git revision or isolate a branch-local
index. This design introduces the identity and lifecycle boundary only. The
dependent incremental-indexing change will create storage and drive the
lifecycle; the fail-closed query change will consume only ready records.

## Decisions

### D1 — Separate repository metadata from index lifecycle records

`code_search_registry` remains the repository configuration/compatibility
table. A new `code_search_indexes` table is authoritative for an individual
semantic index.

The index natural key is:

```text
(repo_slug, namespace_kind, namespace_key, source_revision,
 embedder_model, embedding_dim)
```

This permits the same revision to be indexed with a changed embedding contract
without silently reusing incompatible vectors. `index_id` is the durable
operation handle.

### D2 — Persist exact object IDs, not refs

`source_revision` accepts only lowercase full Git object IDs: 40 hex characters
for SHA-1 or 64 for SHA-256. Callers resolve `main`, branch refs, and worktree
HEADs before calling the registry. This makes identity independent of later ref
movement.

### D3 — Model namespaces explicitly

`namespace_kind` is one of:

- `main` — canonical default-branch history; `namespace_key` must be `main`
- `feature` — a feature/ref-local index; key is the stable change or ref identity
- `work_package` — an isolated worker/checkpoint index; key is the package identity

The human-readable key is metadata, never interpolated into SQL. Every row gets
a stable `storage_key` of `i_<index_id-without-hyphens>`. Future chunk tables use
`code_chunks__<storage_key>`, which stays below PostgreSQL's identifier limit
and cannot collide across namespaces.

### D4 — Use leases for concurrent lifecycle ownership

Lifecycle states are:

```text
pending -> indexing -> ready
                    -> failed
                    -> not_configured
pending/indexing/failed/not_configured -> deleting -> deleted
```

`ensure_index` uses `INSERT ... ON CONFLICT ... RETURNING` on the natural key,
so duplicate requests receive the same record. `claim_index` atomically assigns
a new lease token and increments `attempt_count` when the row is pending,
retryable, or has an expired lease. `mark_ready`, `mark_failed`, and
`mark_not_configured` require the current lease token. A late worker therefore
cannot overwrite a newer attempt.

`ready` is immutable for a given natural key. A new embedder contract produces a
new row.

### D5 — Promote canonical main by guarded compare-and-swap

`code_search_registry.canonical_index_id` points to a ready `main` index for the
same `repo_slug`. Promotion locks the repository row, validates the candidate,
and optionally compares the current pointer with
`expected_current_index_id`. A database trigger enforces the same repository,
`main` namespace, and `ready` status even when SQL bypasses the Python module.

Feature and work-package rows can never be canonical. A new main revision is
prepared in isolated storage and becomes visible only after the pointer update.

### D6 — Make garbage collection conservative and retryable

An index is eligible only when all are true:

- namespace kind is `feature` or `work_package`;
- it is not referenced by any canonical pointer;
- it is not actively leased;
- `retention_until` is non-null and in the past;
- state is terminal or abandoned after lease expiry.

The operation claims a candidate by moving it to `deleting`, invokes an injected
storage deleter using `storage_key`, then marks it `deleted`. A deletion failure
returns the row to `failed` with `last_error` so it remains inspectable and
retryable. Main rows are excluded in both SQL and application validation.

### D7 — Preserve the legacy path as explicitly non-authoritative

This change does not rewrite `CodeSearchService`, `index_repo`, or
`chunk_table_name(repo_slug)`. Existing behavior remains behind its current
feature flag. The new module and contract are the dependency boundary for
`complete-incremental-semantic-indexing`; the later fail-closed query change
will make `canonical_index_id` and exact-revision lookup authoritative.

## Component Shape

```text
packages/code-search/src/code_search_pkg/
  registry.py        # types, validation, async registry operations
  identifiers.py     # legacy repo slug + new storage-key table naming

agent-coordinator/database/migrations/
  029_revision_aware_code_search_indexes.sql

code_search_registry (repository metadata)
          |
          | canonical_index_id
          v
code_search_indexes (exact revision + namespace + lifecycle)
          |
          | storage_key
          v
code_chunks__i_<uuidhex>       [created by ri-02, not this change]
```

## Registry Record Contract

Each serialized record contains:

- `index_id` and `storage_key`
- `repo_slug`
- `namespace_kind` and `namespace_key`
- `source_revision`
- `embedder_model` and `embedding_dim`
- `status`, `attempt_count`, and optional lease fields
- `chunk_count`, `last_error`, and timestamps
- optional `retention_until` and `deleted_at`

The JSON Schema in `contracts/index-record.schema.json` is the handoff contract
for the incremental indexer and exact-revision query work.

## Error Semantics

- Invalid repo slug, namespace, revision, or embedding dimension: `ValueError`
  before SQL.
- Missing index identity: `IndexNotFoundError`.
- Non-current lease token: `IndexLeaseConflictError`.
- Illegal lifecycle transition: `IndexStateConflictError`.
- Invalid canonical candidate or compare-and-swap mismatch:
  `CanonicalPromotionError`.
- Storage deletion failure: row remains non-deleted with a durable error.

These are internal library exceptions in this change. HTTP/MCP mappings belong
to `expose-fail-closed-semantic-code-search`.

## Verification Strategy

- Pure unit tests cover validation, natural-key stability, storage-key naming,
  record decoding, transition guards, and GC eligibility.
- Structural migration tests run without a database and reject destructive DDL.
- Live Postgres tests apply the migration twice, exercise duplicate concurrent
  ensures, lease takeover, stale completion rejection, canonical constraints,
  and GC exclusion for main/canonical records.
- Existing code-search unit tests remain green, proving the compatibility path
  is not broken.

## Migration and Rollout

1. Apply the additive migration.
2. Deploy the new registry module unused by production query paths.
3. Let ri-02 write revision-aware records and isolated chunk storage.
4. Let ri-03 switch queries to exact/canonical records and fail closed.
5. Remove legacy freshness columns only in a later deprecation change after all
   consumers are migrated.

No existing chunk table is copied, renamed, or dropped in this change.

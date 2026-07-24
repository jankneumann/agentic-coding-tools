# Add revision-aware semantic index registry

> Parent roadmap: `project-context-refresh-lifecycle`
> Change ID: `add-revision-aware-semantic-index-registry`
> Effort: M
> Priority: 1
> Approval: inherited from `$autopilot-roadmap project-context-refresh-lifecycle`

## Why

The existing semantic-search foundation has a single mutable
`code_search_registry` row and a single `code_chunks__<repo_slug>` table per
repository. It can record a `last_indexed_commit`, but it cannot distinguish a
canonical main index from a feature or work-package index, cannot keep lifecycle
history for multiple revisions, and cannot safely arbitrate concurrent
indexing attempts. Consequently, a search result cannot yet prove which Git
revision produced it, and branch-local indexing could overwrite the index used
for main.

The project-context refresh lifecycle needs a durable source of truth before
incremental indexing, fail-closed querying, and context injection can be built
on top of semantic search.

## What Changes

- Add an authoritative `code_search_indexes` registry keyed by repository,
  namespace kind, namespace key, exact Git object ID, embedder model, and
  embedding dimension.
- Give every index a stable UUID and storage key so its eventual chunk table is
  isolated from all other namespaces and revisions.
- Define lifecycle states, lease-based ownership, attempt tracking, completion
  metadata, and guarded state transitions for concurrent index workers.
- Add an explicit canonical pointer to `code_search_registry`; only a ready
  `main` namespace for the same repository may be promoted.
- Add deterministic garbage-collection eligibility for expired feature and
  work-package indexes while making canonical main indexes ineligible.
- Add a light, asyncpg-only registry module under `packages/code-search` for
  identity construction, idempotent ensure/claim operations, guarded
  completion, canonical promotion, and garbage-collection candidate selection.
- Keep the current `code_search_registry` columns and repo-slug chunk naming as
  a compatibility bridge. Follow-up changes migrate indexing and querying to
  the new index identity; this change does not claim that the unfinished
  `index_repo` pipeline is operational.

## Scope

### In scope

- Postgres schema and migration for revision-aware index records.
- Pure identity and lifecycle types plus async registry persistence.
- Exact-revision validation for SHA-1 and SHA-256 Git object IDs.
- Canonical-promotion and garbage-collection safety rules.
- Tests and operator documentation for the registry contract.

### Out of scope

- Executing the CocoIndex pipeline (`complete-incremental-semantic-indexing`).
- Creating or populating revision-specific chunk tables.
- Exposing exact-revision search through MCP/HTTP
  (`expose-fail-closed-semantic-code-search`).
- Injecting semantic results into agent context.
- Scheduling garbage collection automatically; this change supplies the safe
  operation and candidate rules.

## Dependencies

- None.

Downstream roadmap dependencies:

- `complete-incremental-semantic-indexing`
- `implement-project-context-refresh-orchestration`
- `expose-fail-closed-semantic-code-search` (transitively)

## Approaches Considered

### Approach A — Mutate the existing repository row into a composite registry

Change the primary key of `code_search_registry` from `repo_slug` to a
repository/namespace/revision composite and update existing readers in place.

**Pros**

- Uses one table.
- Avoids a second registry name.

**Cons**

- Breaks current lookup assumptions in `agent-coordinator/src/code_search.py`.
- Requires a destructive primary-key migration and immediate coordinated
  rollout across index and query paths.
- Conflates repository configuration with individual index attempts.

**Effort:** M

### Approach B — Add an authoritative index table beside repository metadata (Recommended)

Retain `code_search_registry` as repository configuration and compatibility
metadata. Add `code_search_indexes` for immutable identity plus lifecycle state,
and add a guarded `canonical_index_id` pointer from the repository row.

**Pros**

- Additive migration with a safe rollout path.
- Separates repository configuration from revision-specific lifecycle records.
- Preserves current readers until downstream changes deliberately switch over.
- Supports history, retries, branch isolation, and exact provenance.

**Cons**

- Temporarily keeps legacy freshness fields beside the new source of truth.
- Requires joins for exact query provenance.
- Needs an explicit compatibility-removal follow-up after downstream rollout.

**Effort:** M

### Approach C — Encode namespace and revision only in chunk-table names

Derive a table name from repo/ref/SHA and use Postgres catalog inspection as the
registry.

**Pros**

- Minimal schema work.
- Physical isolation is visible in table names.

**Cons**

- Cannot represent pending, failed, or not-configured attempts.
- Cannot safely coordinate concurrent owners or record errors.
- Git refs do not fit safely into SQL identifiers and Postgres identifiers are
  length-limited.
- Catalog presence is not proof that an index is complete or queryable.

**Effort:** S

## Selected Approach

Approach B is selected by the approved roadmap direction. It provides the
durable provenance and isolation the downstream lifecycle needs without
claiming that existing indexing or query surfaces are already revision-aware.

## Acceptance Outcomes

- The registry records exact source revision, namespace, embedder model,
  embedding dimension, chunk count, lifecycle status, attempt count, timestamps,
  and last error.
- Repeating the same repository/namespace/revision/model request returns the
  same durable index identity.
- Concurrent creation and completion attempts preserve one authoritative record;
  only the current lease holder can publish a terminal result.
- Main, feature, and work-package identities always have distinct storage keys
  and cannot overwrite or masquerade as one another.
- Canonical promotion rejects non-main, incomplete, cross-repository, and stale
  compare-and-swap requests.
- Garbage collection can remove eligible expired noncanonical storage while
  never selecting the canonical pointer or any `main` namespace.
- Existing semantic-search readers remain compatible until the dependent
  indexing and fail-closed query changes adopt the new registry.

## Risks

- The repository temporarily has legacy freshness columns and the new canonical
  source of truth. Documentation and APIs must label the legacy columns
  non-authoritative.
- A worker crash can leave an index `indexing`; bounded leases and takeover after
  expiry prevent permanent deadlock.
- Storage deletion and registry tombstoning are two effects. The garbage
  collector must delete storage first and tombstone only after successful
  deletion so a failed delete is retryable.
- SHA validation supports 40- and 64-hex object IDs; abbreviated or symbolic
  refs are intentionally rejected at the persistence boundary.

## Rollback

Before downstream consumers adopt the table, rollback removes
`canonical_index_id` and drops `code_search_indexes`. After adoption, rollback
first points consumers back to legacy repo-slug behavior, then removes the new
schema. No existing chunk table is renamed or deleted by this change.

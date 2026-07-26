# Change: Expose fail-closed semantic code search

> Parent roadmap: `project-context-refresh-lifecycle`
> Roadmap item: `ri-03`
> Change ID: `expose-fail-closed-semantic-code-search`
> Effort: M
> Priority: 3

## Why

RI02 can now build immutable, revision-aware semantic indexes, but the
coordinator still reads the legacy mutable `code_chunks__<repo_slug>` table.
Neither HTTP nor MCP startup initializes the service, callers cannot request an
exact revision, responses contain no index provenance, and unresolved
work-package scopes silently become unrestricted.

This makes the current search surface both unusable for newly built indexes and
unsafe as coding context: a legacy table can be served without proving that its
contents match the caller's repository revision or read boundary.

## What Changes

- Replace the legacy query target with guarded selection of a ready RI02 index
  and address its immutable table only through a validated `storage_key`.
- Require an exact repository revision, explicit namespace, and authoritative
  scope on every search request. Non-main namespaces also require the exact
  index ID so multiple fingerprint variants cannot be selected arbitrarily.
- Return one discriminated response envelope for ready, revision mismatch,
  not-indexed, not-configured, unavailable, and scope-rejected states. Every
  non-ready state returns zero semantic hits and an exact-search fallback.
- Attach repository, revision, index, namespace, embedding-contract, and scope
  provenance to the response and every hit.
- Initialize a loop-owned query runtime for HTTP and direct MCP, expose a
  body-aware status surface, and shut down its pool safely.
- Add `CAN_CODE_SEARCH` to capability discovery. It is true only when the
  feature is enabled, the runtime and query provider are ready, and at least one
  compatible canonical index has usable published storage.
- Resolve work-package scope through a trusted resolver. Missing, malformed,
  stale, or empty authorization fails closed before embedding or storage reads.
- Require authenticated HTTP callers and bind every request to the validated
  coordinator principal before accepting caller-selected filters.
- Keep the feature default-off and preserve coordinator availability when
  optional database or embedding resources are unavailable.
- Replace Docker-only source copying with a supported monorepo package
  dependency whose asyncpg range is compatible with the coordinator, and prove
  imports in local and container-style environments.

## Selected Approach

Use a **strict v2 exact-index query boundary with structured operational
states**.

The service first resolves and validates scope, then selects the guarded
canonical or exact namespaced index, checks the requested revision and query
embedding contract, and only then embeds and queries. Expected operational
degradation is represented as a successful typed envelope so HTTP, direct MCP,
and HTTP-proxy MCP return identical evidence. No production path reads legacy
storage or chooses an arbitrary ready index.

## Approaches Considered

### Approach 1 — Strict v2 exact-index boundary (Recommended)

Require revision, namespace, and scope; query only RI02 storage; expose
structured fallback states and body-aware readiness.

- **Pros**: freshness is provable; scope is fail-closed; surfaces remain
  consistent during optional-resource degradation; directly supports RI12.
- **Cons**: intentionally breaks the default-off legacy request shape; requires
  coordinated API, MCP, startup, and discovery updates.
- **Effort**: M

### Approach 2 — Add revision fields to the legacy service

Keep the existing repo-slug table and compare its legacy
`last_indexed_commit` before search.

- **Pros**: smaller diff; minimal surface changes.
- **Cons**: cannot consume RI02 immutable storage or prove fingerprints,
  publication, canonicality, or namespace isolation; preserves unsafe
  fail-open scope behavior.
- **Effort**: S

### Approach 3 — Query the newest ready v2 index

Select the most recently completed ready row and report staleness after
retrieval.

- **Pros**: simple selection; can return approximate context when exact indexes
  lag.
- **Cons**: may expose stale or branch-isolated content; violates the roadmap's
  exact-revision requirement; encourages callers to treat mismatched hits as
  current.
- **Effort**: M

## Dependencies

- `ri-01` / `add-revision-aware-semantic-index-registry`
- `ri-02` / `complete-incremental-semantic-indexing`, including safe retry of
  guarded canonical promotion
- Postgres migration `030_incremental_code_search_indexes.sql`
- Explicit RI02-compatible query embedding configuration

## Acceptance Outcomes

- Coordinator HTTP and direct-MCP lifecycles initialize and close a loop-owned
  query runtime without making optional search failure fatal to the coordinator.
- `CAN_CODE_SEARCH` is false when disabled, uninitialized, unconfigured,
  unreachable, legacy-only, provider-incompatible, noncanonical, or missing
  usable storage; an HTTP status probe reports true only for usable v2 state.
- A ready exact-revision query reads only
  `code_chunks__<validated-storage-key>` and returns provenance-rich hits.
- A feature or work-package query without an exact index ID is rejected before
  registry access; an index ID that does not match repository, namespace,
  revision, and provider identity is non-ready.
- A requested revision mismatch, missing index, provider mismatch, missing
  table, or stale scope returns no semantic hits and an explicit exact-search
  fallback without calling the embedder or KNN backend when rejection can be
  determined earlier.
- Explicit and work-package scopes fail closed; deny rules override allow
  rules, caller path filters cannot widen authority, and unresolved scope never
  degrades to unrestricted search.
- HTTP, direct MCP, and HTTP-proxy MCP expose the same request and response
  contract with bounded validation and sanitized errors.
- HTTP search requires a valid coordinator principal; provider/database work
  has bounded time and concurrency, and metrics/logs record states without
  query text, source content, credentials, or DSNs.
- Legacy registry rows and `code_chunks__<repo_slug>` tables remain available
  for rollback diagnostics but are never query-authoritative.
- The coordinator imports `code_search_pkg` through its declared dependency in
  local, test, and production builds; the code-search package and coordinator
  resolve one supported asyncpg version.

## Impact

- **Affected specs**: `code-search`, `agent-coordinator`
- **Affected code**:
  `packages/code-search/src/code_search_pkg/query_pg.py`,
  `agent-coordinator/src/{code_search,coordination_api,coordination_mcp,http_proxy}.py`,
  package manifests/locks, the coordinator Docker build, coordinator startup
  support, coordination-bridge capability detection, tests, and
  `docs/guides/code-search.md`
- **Affected interfaces**: `POST /search/code`,
  `GET /search/code/status`, MCP `search_code`, and `CAN_CODE_SEARCH`
- **Affected data**: read-only consumption of migrations 029/030; no new
  migration
- **Security boundary**: search requests require a trusted scope and never
  return semantic rows outside it

## Approval

The explicit `$autopilot-roadmap project-context-refresh-lifecycle` invocation
provides inherited direction and implementation approval for this
roadmap-selected item.

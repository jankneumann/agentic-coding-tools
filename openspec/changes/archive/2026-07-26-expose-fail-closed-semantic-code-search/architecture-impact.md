# Architecture Impact

<!-- Implementation base: cfb74b67
     Implementation commit: 52f25814
     Branch: openspec/expose-fail-closed-semantic-code-search -->

## Changed Boundaries

RI03 turns the existing default-off semantic-search skeleton into a supported
read path over RI02 immutable indexes:

- `packages/code-search/src/code_search_pkg/query_pg.py` owns exact registry
  selection, validated storage-key addressing, and bounded parameterized KNN.
- `agent-coordinator/src/code_search.py` owns typed operational states,
  revision/provider/storage precedence, provenance, and exact-search fallback.
- `agent-coordinator/src/code_search_authorization.py` owns principal-bound
  repository/namespace grants and exact effective-scope non-emptiness.
- `agent-coordinator/src/code_search_runtime.py` owns loop-local resources,
  single-flight readiness, TTL/backoff, concurrency, timeouts, and shutdown.
- HTTP, direct MCP, and HTTP-proxy MCP adapt one request/response contract.
- Capability discovery consumes the body-aware readiness truth table.

## Cross-Layer Flow

```text
authenticated principal + exact request
  -> server grant / immutable work-package authority
  -> normalized effective scope proof
  -> guarded canonical or exact non-main index identity
  -> revision and provider compatibility
  -> final immutable storage readiness
  -> bounded embedding + parameterized KNN
  -> defensive scope filter + provenance-bearing hits
```

Any failed proof exits before the next expensive stage and returns either a
transport Problem document or a typed non-ready envelope with mandatory
`exact_search` fallback. Query code never indexes, repairs, promotes, or mutates
registry state.

## Dependency and Lifecycle Impact

The coordinator now declares `code-search-pkg` as a non-editable monorepo path
dependency with a shared asyncpg range. Docker installs the package wheel
rather than copying runtime source. HTTP and direct MCP each own resources in
their serving event loop; HTTP-proxy MCP owns no second runtime. Disabled mode
imports no optional semantic package and performs no pool/provider work.

Readiness is dynamic rather than route-based. One process-local refresh lock
collapses concurrent public status requests to one provider probe and registry
read, while search work remains separately bounded by a semaphore and deadline.

## Authorization Impact

Caller scope is only a narrowing of server-owned authority. Effective glob
non-emptiness is proven with a bounded product NFA across allow/path layers,
deny subtraction, and normalized relative-path state. The state cap fails
closed for pathological complexity without authorizing an unproven path; a
separate transition-work budget charges alphabet size against active NFA
positions so synchronous proof cannot monopolize the serving event loop.
Malformed expressions are eagerly rejected, and SQL receives only compiled,
bounded regex parameters.

## Compatibility and Rollback

The prior optional request shape is intentionally replaced: exact source
revision, namespace, and scope identity are required. Legacy registry fields
and repo-slug tables remain for rollback diagnostics but are never queried by
v2. Rollback is operational: disable `CODE_SEARCH_ENABLED` and restart. No data
migration or destructive cleanup is required.

## Validation Findings

| Severity | Category | Description |
|---|---|---|
| resolved | correctness | Revision/provider mismatch now precedes final-storage degradation. |
| resolved | authorization | Empty, disjoint, deny-covered, bracket, and malformed scopes fail closed before semantic work. |
| resolved | resilience | Readiness refresh is single-flight; search work, external calls, cancellation, and shutdown are bounded. |
| resolved | contract | HTTP and MCP/proxy expected failures preserve frozen Problem semantics. |
| warning | live evidence | Postgres/pgvector, provider, and retrieval-quality gates are unavailable in this environment. |
| info | analyzer coverage | The architecture graph matched zero changed entrypoints; behavioral surface tests provide the substantive flow evidence. |

## Recommendation

Safe for stacked PR review with the feature still default-off. Do not enable in
production until the documented live resource and retrieval-quality gates pass.

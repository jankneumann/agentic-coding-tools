# RI03 reviewed-plan resolution

## Review coverage

- Two independent Codex subagents reviewed security/correctness and
  architecture/lifecycle.
- The primary agent reviewed OpenAPI, spec traceability, work-package scope,
  performance, and observability.
- External Claude and Gemini CLI dispatch was attempted. Claude returned an
  unknown error and Gemini timed out; `review-manifest.json` records both
  failures.

## Resolved blockers

1. **Non-main selection** — feature/work-package requests now require exact
   `index_id`; full record identity is validated.
2. **Package/runtime import boundary** — D13 and `wp-query-adapter` now own a
   declared coordinator path dependency, compatible asyncpg range, lockfiles,
   Docker install, and local/container import smoke tests.
3. **Repository/scope authorization** — D6 makes caller scope a narrowing of a
   principal-bound server grant. HTTP returns 401/403 before semantic work.
4. **Work-package provenance** — the resolver is bound to repository, change,
   package, and exact source Git revision; unavailable deployed resolution
   fails closed pending RI08's durable registry.
5. **Dynamic readiness** — D9 specifies TTL, backoff, invalidation, recovery,
   timeouts, cancellation, transition evidence, and bounded shutdown.
6. **Contract truth table** — search state conditions bind current/results,
   fallback reason, index nullability, and scope decision. Status is a
   discriminated `oneOf`.
7. **Spec/task traceability** — active deltas now cover both `code-search` and
   `agent-coordinator`; tasks map scenarios 1–21. Capability discovery consumes
   the frozen status contract in parallel, while integration depends on both it
   and the runtime package and verifies the live boundary.
8. **Observability/privacy** — D12 and tasks require bounded state/latency
   evidence without query text, source content, credentials, DSNs, scope
   patterns, or provider bodies.

## Accepted trade-offs

- HTTP requires an authenticated principal, while direct stdio MCP uses the
  configured local identity. Both are constrained by server-owned code-search
  grants.
- Work-package scope requests are rejected in deployed runtimes until an
  immutable resolver is configured. RI08 can add durable declarations without
  weakening RI03.
- MCP-only capability discovery remains false when it cannot invoke status.
- The feature remains default-off, so the strict in-place request break is
  preferred over preserving an unsafe legacy reader.

## Implementation review convergence

Two independent read-only Codex reviewers audited the implemented branch across
correctness, authorization, lifecycle, contracts, resilience, performance, and
integration cleanup. A separately phrased defensive-review dispatch failed at
the provider policy boundary before producing findings; it was not counted as
review evidence. The two successful reviewers iterated until each reported no
remaining blocker.

Resolved implementation findings:

1. **Effective scope non-emptiness** — replaced heuristic witness enumeration
   with a bounded product-NFA proof across allow/path layers, deny subtraction,
   and normalized relative-path state. Independent state and transition-work
   budgets fail closed before synchronous proof can monopolize the event loop.
   Disjoint, deny-covered, bracket, malformed, and multi-class intersections
   are regression-tested.
2. **HTTP Problem contract** — all route and framework-level 401/403/404/422/429
   outcomes for `/search/code` use the frozen `application/problem+json`
   documents; unrelated FastAPI validation remains unchanged.
3. **MCP/proxy failure parity** — direct and proxied MCP preserve sanitized
   forbidden and overload problems, including a validated retry delay.
4. **Runtime observability** — initialization and readiness completion now emit
   bounded counters and privacy-safe structured state/reason, duration, repo,
   and namespace dimensions.
5. **Readiness single-flight** — concurrent public status refreshes share one
   provider probe and registry read after TTL/backoff expiry.
6. **Complete request validation** — language control characters and malformed
   scope regexes are rejected before index, embedding, or vector work.
7. **Failure precedence** — index identity selection is distinct from final
   storage readiness, so revision/provider mismatches remain authoritative
   before missing-storage degradation.
8. **Scratch cleanup** — the resource-gated Postgres fixture closes its pool
   across setup, yield, and cleanup failure paths.

The final convergence run preserves exact-index selection, default-off
lifecycle, truthful capability discovery, and mandatory exact-search fallback.
Live Postgres/pgvector, provider, and retrieval-quality evidence remains
explicitly deferred until acknowledged external resources are available.

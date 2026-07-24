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

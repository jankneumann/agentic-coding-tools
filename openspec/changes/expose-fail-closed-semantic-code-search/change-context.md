# Change Context: expose-fail-closed-semantic-code-search

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| code-search.1 | `specs/code-search/spec.md` — Strict code-search request identity | Accept only bounded requests with exact repository, revision, namespace, and authoritative scope identity. | `contracts/openapi/v2.yaml#/components/schemas/CodeSearchRequest` | D1, D4 | --- | `tests/test_openapi_contract.py`; `agent-coordinator/tests/test_code_search_surfaces.py` | --- |
| code-search.2 | `specs/code-search/spec.md` — Discriminated fail-closed outcomes | Return one state-discriminated envelope; only ready responses may contain current hits. | `contracts/openapi/v2.yaml#/components/schemas/CodeSearchResponse` | D5 | --- | `tests/test_openapi_contract.py`; `agent-coordinator/tests/test_code_search.py` | --- |
| code-search.3 | `specs/code-search/spec.md` — Revision-aware immutable query storage | Select only guarded ready v2 indexes and address their immutable storage keys. | `contracts/openapi/v2.yaml#/components/schemas/CodeSearchResponse` | D2, D3, D4 | --- | `packages/code-search/tests/test_query_pg.py`; `agent-coordinator/tests/test_code_search.py`; `agent-coordinator/tests/integration/postgres/test_code_search_v2.py` | --- |
| code-search.4 | `specs/code-search/spec.md` — Authoritative read scope | Resolve trusted authority before semantic work; intersect narrowing filters and apply deny precedence. | `contracts/openapi/v2.yaml#/components/schemas/CodeSearchRequest` | D4, D6 | --- | `agent-coordinator/tests/test_code_search_authorization.py`; `agent-coordinator/tests/test_code_search.py` | --- |
| code-search.5 | `specs/code-search/spec.md` — Truthful dynamic capability | Advertise code search only after a body-aware probe proves usable v2 readiness. | `contracts/openapi/v2.yaml#/components/schemas/CodeSearchStatus` | D9 | --- | `skills/coordination-bridge/scripts/tests/test_code_search_capability.py`; `agent-coordinator/tests/test_code_search_runtime.py` | --- |
| code-search.6 | `specs/code-search/spec.md` — Loop-owned optional runtime | Own resources in the serving loop and isolate optional-resource startup and shutdown failures. | `contracts/openapi/v2.yaml#/paths/~1search~1code~1status` | D7, D8, D9, D12 | --- | `agent-coordinator/tests/test_code_search_runtime.py` | --- |
| code-search.7 | `specs/code-search/spec.md` — HTTP, MCP, and proxy parity | Carry the same v2 inputs and serialize the same operational outcomes on all three surfaces. | `contracts/openapi/v2.yaml#/paths/~1search~1code` | D5, D10 | --- | `agent-coordinator/tests/test_code_search_surfaces.py` | --- |
| code-search.8 | `specs/code-search/spec.md` — Authenticated bounded query execution | Authenticate HTTP principals and bound provider/database time and concurrency. | `contracts/openapi/v2.yaml#/paths/~1search~1code/post` | D6, D7, D12 | --- | `agent-coordinator/tests/test_code_search_runtime.py`; `agent-coordinator/tests/test_code_search_surfaces.py` | --- |
| code-search.9 | `specs/code-search/spec.md` — Privacy-preserving code-search observability | Record bounded state evidence without sensitive request, result, credential, or provider content. | `contracts/openapi/v2.yaml#/components/schemas/CodeSearchResponse` | D12 | --- | `agent-coordinator/tests/test_code_search.py`; `agent-coordinator/tests/test_code_search_runtime.py` | --- |
| code-search.10 | `specs/code-search/spec.md` — Repo Registry with Embedder Consistency | Require model, dimension, and nonlegacy fingerprint compatibility from v2 registry authority. | `contracts/openapi/v2.yaml#/components/schemas/CodeSearchResponse` | D2, D4, D7 | --- | `agent-coordinator/tests/test_code_search.py`; `agent-coordinator/tests/integration/postgres/test_code_search_v2.py` | --- |
| code-search.11 | `specs/code-search/spec.md` — Semantic Retrieval Query | Execute one bounded, parameterized, cosine-ranked query with all filters and retained provenance. | `contracts/openapi/v2.yaml#/components/schemas/CodeSearchHit` | D3, D5, D6 | --- | `packages/code-search/tests/test_query_pg.py`; `agent-coordinator/tests/test_code_search.py` | --- |
| code-search.12 | `specs/code-search/spec.md` — Scope-Aware Result Filtering | Bind server grants and immutable work-package authority to repository and revision; caller input may only narrow. | `contracts/openapi/v2.yaml#/components/schemas/CodeSearchRequest` | D4, D6 | --- | `agent-coordinator/tests/test_code_search_authorization.py`; `agent-coordinator/tests/test_code_search.py` | --- |
| agent-coordinator.1 | `specs/agent-coordinator/spec.md` — Code Search Dual-Surface Exposure | Expose one typed service through HTTP, direct MCP, and HTTP-proxy MCP with validation before embedding. | `contracts/openapi/v2.yaml#/paths/~1search~1code` | D4, D5, D10 | --- | `agent-coordinator/tests/test_code_search_surfaces.py` | --- |
| agent-coordinator.2 | `specs/agent-coordinator/spec.md` — Code Search Is a Direct Read | Never mutate or repair during search and degrade optional failures within bounded deadlines. | `contracts/openapi/v2.yaml#/components/schemas/CodeSearchResponse` | D7, D11, D12 | --- | `agent-coordinator/tests/test_code_search.py`; `agent-coordinator/tests/test_code_search_runtime.py` | --- |
| agent-coordinator.3 | `specs/agent-coordinator/spec.md` — Code Search Feature Flag | Default off with no optional work; expose capability only from valid dynamic readiness. | `contracts/openapi/v2.yaml#/components/schemas/CodeSearchStatus` | D8, D9 | --- | `agent-coordinator/tests/test_code_search_runtime.py`; `agent-coordinator/tests/test_code_search_surfaces.py`; `skills/coordination-bridge/scripts/tests/test_code_search_capability.py` | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Prevent revision and namespace guessing. | Exact request schema and validation on every surface. | Exact identity is the only reliable freshness proof. |
| D2 | Prevent arbitrary or legacy index selection. | Guarded main canonical join and exact non-main index lookup. | Selection remains deterministic across fingerprint variants. |
| D3 | Prevent unsafe SQL identifier derivation. | Validate storage keys before deriving final table names. | Immutable storage identity is the narrowest safe query boundary. |
| D4 | Prevent unauthorized or stale embedding work. | Resolve scope and validate revision/provider before embedding. | Rejection remains cheap and fail closed. |
| D5 | Preserve machine-readable degraded behavior. | State-discriminated response variants and exact-search fallback. | Callers can distinguish operational degradation without accepting stale hits. |
| D6 | Treat code visibility as authorization. | Principal grants, immutable work-package resolution, normalized glob intersection, deny precedence. | Caller filters cannot become the trust root. |
| D7 | Prove vector compatibility and bound expensive work. | Complete provider contract, timeouts, and concurrency limit. | Model name alone cannot prove compatible embeddings. |
| D8 | Avoid cross-loop resources and optional startup failures. | Shared factory with separate HTTP/direct-MCP loop-owned instances. | Lifecycle ownership is explicit and proxy mode avoids duplicate work. |
| D9 | Avoid false-positive capability advertising. | Dynamic, cached, body-aware status with invalidation and recovery. | Availability reflects usable context rather than route presence. |
| D10 | Avoid transport-specific semantics. | One request/response serialization contract for HTTP, MCP, and proxy. | Agents receive identical evidence on every surface. |
| D11 | Keep query operations reversible and side-effect free. | No indexing, promotion, repair, queue, or registry mutation. | RI02 remains the single owner of publication. |
| D12 | Make failures diagnosable without leaking code. | Bounded counters and sanitized structured transition logs. | Operations remain observable while source and credentials stay private. |
| D13 | Make the shared adapter a supported dependency. | Monorepo path dependency, compatible asyncpg range, regenerated locks, installed Docker wheel. | Local, test, and production imports use the same package boundary. |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|
| plan-architecture | plan | architecture | critical | resolved | Exact non-main index IDs, supported package dependency, runtime readiness lifecycle, timeouts, and coordinator spec delta were added before implementation. |
| plan-security | plan | security | critical | resolved | Principal-bound grants, immutable work-package provenance, discriminated schemas, scenario ownership, and canonical glob validation were added before implementation. |

## Coverage Summary

- **Requirements traced**: 15/15
- **Tests mapped**: 15 requirements have at least one planned test
- **Evidence collected**: 0/15 requirements have pass/fail evidence
- **Gaps identified**: none at Phase 1
- **Deferred items**: live Postgres and provider evidence remains resource-gated

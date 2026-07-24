# Tasks: Expose fail-closed semantic code search

> Change ID: `expose-fail-closed-semantic-code-search`
> Execution tier: local-parallel

## Status

- [x] Planning
- [ ] Implementation
- [ ] Testing
- [ ] Review
- [ ] Done

## Phase 0 — Freeze the v2 boundary

- [x] 0.1 (S) Write contract tests for strict request validation,
  discriminated operational states, provenance invariants, exact-search
  fallback, and body-aware capability readiness.
  **Spec scenarios**: code-search.1-4, code-search.9-13, code-search.17-20
  **Contracts**: contracts/openapi/v2.yaml
  **Design decisions**: D1, D5, D9, D10
  **Dependencies**: None
- [x] 0.2 (S) Finalize the OpenAPI v2 contract from the failing examples.
  **Spec scenarios**: code-search.1-4, code-search.9-13, code-search.17-20
  **Contracts**: contracts/openapi/v2.yaml
  **Design decisions**: D1, D5, D10
  **Dependencies**: 0.1
- [x] 0.3 (S) Document the normative HTTP/MCP/status contract boundary.
  **Spec scenarios**: all code-search scenarios
  **Contracts**: contracts/README.md, contracts/openapi/v2.yaml
  **Design decisions**: D1, D5, D9, D10
  **Dependencies**: 0.2

- [x] Checkpoint: contracts parse, failing examples are intentional, cumulative diff is contract-only

## Phase 1 — Query immutable exact-index storage

- [x] 1.1 (S) Write clean-environment import tests for the shared query
  package in local coordinator and container-style layouts.
  **Spec scenarios**: code-search.14
  **Design decisions**: D13
  **Dependencies**: 0.3
- [x] 1.2 (M) Declare the supported coordinator dependency on code-search-pkg,
  reconcile asyncpg compatibility, regenerate lockfiles, and install the wheel
  in the Docker builder.
  **Spec scenarios**: code-search.14-16
  **Design decisions**: D8, D13
  **Dependencies**: 1.1
- [x] 1.3 (M) Write query-adapter tests for validated storage-key addressing,
  exact canonical selection, legacy exclusion, provider compatibility, bounded
  filters, correct cosine-similarity semantics, and missing storage.
  **Spec scenarios**: code-search.5-9
  **Contracts**: contracts/openapi/v2.yaml
  **Design decisions**: D2, D3, D7
  **Dependencies**: 0.3, 1.2
- [x] 1.4 (M) Implement storage-key KNN over exact v2 index selection without
  a legacy read fallback.
  **Spec scenarios**: code-search.5-9
  **Contracts**: contracts/openapi/v2.yaml
  **Design decisions**: D2, D3, D7
  **Dependencies**: 1.3

## Phase 2 — Enforce fail-closed service behavior

- [ ] 2.1 (M) Write authorization tests for principal-bound repository grants,
  immutable work-package provenance, deny precedence, canonical glob
  validation, path intersection, stale replay, and cross-repository denial.
  **Spec scenarios**: code-search.2, code-search.10-11, code-search.19
  **Contracts**: contracts/openapi/v2.yaml
  **Design decisions**: D4, D6
  **Dependencies**: 0.3
- [ ] 2.2 (M) Implement principal-bound authorization with normalized
  effective scopes.
  **Spec scenarios**: code-search.2, code-search.10-11, code-search.19
  **Contracts**: contracts/openapi/v2.yaml
  **Design decisions**: D4, D6
  **Dependencies**: 2.1
- [ ] 2.3 (M) Write service-state tests for exact revision rejection before
  embedding, complete provider matching, bounded pagination, provenance-rich
  hits, sanitized degradation, and sensitive-log exclusion.
  **Spec scenarios**: code-search.1-9, code-search.20-21
  **Contracts**: contracts/openapi/v2.yaml
  **Design decisions**: D4, D5, D7, D12
  **Dependencies**: 1.4, 2.2
- [ ] 2.4 (M) Implement the typed exact-search state machine with defensive
  hit filtering and bounded observability.
  **Spec scenarios**: code-search.1-9, code-search.20-21
  **Contracts**: contracts/openapi/v2.yaml
  **Design decisions**: D4, D5, D7, D12
  **Dependencies**: 2.3

- [ ] Checkpoint: query and service suites green, no repo-slug table read remains, cumulative diff reviewed

## Phase 3 — Own startup and surface parity

- [ ] 3.1 (M) Write lifecycle tests for disabled no-op startup, loop-owned
  pool/provider creation, unavailable-resource degradation, status transitions,
  TTL/backoff recovery, immediate invalidation, bounded cancellation, clean
  shutdown, and HTTP-proxy no-double-init.
  **Spec scenarios**: code-search.12, code-search.14-16
  **Contracts**: contracts/openapi/v2.yaml
  **Design decisions**: D8, D9, D12
  **Dependencies**: 0.2, 2.2
- [ ] 3.2 (M) Implement loop-owned code-search lifespans from the shared
  runtime factory.
  **Spec scenarios**: code-search.12, code-search.14-16
  **Contracts**: contracts/openapi/v2.yaml
  **Design decisions**: D7-D9, D12
  **Dependencies**: 3.1
- [ ] 3.3 (M) Write HTTP, MCP, and proxy parity tests for v2 inputs, structured
  non-ready outcomes, missing/cross-repository grants, malformed requests,
  timeout/overload behavior, and sanitized unexpected failures.
  **Spec scenarios**: code-search.1-4, code-search.17-20
  **Contracts**: contracts/openapi/v2.yaml
  **Design decisions**: D5, D6, D7, D10, D12
  **Dependencies**: 2.2
- [ ] 3.4 (M) Implement the typed HTTP/status endpoints, direct MCP tool
  contract, and proxy forwarding.
  **Spec scenarios**: code-search.1-4, code-search.17-20
  **Contracts**: contracts/openapi/v2.yaml
  **Design decisions**: D5-D7, D10, D12
  **Dependencies**: 3.2, 3.3

- [ ] Checkpoint: lifecycle and three-surface parity suites green, optional failures do not fail coordinator readiness

## Phase 4 — Publish truthful capability discovery

- [x] 4.1 (S) Write capability-probe tests for default false, 404, 422, 500,
  malformed body, `available=false`, `available=true`, and unverifiable
  MCP-only transport.
  **Spec scenarios**: code-search.12-13
  **Contracts**: contracts/openapi/v2.yaml
  **Design decisions**: D9
  **Dependencies**: 0.2
- [x] 4.2 (S) Add `CAN_CODE_SEARCH` to both discovery implementations using
  the body-aware status probe and fail-closed MCP fallback.
  **Spec scenarios**: code-search.12-13
  **Contracts**: contracts/openapi/v2.yaml
  **Design decisions**: D9
  **Dependencies**: 4.1
  **Parallelization rationale**: capability discovery consumes the frozen
  status contract and fake HTTP bodies; `wp-integration` verifies it against
  the implemented runtime endpoint.

## Phase 5 — Integration evidence

- [ ] 5.1 (M) Add resource-gated Postgres tests for migration-030 canonical
  storage, exact success, revision mismatch, legacy-only state, provider
  mismatch, canonical pointer changes, and missing final table.
  **Spec scenarios**: code-search.5-9, code-search.12, code-search.15
  **Contracts**: contracts/openapi/v2.yaml
  **Design decisions**: D2-D4, D7-D9
  **Dependencies**: 2.2, 3.4
- [ ] 5.2 (S) Update the code-search guide with v2 request examples,
  provenance, scope rules, readiness semantics, compatibility break, and
  exact-search fallback.
  **Spec scenarios**: all code-search scenarios
  **Contracts**: contracts/README.md, contracts/openapi/v2.yaml
  **Design decisions**: D1-D13
  **Dependencies**: 4.2
- [ ] 5.3 (M) Run unit, API, MCP, bridge, contract, strict OpenSpec,
  work-package, Ruff, Pyright, architecture, and available live-resource
  validation. Report mandatory evidence separately from resource-deferred
  evidence.
  **Spec scenarios**: all code-search scenarios
  **Dependencies**: 5.1, 5.2

- [ ] Checkpoint: all deterministic gates green, live evidence classified, cumulative diff maps to tasks

## Task Sizing

No task is XL. Tasks 0.1-0.3, 1.1, 4.1, 4.2, and 5.2 are S. All remaining
tasks are M; none is L. Multi-surface parity remains one cohesive task because
all three adapters are verified against the same frozen serialization contract.

# Validation Report: expose-fail-closed-semantic-code-search

**Date**: 2026-07-24
**Implementation commit**: `52f25814`
**Branch**: `openspec/expose-fail-closed-semantic-code-search`

## Phase Results

| Phase | Result | Details |
|---|---|---|
| Deploy | skip | The optional query feature remains default-off; no acknowledged Postgres/provider deployment resource is available. |
| Smoke | pass | Disabled/import isolation plus in-process HTTP, direct-MCP, and proxy behavior pass. |
| Gen-Eval | skip | Retrieval-quality evaluation requires the deferred live provider gate. |
| Security | pass | Principal grants, exact revision/provider ordering, scope-language proof, sanitized failures, and bounded concurrency passed independent review. |
| E2E | warn | Deterministic cross-surface suites pass; six new Postgres/pgvector cases and seven upstream package cases are resource-deferred. |
| Architecture | pass | Changed-file flow validation and structural checks report no feature-scoped finding; the graph matches no changed package entrypoint. |
| Spec Compliance | pass | 15/15 requirements map to deterministic pass evidence; live portions are explicitly deferred. |
| Evidence | pass | Contracts, work-package DAG/scope, task reconciliation, review convergence, and diff hygiene pass. |
| Logs | skip | No deployed service log stream exists; in-process privacy-safe observability regressions pass. |
| CI/CD | pending | A stacked draft PR is created after this local validation record is committed and pushed. |

## Deterministic Evidence

- Shared code-search package: **277 passed**, 7 resource skips
- Coordinator query/runtime/surfaces: **100 passed**
- Capability bridge: **71 passed**
- OpenAPI v2 contract: **30 passed**
- Deterministic total: **478 passed**
- Strict mypy over four RI03 service/authorization/runtime/integration files: **pass**
- Changed-file Ruff lint: **pass**
- Strict OpenSpec: **pass**
- Work-package schema/DAG/parallel zones/scope: **pass**
- Architecture flow validation: **0 findings**
- Review findings schema: **pass**
- `git diff --check`: **pass**

The resource-gated RI03 Postgres suite collects six cases—exact canonical
success, revision mismatch, legacy exclusion, provider mismatch, canonical
pointer movement, and vanished final storage—but reports six skips without an
acknowledged scratch DSN. Skips are not counted as passes.

## Review Convergence

Independent implementation reviewers found and drove fixes for empty/disjoint
scope handling, HTTP Problem documents, MCP/proxy failure parity, runtime
observability, readiness single-flight, complete language/scope validation,
missing-storage precedence, and scratch cleanup. The final review iteration
reported no unresolved finding after the product-NFA scope proof replaced
bounded heuristic witness expansion; a separate work budget bounds transition
cost as well as stored automaton states.

See [change-context.md](./change-context.md) for per-requirement evidence and
[reviews/review-resolution.md](./reviews/review-resolution.md) for dispositions.

## Result

**PASS WITH RESOURCE WARNINGS** — deterministic implementation and contract
evidence is green. Production enablement remains blocked on the documented
live Postgres/pgvector, embedding-provider, and retrieval-quality gates.

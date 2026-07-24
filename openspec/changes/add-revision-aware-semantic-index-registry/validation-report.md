# Validation Report: add-revision-aware-semantic-index-registry

**Date**: 2026-07-23 14:58:06 EDT
**Commit**: 6ce11776
**Branch**: `openspec/add-revision-aware-semantic-index-registry`

## Phase Results

| Phase | Result | Details |
|-------|--------|---------|
| Deploy | skip | No deployable service is added; Docker is unavailable. |
| Smoke | skip | No live API or MCP surface changes in this registry-foundation item. |
| Gen-Eval | skip | The coordinator descriptor does not cover this internal registry contract. |
| Security | warn | Static review and orchestrator dry-run pass; container/ZAP scanners are unavailable. |
| E2E | skip | Existing coordinator E2E tests do not exercise this unused internal registry boundary. |
| Architecture | warn | Scoped flows: 0 findings; structural linter: pass. Global refresh contains unrelated stale-baseline warnings and excludes package Python modules. |
| Spec Compliance | pass | 14/14 scenarios mapped and locally verified; supplemental live PostgreSQL cases are deferred. |
| Evidence | pass | Review schema, work-package DAG, contracts, and task checklist are complete. |
| Logs | skip | No service was deployed, so no runtime log stream exists. |
| CI/CD | skip | GitHub CLI authentication is invalid and no PR exists for this branch. |

## Test and Contract Evidence

- Code-search package: **43 passed, 5 skipped**
- Migration and legacy compatibility: **9 passed, 4 skipped**
- Executable JSON Schema lifecycle cases: **8 passed**
- Changed-file Ruff: **pass**
- Changed-file Pyright: **0 errors, 0 warnings**
- Strict OpenSpec validation: **pass**
- Work-package schema/DAG/locks: **pass**
- Architecture graph schema: **pass**
- Changed-file architecture flow validation: **0 findings**
- Changed-file structural linter: **pass**
- `git diff --check`: **pass**

The skipped package cases require optional CocoIndex/embedder dependencies.
The four migration skips require `POSTGRES_DSN`; their structural and
repository-level regressions pass locally.

## Spec Compliance

See [change-context.md](./change-context.md) for the full requirement
traceability matrix.

**Summary**: 14/14 scenarios traced, 14/14 mapped to passing local evidence,
4/4 independent-review fix findings resolved, and live PostgreSQL confirmation
deferred for the environment-dependent cases.

## Log Analysis

Skipped because no service was deployed. No runtime errors, warnings,
deprecations, stack traces, or unhandled exceptions were collected.

## Result

**PASS WITH WARNINGS** — The implementation is ready for PR review. Publication
and CI verification remain blocked by invalid GitHub CLI authentication, and
main-branch synchronization remains subject to the active-agent sync-point
guard.

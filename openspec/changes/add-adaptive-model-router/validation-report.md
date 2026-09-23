# Validation Report: add-adaptive-model-router (dg-00)

**Date**: 2026-09-16
**Validated code commit**: `081d7645`
**Branch**: `openspec/roadmap-dispatch-governance--dg00-recovery`
**Result**: PASS WITH ADVISORIES

## Phase Results

| Phase | Status | Evidence |
|---|---|---|
| Focused integration | PASS | 345 passed across model-routing, DB adapter, coordinator API/proxy/config, and watchdog |
| Coordinator regression | PASS | 2,597 passed, 11 skipped, 132 deselected; one known migration-sequence warning |
| Affected skills | PASS | 735 passed, 2 skipped |
| Static checks | PASS | Ruff passed; mypy passed for 15 affected source files; diff check clean |
| Contracts/spec | PASS | Contract parity 17 passed; strict OpenSpec all: 93 passed, 0 failed |
| Work packages | PASS | Schema, dependency references, DAG cycles, and lock keys valid |
| Architecture | PASS (qualified) | Refresh pipeline passed all available stages; TypeScript analyzer skipped and prior artifact carried forward; 55 changed files produced 0 scoped-flow findings |
| Plan review | PASS | 4/4 schema-valid quorum; 0 confirmed, 0 blocking, 11 unconfirmed advisories |
| Implementation review | PASS | Final round 4/4 schema-valid quorum; 0 confirmed, 0 blocking, 5 unconfirmed advisories |
| Security | PASS (scoped) | Bearer enforcement and 401/503 transport contracts are exercised; no dependency manifests changed. Live DAST was not required for the four internal dg-00 outcomes |
| Deploy/live E2E | DEFERRED | No production deployment requested. Live quick-task E2E is outside the four roadmap acceptance outcomes and remains explicitly deferred |

## Acceptance Outcomes

1. All five `/routing/*` paths and matching MCP selection are implemented and contract-tested.
2. Migration 040 and storage-only catalog behavior are implemented, including apply/re-apply coverage and hardened Postgres filter translation.
3. `ROUTING_ADAPTIVE` defaults off with exact static behavior; enabled resolution delegates with a bounded timeout and exact-static error fallback.
4. `OpenAICompatAdapter` is reachable after CLI/SDK discovery without duplicating the merged scoring or cost core.

## Qualified Architecture Evidence

The refresh used explicit repository roots: `agent-coordinator/src`, `agent-coordinator/database/migrations`, and `apps`. Python, PostgreSQL, SQL tree-sitter, compiler, enrichment, validation, parallel-zone, views, and report stages passed. TypeScript analysis remained unavailable after dependency bootstrap and the previously committed TypeScript artifact was carried forward. The source-root refresh does not ingest tests, so direct test evidence above qualifies graph test-link coverage. Generated repository-wide artifacts were restored after validation to avoid unrelated churn; the change-local `architecture-impact.md` records the durable interpretation.

## Review Convergence

Round 1 exposed contract, catalog, ledger, refresh, and exploration-budget defects. Round 2 confirmed two backend seams missed by mocks: encoded Postgres filter decoding and missing exploration entry counts. Both were fixed with direct regression tests. Final Round 3 returned 0 findings from Antigravity and Codex; Claude and Grok supplied five unconfirmed judgment advisories, with zero confirmed, disagreement, or blocking findings. Pi failed in the final two rounds; the four successful independent vendors satisfy the configured quorum.

## Residual Advisories

Unconfirmed advisories concern FastAPI 422 schema detail, probing retained unavailable local rows, a partly tautological proxy parity test, and one stale by-model description. They do not invalidate the four dg-00 outcomes and remain visible in `reviews/consensus-impl.json`. Removed OpenRouter-model reconciliation remains explicitly deferred as DT-9.

## Result

**PASS WITH ADVISORIES** — dg-00 satisfies all four roadmap acceptance outcomes and its validation/review gate.

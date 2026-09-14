# Validation Report: mirror-autopilot-phase-state-into-the-work-queue

**Date**: 2026-09-14T03:58:34-04:00
**Validated commit**: `5693a3206ab0ffb0a232c69f569629f975be1635`
**Branch**: `openspec/recover-ri-09-work-queue-projection`
**Surface**: non-deployable change with locally validated API, PostgreSQL, and Kanban paths

## Phase Results

| Phase | Result | Details |
|---|---|---|
| Deploy | not applicable | No external environment was mutated; the repository-defined disposable PostgreSQL stack was used for validation. |
| Smoke | pass | Migrations 038-039 applied on the live stack and the fresh full migration chain passed. |
| Gen-Eval | not applicable | No generator/evaluator scenario surface changed. |
| Security | pass | No dependency or credential changes; projection labels are exact, coordinator-only, and policy/auth handlers retain typed failures. |
| E2E | pass | FastAPI to service to asyncpg to PostgreSQL projection lifecycle and board query passed. |
| Architecture | pass with advisory warnings | Deterministic artifacts are fresh; flow validation returned 0 errors. Optional TypeScript analysis was unavailable and existing graph coverage warnings remain advisory. |
| Spec Compliance | pass | 1/1 traced requirement has live and focused evidence; 0 gaps and 0 deferred items. |
| Logs | pass | Live PostgreSQL/EventBus tests completed without service errors. |
| CI/CD | pending | Local required gates pass; hosted checks begin after PR creation. |

## Evidence

- 436 Autopilot tests passed.
- 96 coordination-bridge tests passed.
- 143 coordinator queue, issue, projection-visibility, and API tests passed.
- 18 focused live PostgreSQL migration, projection, EventBus/SSE, and HTTP E2E tests passed; the broader earlier live run passed 30 tests.
- 224 Kanban tests passed with 6 declared skips; the production build passed.
- 4,763 canonical skills tests passed with 13 declared skips.
- All 90 OpenSpec artifacts passed strict validation.
- Scoped Ruff, dependency direction, byte-level skill mirror parity, installer regression (29 passed), work-package schema/DAG/locks, and diff checks passed.
- Architecture refresh completed with 0 errors; canonical freshness passed. Optional TypeScript analysis remained unavailable and 2,716 existing repository-wide warnings remain advisory.

## Review and recovery

Round 4 reached substantive quorum from Claude Code, Codex, and Grok and drove canonical ESCALATE recovery, non-halting projection degradation, and atomic label repair.

Round 5 attempted every configured locally addressable vendor type. Codex and Grok supplied substantive schema-valid findings; Pi supplied 20 additional schema-valid findings preserved out of band after its adapter returned protocol NDJSON. The credible gaps produced first-insert SSE notification, replay/collision/terminal-row integrity, executable and idempotent ESCALATE recovery, auto-resume persistence, exact runtime/OpenAPI bounds, and a real installed-payload parity gate. Round 6 reviews the integrated post-fix commit with the repository-local vendor configuration forced explicitly so Antigravity receives its required JSON output mode.

The explicit monolithic `pytest tests` command was rejected as an invalid gate:
it bypasses the curated skills `testpaths` ordering and creates known flat-module
import collisions. The canonical `cd skills && .venv/bin/python -m pytest -q`
gate passed with the result above.

## Result

**PASS** — All locally executable required phases pass. The implementation is
ready for the post-fix vendor review and pull-request checks.

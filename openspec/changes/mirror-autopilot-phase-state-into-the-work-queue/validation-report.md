# Validation Report: mirror-autopilot-phase-state-into-the-work-queue

**Date**: 2026-09-14T05:17:05-04:00
**Validated commit**: `c8f8e37e592031110561028b0b81644fd49b0fc0`
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
- 143 coordinator work-queue, issue, projection-visibility, and API tests passed with 18 declared skips.
- 42 live PostgreSQL migration, projection, EventBus/SSE, and HTTP E2E tests passed.
- 224 Kanban tests passed with 6 declared skips; the production build passed.
- 4,764 canonical skills tests passed with 13 declared skips.
- All 90 OpenSpec artifacts passed strict validation.
- Scoped Ruff, dependency direction, byte-level skill mirror parity, installer regression (29 passed), work-package schema/DAG/locks, and diff checks passed.
- Architecture refresh completed with 0 errors; canonical freshness passed. Optional TypeScript analysis remained unavailable and 2,716 existing repository-wide warnings remain advisory.

## Review and recovery

Round 4 reached substantive quorum from Claude Code, Codex, and Grok and drove canonical ESCALATE recovery, non-halting projection degradation, and atomic label repair.

Round 5 attempted every configured locally addressable vendor type. Codex and Grok supplied substantive schema-valid findings; Pi supplied 20 additional schema-valid findings preserved out of band after its adapter returned protocol NDJSON. The credible gaps produced first-insert SSE notification, replay/collision/terminal-row integrity, executable and idempotent ESCALATE recovery, auto-resume persistence, exact runtime/OpenAPI bounds, and a real installed-payload parity gate. Round 6 sent the verified repository-local prompt to every configured harness and reached schema-valid quorum from Claude Code, Codex, and Grok. It identified and closed an unowned issue-row collision, over-broad active-row reset, missing HTTP 409 classification, and the empty round-5 disposition ledger. Database-owned UUID registration prevents ownership spoofing; Pi schema-invalid out-of-band output is preserved byte-for-byte as raw evidence.

Round 7 again addressed every configured harness and reached protocol-valid quorum from Claude Code, Grok, and Pi; Antigravity complete schema-valid review was recovered as out-of-band evidence after its adapter appended an extra payload, while Codex timed out. The credible findings drove a fresh-checkout CI mirror install, label-spoof-resistant registry ownership, terminal-state transition idempotence, persistence of initialization options, and EventBus/SSE refresh on terminal-row reactivation. The ambiguous pre-038 unlabeled-row upgrade case remains deliberately fail-closed and is now documented. All fixes have executable regression coverage, and the post-fix validation matrix passes.

The explicit monolithic `pytest tests` command was rejected as an invalid gate:
it bypasses the curated skills `testpaths` ordering and creates known flat-module
import collisions. The canonical `cd skills && .venv/bin/python -m pytest -q`
gate passed with the result above.

## Result

**PASS** — All locally executable required phases pass. The implementation is
ready for the final convergence review and pull-request checks.

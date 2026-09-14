# Validation Report: mirror-autopilot-phase-state-into-the-work-queue

**Date**: 2026-09-14T08:09:22-04:00
**Validated commit**: `88087a5df0f8c317c5e6ad93e41e345d1deb3359`
**Branch**: `openspec/recover-ri-09-work-queue-projection`
**Surface**: non-deployable change with locally validated API, PostgreSQL, and Kanban paths

## Phase Results

| Phase | Result | Details |
|---|---|---|
| Deploy | not applicable | No external environment was mutated; the repository-defined disposable PostgreSQL stack was used for validation. |
| Smoke | pass | Migrations 038-039 applied on the live stack and the fresh full migration chain passed. |
| Gen-Eval | not applicable | No generator/evaluator scenario surface changed. |
| Security | pass | Projection publication is a distinct trust-level-3 operation bound to the exact change ID across HTTP and local service paths; trust-level-2 ordinary submitters, reserved-label spoofing, owned-row issue mutation, and trust-resolution failures stop before mutation. |
| E2E | pass | FastAPI to service to asyncpg to PostgreSQL projection lifecycle and board query passed. |
| Architecture | pass with advisory warnings | Deterministic artifacts are fresh; flow validation returned 0 errors. Optional TypeScript analysis was unavailable and existing graph coverage warnings remain advisory. |
| Spec Compliance | pass | 1/1 traced requirement has live and focused evidence; 0 gaps and 0 deferred items. |
| Logs | pass | Live PostgreSQL/EventBus tests completed without service errors. |
| CI/CD | pending | Local required gates pass; hosted checks begin after PR creation. |

## Evidence

- 445 Autopilot tests passed.
- 96 coordination-bridge tests passed.
- 2,510 coordinator CI-selected tests passed with 11 declared skips and 125 live-marker deselections.
- 45 live PostgreSQL migration, projection, EventBus/SSE, and HTTP E2E tests passed.
- 224 Kanban tests passed with 6 declared skips; the production build passed.
- 4,767 canonical skills tests passed with 13 declared skips.
- All 90 OpenSpec artifacts passed strict validation.
- Canonical coordinator and skills Ruff gates, mypy over all 77 coordinator source files, byte-level skill mirror parity, and work-package schema/DAG/locks/context-impact checks passed.
- Architecture refresh completed with 0 errors; canonical freshness passed. Optional TypeScript analysis remained unavailable and 2,716 existing repository-wide warnings remain advisory.

## Review and recovery

Round 4 reached substantive quorum from Claude Code, Codex, and Grok and drove canonical ESCALATE recovery, non-halting projection degradation, and atomic label repair.

Round 5 attempted every configured locally addressable vendor type. Codex and Grok supplied substantive schema-valid findings; Pi supplied 20 additional schema-valid findings preserved out of band after its adapter returned protocol NDJSON. The credible gaps produced first-insert SSE notification, replay/collision/terminal-row integrity, executable and idempotent ESCALATE recovery, auto-resume persistence, exact runtime/OpenAPI bounds, and a real installed-payload parity gate. Round 6 sent the verified repository-local prompt to every configured harness and reached schema-valid quorum from Claude Code, Codex, and Grok. It identified and closed an unowned issue-row collision, over-broad active-row reset, missing HTTP 409 classification, and the empty round-5 disposition ledger. Database-owned UUID registration prevents ownership spoofing; Pi schema-invalid out-of-band output is preserved byte-for-byte as raw evidence.

Round 7 again addressed every configured harness and reached protocol-valid quorum from Claude Code, Grok, and Pi; Antigravity complete schema-valid review was recovered as out-of-band evidence after its adapter appended an extra payload, while Codex timed out. The credible findings drove a fresh-checkout CI mirror install, label-spoof-resistant registry ownership, terminal-state transition idempotence, persistence of initialization options, and EventBus/SSE refresh on terminal-row reactivation. The ambiguous pre-038 unlabeled-row upgrade case remains deliberately fail-closed and is now documented. All fixes have executable regression coverage, and the post-fix validation matrix passes.

Round 8 reached four-vendor protocol quorum and exposed additional critical state-recovery and database-ownership defects, plus package-ledger, mirror, schema, dispatcher, and operator-documentation gaps. Manual and automatic escalation resumes now share one persisted resolved edge; stale apply-outcome callers cannot change the durable resume phase; all labelled-row mutations require database-owned UUID registration; migration 039 never auto-adopts mutable legacy fields; and the historical unlabelled reconcile contract remains intact. The complete mirror payload, heterogeneous request tuple, canonical problem details, and Antigravity structured-output envelopes are pinned by tests. A full-suite compatibility failure was reproduced, corrected, and guarded before this report.

Rounds 9 and 10 addressed every configured harness and corrected the review infrastructure itself. Exact reviewed-worktree vendor configuration now wins over stale coordinator/global state unless an explicit configuration is supplied; dispatch, vendor checks, and agent listing share that resolver; exact reviewed cwd and fallback behavior are regression tested. Round 10 reached schema-valid Antigravity/Grok quorum and independently reported no remaining projection defect.

Round 11 reached four-vendor schema-valid quorum from Antigravity, Codex, Grok, and Pi. Codex identified three critical defects that were independently reproduced: trust-level-2 HTTP callers could publish projections, newer-generation repair could insert around an unowned pre-registry row, and reconciliation swallowed trust-resolution failure before mutating. It also found an SDK-only coordinator-roster fallback bug. All four were fixed test-first. Projection publication now uses a distinct elevated operation against the exact change resource, both labelled SQL paths preflight every associated unowned reserved-labelled row before mutation, reconciliation propagates trust failure, and SDK-only rosters remain authoritative. The package, spec, operator guide, review-skill documentation, policy profiles, Cedar policy/schema, migration upgrade path, and live tests encode the recovered contract.

Round 12 again reached four-vendor schema-valid quorum from Antigravity, Codex, Grok, and Pi. Codex and Grok independently demonstrated that ordinary issue mutation could alter registry-owned projections and that an ordinary issue carrying the reserved label pair could forge board/SSE state and permanently block repair. Both defects were fixed test-first at the service, HTTP, and transactional database layers. The reserved marker is now database-owned; projection RPCs stage insert, ownership, and labels atomically; ordinary issue update/close refuses owned UUIDs; and live tests prove both post-migration spoof rejection and pre-migration fail-closed upgrade behavior. The same round corrected in-process convergence to use reviewed-worktree vendor discovery, aligned local service publication with the elevated operation, and made Cedar omitted-trust resolution use the shared fail-closed resolver.

The explicit monolithic `pytest tests` command was rejected as an invalid gate:
it bypasses the curated skills `testpaths` ordering and creates known flat-module
import collisions. The canonical `cd skills && .venv/bin/python -m pytest -q`
gate passed with the result above.

## Result

**PASS** — All locally executable required phases pass. The implementation is
ready for the final exact-head convergence review and pull-request checks.

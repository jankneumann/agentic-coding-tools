# Validation Report: add-live-vendor-capability-and-cost-registry (dg-01)

**Date**: 2026-09-16
**Validated code commit**: `e5684e8c98c45156c1c256198b1ea8315e221f2e`
**Branch**: `openspec/add-live-vendor-capability-and-cost-registry`
**Result**: PASS

## Phase Results

| Phase | Status | Evidence |
|---|---|---|
| Deploy | PASS (contracted) | Production image copies the vendor probe and pins `AGENTS_YAML`/`SKILLS_ROOT`; behavioral watchdog tests persist every configured first-poll snapshot and start without notification channels. No production deployment was requested. |
| Smoke | PASS | Authenticated registry API and watchdog matrix passed 36 tests; the broader focused registry/API/watchdog rerun passed 43 tests. |
| Security | PASS | Principal-bound own-lane and delegated cross-lane reporting, forbidden writes, bounded resets, non-secret audit reasons, and persisted-pause sanitization are exercised. No dependency manifest changed. |
| E2E / Integration | PASS | Required PostgreSQL migration/core matrix passed 33 tests with 0 skips; affected bridge/dispatcher/policy/runtime matrix passed 501 tests. |
| Architecture | PASS | Work-package DAG, scope overlap, and lock overlap validated with no errors; dg-01 preserves the dg-00 catalog as the sole price store. |
| Spec Compliance | PASS | All 8 requirements and 33 scenarios are implemented and traced; contract parity passed 19 tests; strict OpenSpec passed 93/93. |
| Validation Review | PASS | Final configured panel achieved semantic quorum 2/2 with 0 blocking and 0 disagreement findings; three unavailable harnesses were recorded as bounded timeouts. |
| Static / Regression | PASS | Coordinator: 2,659 passed, 11 skipped, 132 deselected. Skills-root configured suite: 4,873 passed, 15 skipped. Ruff passed both trees; strict mypy passed 83 source files. |
| CI/CD | PASS | PR #562 replacement run 35157071348 passed 19 checks with 1 expected dependency-remediation skip and 0 failures. |

## Smoke Tests

**Status**: pass

Authenticated registry API and watchdog behavior passed 36 declared tests; the broader focused registry/API/watchdog rerun passed 43 tests.

## Security

**Status**: pass

Principal authorization, forbidden cross-lane writes, bounded resets, safe audit reasons, and persisted artifact sanitization are covered by the passing coordinator and roadmap-runtime suites. No dependency manifest changed.

## E2E Tests

**Status**: pass

The required PostgreSQL migration/core matrix passed 33 tests with zero skips. Bridge, dispatcher, roadmap policy, and runtime integration passed 501 affected tests.

## Architecture

**Status**: pass

The validated package DAG is acyclic with no scope or lock overlap errors. The implementation preserves the dg-00 model catalog as the only price store and exposes explicit typed identity/location for dg-04.

## Spec Compliance

**Status**: pass

All 8 normative requirements and 33 scenarios are implemented and traced in `change-context.md`. Contract parity passed 19 tests and strict OpenSpec passed 93/93.

## Acceptance Outcomes

1. `GET /vendors` and `GET /vendors/{agent_id}/availability` expose explicitly configured lane identity, typed location, capabilities, effective availability, reset state, and catalog projections.
2. Watchdog snapshots persist on the first poll, become stale deterministically, preserve transition events, isolate per-lane persistence failures, and audit failure paths without leaking exception payloads.
3. Rate-limit observations are principal-bound, bounded, idempotent, lane/model scoped, compacted, and reported by dispatch collectors without changing dispatch outcomes.
4. Pricing remains owned by dg-00 `model_catalog`; exact-model quotes use deterministic six-place `ROUND_HALF_UP`, and missing or ambiguous joins remain unknown and audited.
5. Roadmap policy consumes capability/location-filtered registry lanes, preserves exact lane provenance, fails closed by default, honors WAIT without redispatch spin, and sanitizes persisted pause state.
6. The hardcoded orchestrator vendor roster is removed; dg-04 can consume explicit `location`, `policy_vendor`, `catalog_vendor`, and lane capability fields without heuristics.

## Canonical Gate Evidence

- Coordinator non-e2e/non-integration: **2,659 passed, 11 skipped, 132 deselected**.
- Required PostgreSQL migration/core gate: **33 passed, 0 skipped**.
- Contract parity: **19 passed**.
- API/watchdog declared gate: **36 passed**.
- Affected skills integration matrix: **501 passed**.
- Configured skills-root suite: **4,873 passed, 15 skipped**.
- Strict mypy: **83 source files, 0 issues**.
- Ruff: **both coordinator and skills trees passed**.
- Strict OpenSpec: **93 passed, 0 failed**.
- Work-package DAG/scope/locks: **valid; no overlap errors**.
- Diff hygiene: **clean**.

The repository-wide command originally written as `pytest -c skills/pyproject.toml` from the repository root collected unrelated sibling projects and failed during collection because the configuration is rooted at `skills/`. The package declaration now invokes the same configured suite from the `skills` directory; that canonical invocation passed 4,873 tests. This was a gate-command correction, not a product-code exception.

## Validation Review

**Status**: pass

Five configured harnesses received the final bounded verification prompt. Claude Code and Grok returned schema-valid, semantically coherent reviews. Antigravity, Codex, and Pi reached the configured 240-second deadline and were recorded as transient timeouts. The two usable reviewers satisfied the required quorum: 2/2, zero blockers, zero disagreements, one confirmed positive finding, and four advisory positive findings. The canonical evidence is under `reviews/implementation-round-5/`.

Earlier rounds remain preserved as historical evidence. They drove remediation for exact-lane reporting, lifecycle audit coverage, WAIT persistence, snapshot-failure audit/logging, and persisted pause-state sanitization.

## Implementation-Time Choice Audit

The independent choices ledger records one sound, high-confidence silent-spec choice: exact half-microdollar request quotes use explicit `ROUND_HALF_UP` at six decimal places. The boundary behavior is covered by a named test. The installed `.agents/audit-choices` schema-path defect is outside dg-01 and is tracked by GitHub issue #559; canonical `skills/audit-choices` produced the valid ledger.

## Residual Notes

- One migration-sequence warning is expected on feature branches when a later numbered migration already exists; migration 041 does not collide.
- Live production deployment was not requested. The image contract and behavioral startup/persistence path are tested locally.
- PR #562 targets the finalized dg-00 branch; replacement CI run 35157071348 is fully green.

## Result

**PASS** — dg-01 satisfies its six roadmap outcomes, all required local validation gates, and the configured multi-vendor implementation review. It is ready for stacked PR submission against `openspec/add-adaptive-model-router`.

# Validation Report: implement-idempotent-queue-submission-and-outbox-ordering

**Date**: 2026-09-01 22:15 EDT
**Commit**: `b0907df98c04af88f7c72cd5043823c533154844`
**Validated tree**: `c368b09908bcce8bbfb9624396e16d241bc985f1`
**Branch**: `openspec/implement-idempotent-queue-submission-and-outbox-ordering`

## Result

**PASS WITH ADVISORIES** — All required phases pass at the validation-fix head. Fresh rootless Podman deployment, migration apply/retry, live PostgreSQL projection behavior, smoke, security coverage, HTTP E2E, contracts, traceability, and affected suites succeeded. Architecture freshness and unrelated fresh-schema/runtime bootstrap noise remain advisory baselines.

## Phase Results

### Deploy

**Status**: pass

Rootless Podman 4.9.3 started a fresh PostgreSQL 18.3 volume and coordinator API on isolated ports 55439 and 18089. PostgreSQL initdb executed migration 035 as BEGIN → LOCK → preflight/DDL → COMMIT, and the API returned health 200.

The real asyncpg runner independently applied only migration 035 in a disposable database, returned `[035_work_queue_projection.sql]`, then returned `[]` on immediate retry. The projection table, unique index, reconcile function, and schema-migrations record were all present.

## Smoke Tests

**Status**: pass

The reusable live smoke suite passed 11/11: health/readiness, valid/invalid/missing credentials, CORS behavior, and error sanitization.

## Security

**Status**: pass with warning

One bounded OWASP ZAP baseline attempt reached the live isolated API and completed passive coverage: 66 rules passed, zero failures, and one advisory cacheability warning on the public 404 root response. The wrapper exited 2 after scanning because the rootless container could not write its HTML/JSON report into the mounted temporary directory; the complete rule summary remained in the captured scanner log and no second attempt was made. Preventive checks found no new Tier-3 dynamic execution, TLS bypass, hardcoded secret, or unparameterized SQL boundary. No dependency manifests changed, so dependency SCA was not repeated. The installed security skill omitted its referenced detailed checklist file; embedded A01/A03 rules were applied.

## E2E Tests

**Status**: pass

Live HTTP projection flow passed: missing auth returned 401; keyed create returned 200; replay returned the same UUID with deduplicated true; an equal-sequence different-phase request returned RFC 7807 409; reconciliation returned 200 and cancelled the stale UUID.

## Spec Compliance

**Status**: pass

- Strict OpenSpec: valid.
- Semantic OpenAPI: OK.
- Requirement traceability: pass, 68 operations cite 36 requirements.
- Work-package schema, dependency refs, DAG, lock keys, scope overlap, and lock overlap: valid.
- Context-impact: pass for all four packages, with no undeclared or spurious surfaces.

### Tests

**Status**: pass for the affected ri-08 surface

- Coordinator unit/transport surface: 142 passed.
- Migration runner: 16 passed.
- Live PostgreSQL projection: 4 passed, 0 skipped, including concurrent canonical replay and reconciliation/cancellation.
- Bridge and autopilot: 460 passed, 2 marker/deprecation warnings.
- Smoke: 11 passed.

The previously recorded repository-wide suite failures remain outside this focused rerun. No affected ri-08 test failed or skipped.

### Architecture

**Status**: DEGRADED

Architecture mode is advisory. Freshness remains unavailable because root configuration targets absent `src`, `database/migrations`, and `web` paths; refresh stopped before promotion and left committed artifacts untouched. Structural linters reported the same 14 file-size advisories and no new blocking architecture finding.

### Package Evidence

**Status**: pass with warning

Package schema/DAG/overlap/context gates pass. Canonical per-package work-result JSON remains absent from the earlier coordinator dispatch; existing context checkpoints and direct validation evidence cover the affected surfaces.

### Log Analysis

**Status**: pass with baseline warnings

No migration-035 or projection endpoint error remains. Fresh-schema logs still contain legacy `coordinator_notify` ambiguity and missing `audit_log.delegated_from` audit-write errors outside the ri-08 projection path.

### CI/CD

**Status**: skipped

No pull request or workflow run exists yet for the feature branch.

## Resolved Findings

1. Migration 035 now has explicit psql transaction boundaries normalized by the asyncpg runner.
2. Bootstrap syntax failures can no longer be falsely recorded as applied.
3. All live PostgreSQL projection tests run without skips and pass.
4. Context-impact metadata declares every inferred surface.
5. Live smoke, ZAP baseline DAST, and HTTP projection E2E checks pass.

## Residual Advisories

1. Correct architecture source-root configuration and refresh the graph.
2. Repair rootless ZAP report-volume permissions so future runs retain JSON/HTML artifacts.
3. Address legacy fresh-schema migration-runner and `audit_log.delegated_from` bootstrap noise separately.
4. Repair repository-wide test isolation failures recorded by the first validation run.

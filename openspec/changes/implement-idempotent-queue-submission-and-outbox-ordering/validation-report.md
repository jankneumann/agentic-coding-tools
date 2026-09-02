# Validation Report: implement-idempotent-queue-submission-and-outbox-ordering

**Date**: 2026-09-01 22:55 EDT
**Commit**: `59fdb05f65e2a38d3ad75263a6a51f950edb7be2`
**Validated tree**: `b2478da8a9aed3c4bc3271dec92c6e7d9b017d45`
**Branch**: `openspec/implement-idempotent-queue-submission-and-outbox-ordering`

## Result

**PASS WITH ADVISORIES** — All required phases pass at the security-evidence fix head without overrides. Fresh rootless Podman deployment, migration apply/retry, live PostgreSQL projection behavior, smoke, security coverage, HTTP E2E, contracts, traceability, and affected suites succeeded. The Security phase now retains independently auditable scanner and gate artifacts; architecture freshness and unrelated fresh-schema/runtime bootstrap noise remain advisory baselines.

## Phase Results

### Deploy

**Status**: pass

Rootless Podman 4.9.3 started a fresh PostgreSQL 18.3 volume and coordinator API on isolated ports 55443 and 18093. PostgreSQL initdb executed migration 035 as BEGIN → LOCK → preflight/DDL → COMMIT, and the API returned health 200.

The real asyncpg runner independently applied only migration 035 in a disposable database, returned `[035_work_queue_projection.sql]`, then returned `[]` on immediate retry. The projection table, unique index, reconcile function, and schema-migrations record were all present.

## Smoke Tests

**Status**: pass

The reusable live smoke suite passed 11/11: health/readiness, valid/invalid/missing credentials, CORS behavior, and error sanitization.

## Security

**Status**: pass with warning

One fresh, bounded OWASP ZAP baseline attempt ran against the isolated API from `2026-09-02T02:34:36Z` through `02:35:04Z`. The scan exited 2 and is classified as `completed_with_warnings`, not as a zero-exit scan pass: 66 passive rules passed, zero failed, and one informational cacheability warning covered three public 404 responses. A writable Podman named volume retained the JSON and HTML reports, while change-local files retained raw stdout/stderr, exact command, target, timestamps, exit code, summaries, and SHA-256 hashes. The canonical security parser and `fail_on=high` risk gate returned **PASS** with one informational finding and zero threshold findings. See `validation-evidence/security/validation-fix-2/execution.json`, `zap.stdout.log`, `zap-report.json`, `security-review-report.json`, and `gate.json`. No second scan attempt was made. Preventive checks found no new Tier-3 dynamic execution, TLS bypass, hardcoded secret, or unparameterized SQL boundary. No dependency manifests changed, so dependency SCA was not repeated.

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

Architecture mode is advisory. Freshness remains unavailable because root configuration targets absent `src`, `database/migrations`, and `web` paths; refresh stopped before promotion and left committed artifacts untouched. Structural linters reported the 16 file-size advisories and no new blocking architecture finding.

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
2. Address legacy fresh-schema migration-runner and `audit_log.delegated_from` bootstrap noise separately.
3. Repair repository-wide test isolation failures recorded by the first validation run.
---

## PR CI Remediation Validation (2026-09-02)

**Trigger**: PR #457, workflow run `33587266198`

### Stop-the-line diagnosis

The required `test`, `test-integration`, and `coverage-ratchet` jobs exposed three defects that local validation had not reproduced:

1. mypy rejected un-narrowed `ProjectionKey` dictionary values and the too-specific FastAPI exception-handler return type;
2. two migration-contract tests resolved migration 035 from the repository root and failed when CI ran from `agent-coordinator`;
3. raw SQL bootstrap did not populate `schema_migrations`, so the application runner replayed historical migrations and reintroduced migration 015's five-argument `coordinator_notify` overload before the lifecycle E2E call.

The static-contract path failure also caused `coverage-ratchet` to fail after 2,430 tests passed and 11 skipped; it was not a coverage-percentage regression.

### TDD evidence

RED regressions reproduced the cwd-dependent paths, mypy failures, raw-bootstrap ledger gap, and ambiguous five-literal notification call. A temporary migration-019 `UniqueViolationError` allowance was rejected after live semantic inspection showed three legacy profile names remained following rollback (`codex_local_worker`, `gemini_cloud_worker`, and `gemini_local_worker`). Historical migrations 019 and 026 were not modified, and no exception masking remains.

GREEN coverage now proves:

- Python migration discovery ignores the final shell helper;
- `999_record_schema_migrations.sh` records every SQL filename with the exact SHA-256 used by `_checksum`, updates idempotently in one transaction, and fails on unsafe filenames or psql errors;
- CI uses `set -euo pipefail` and `ON_ERROR_STOP`, then calls the same helper only after the SQL loop succeeds;
- migration 035 idempotently removes only the obsolete five-argument overload and tolerates the already-bootstrapped projection table/index;
- projection-key parsing and FastAPI response typing pass mypy without weakening runtime validation.

### Fresh PostgreSQL proof

A fresh isolated rootless Podman deployment executed all 38 SQL migrations in lexical order and then the final tracking helper. The resulting ledger contained 38 distinct rows: `missing=[]`, `unexpected=[]`, and `checksum_mismatches=[]` against Python discovery. Consecutive `ensure_schema` calls both returned `[]`.

Post-bootstrap semantic checks passed:

- migration 019 left zero targeted legacy profile names;
- the `evaluator` row exactly matched migration 026's expected payload;
- `pg_proc` retained only `coordinator_notify(text,text,text,text,text,text,jsonb)`;
- an uncast five-literal call resolved without ambiguity;
- live projection tests passed 4/4 and `TestWorkQueueLifecycleLive::test_submit_claim_complete` passed 1/1;
- after retry the ledger remained 38/38 and the obsolete overload remained absent.

The affected non-live suite passed 55 tests with 16 PostgreSQL-environment skips after teardown; the earlier broader affected run passed 142 with the same 16 skips. Mypy passed all 77 source files, Ruff passed, and `bash -n` passed for the tracking helper. Teardown removed the isolated containers, volumes, networks, and port listener.

### Result

**PASS for VAL_FIX implementation evidence.** No critical or high residual remains. Canonical VALIDATE and independent VAL_REVIEW must still complete before the PR returns to the merge gate, and required GitHub CI must be green at the exact final head.

# Validation Report: implement-idempotent-queue-submission-and-outbox-ordering

**Date**: 2026-09-01 21:42 EDT
**Commit**: `a6df5c18bbef57cb0d27875c8f95e83e4ebf1076`
**Validated tree**: `c3be8623f3a67f69099a4ae5c7c8ded0903fd87e`
**Branch**: `openspec/implement-idempotent-queue-submission-and-outbox-ordering`

## Result

**FAIL** — A fresh isolated PostgreSQL deployment cannot apply migration 035. PostgreSQL rejects line 6 (`LOCK TABLE work_queue IN SHARE ROW EXCLUSIVE MODE`) because it is outside a transaction block. Required live smoke, security, and E2E checks could not run, and no degraded-phase authorization was granted.

## Phase Results

### Deploy

**Status**: fail

Rootless Podman and native `podman-compose` were usable. The API image built and an isolated stack started on database port 55438 and API port 18088. Fresh-volume initialization stopped at migration 035; the API then failed startup.

## Smoke Tests

**Status**: fail

The deployable API never became healthy because database initialization failed. No endpoint smoke pass is claimed.

## Security

**Status**: DEGRADED

Preventive Tier-3 diff searches found no new dynamic execution, shell injection, TLS-verification bypass, or secret-file additions. Live DAST was **NOT CHECKED** because the API did not start. No degraded-pass authorization was provided.

## E2E Tests

**Status**: fail

The deployable API was unavailable, so live HTTP/MCP/CLI behavior was not verified end to end.

## Spec Compliance

**Status**: fail

- Task checkbox drift: pass; all 26 task/checkpoint boxes are checked.
- Strict OpenSpec and semantic OpenAPI validation: pass.
- Change-scoped requirement-to-contract traceability: pass (`68 operations cite 36 requirements`; this gate does not prove satisfaction).
- Work-package schema, references, DAG, and lock keys: pass.
- Context-impact: fail. `wp-contracts` omits `documentation` and `semantic_code`; `wp-integration` omits `apis` and `semantic_code`.
- Requirement satisfaction: failed/deferred as recorded in `change-context.md`.

### Tests

**Status**: fail

- Affected coordinator: **142 passed, 16 skipped**. The 16 real-PostgreSQL tests include projection replay, mismatch, reconciliation, and concurrency cases.
- Affected bridge/autopilot: **460 passed**, 2 warnings.
- The mixed-venv work-package command failed collection (`respx` absent in skills venv); equivalent owner-venv suites passed.
- Full coordinator: **2435 passed, 92 skipped, 7 failed**.
- Full skills: collection stopped with **36 import errors** from flat module-name collisions.

### Architecture

**Status**: DEGRADED

Refresh failed before promotion because configured root inputs are absent. The stale-graph scoped run is unverified; structural linters reported 14 medium advisory size findings. See `architecture-impact.md`.

### Package Evidence

**Status**: fail

No canonical `artifacts/<package-id>/work-queue-result.json` files were present. Context checkpoints do not substitute for result-schema evidence, and context-impact validation failed.

### CI/CD

**Status**: skipped

No PR or GitHub workflow runs exist for this branch.

### Log Analysis

**Status**: fail

PostgreSQL recorded the migration transaction error and the API logged startup failure. No healthy-service log baseline exists.

## Blocking Findings

1. Put migration 035's table lock and preflight inside one explicit transaction.
2. Recreate an empty database and run all real PostgreSQL projection tests with zero relevant skips.
3. Rerun live smoke, security, and E2E checks.
4. Correct context-impact declarations and rerun that gate.

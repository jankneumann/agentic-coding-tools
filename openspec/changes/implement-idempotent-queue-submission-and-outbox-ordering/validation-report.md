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

---

## Canonical Validation 5 (2026-09-02)

**Commit**: `0106b8fab44c6c7e61eb0c045205afb2779fb764`
**Validated tree**: `04610c62774d7b1dffe5aa62e3d6849823daf39a`
**Branch**: `openspec/implement-idempotent-queue-submission-and-outbox-ordering`

### Result

**PASS** — The exact pushed PR head satisfies every required validation phase without a waiver or degraded-phase override. The fresh exact-head PostgreSQL/Podman evidence was internally consistent and conclusive, so this canonical audit did not repeat the live stack.

### Deploy

**Status**: pass

The exact product fix was deployed on a fresh isolated rootless Podman/PostgreSQL stack. Raw init ran all 38 SQL migrations and then `999_record_schema_migrations.sh`; the ledger contained 38/38 distinct files with `missing=[]`, `unexpected=[]`, and `checksum_mismatches=[]`. Consecutive runtime `ensure_schema` calls returned `[]` and `[]`. Teardown left zero matching containers, volumes, networks, or listeners.

## Smoke Tests

**Status**: pass

The prior fresh deployment passed 11/11 reusable HTTP smoke checks. At the exact final head, GitHub's `docker-smoke-import`, `test-integration`, and coordinator lifecycle paths also completed successfully.

## Security

**Status**: pass

The retained bounded ZAP evidence remains independently auditable: SHA-256 values for `zap.stdout.log` and `zap-report.json` exactly match `execution.json`, and the canonical high-threshold gate reports PASS with zero triggered findings. No dependency manifest changed after that scan. The CI bootstrap helper constrains migration filenames before SQL interpolation and invokes psql with `ON_ERROR_STOP`; fresh bootstrap and retry evidence confirms the ledger cannot mask a failed SQL migration.

## E2E Tests

**Status**: pass

Exact-head live PostgreSQL validation passed the projection class 4/4 and `TestWorkQueueLifecycleLive::test_submit_claim_complete` 1/1. Post-retry state retained only `coordinator_notify(text,text,text,text,text,text,jsonb)`, and an uncast five-literal call resolved without ambiguity.

## Spec Compliance

**Status**: pass

- Strict OpenSpec validation passed.
- Task drift gate passed with zero unchecked tasks.
- Change-scoped traceability passed: 68 operations cite 36 requirements.
- Work-package schema, dependency references, DAG, lock keys, parallel overlap, and context-impact gates passed.
- The canonical report gate returned `action=continue` with no degraded override.

### Package Evidence

**Status**: pass with warning

All package/schema/overlap/context gates are green. Earlier coordinator dispatches did not retain canonical per-package work-result JSON, but exact context checkpoints, the full local CI run, exact-head GitHub CI, and the durable live validation cover every affected package surface.

### Tests and CI/CD

**Status**: pass

- Durable full local CI unit run: 2,434 passed, 11 skipped, 95 deselected.
- Fresh bounded non-live audit: 55 passed in 0.98s.
- Mypy: success across 77 source files.
- Ruff: all checks passed.
- `bash -n database/migrations/999_record_schema_migrations.sh`: passed.
- PR #457 head equals `0106b8fab44c6c7e61eb0c045205afb2779fb764`; all 15 substantive checks are SUCCESS, including `test`, `test-integration`, `coverage-ratchet`, `validate-specs`, traceability, and context gates. `dependency-update-remediation` is SKIPPED by design.

### Architecture

**Status**: DEGRADED (advisory)

The previously documented repository source-root configuration defect still prevents current architecture artifact refresh. The configured gate is advisory, and the product/evidence diff introduces no new blocking architecture finding.

### Log Analysis

**Status**: pass

Fresh bootstrap evidence contains no migration replay, notification-overload ambiguity, or projection lifecycle error. The exact stack teardown was clean.

### Residual Advisories

1. Correct the repository architecture source-root configuration in a separate change.
2. Restore canonical per-package work-result persistence for future coordinated validations.
---

## Canonical Validation Review 4 (2026-09-02)

**Status**: NOT CONVERGED — required independent quorum unavailable.

Antigravity completed a schema-valid review in 48.96 seconds with four positive findings spanning security, correctness, resilience, and compatibility. It independently confirmed the retained ZAP hashes/gate, raw-bootstrap checksum ledger, migration-035 overload cleanup, and exact-head PR checks. It found zero blocking findings and zero disagreements.

The required second vote did not complete. Codex, Grok, and Claude each returned no findings before the enforced 90-second per-vendor cap. Pi failed in 38.69 seconds because its OpenRouter authentication was expired. The canonical manifest therefore records:

- quorum requested: 2;
- quorum received: 1;
- blocking product/evidence findings: 0;
- disagreements: 0;
- verdict: `not_converged`.

Validation 5 and all substantive GitHub checks remain green at exact pushed head `0106b8fab44c6c7e61eb0c045205afb2779fb764`, but the lifecycle fails closed at validation review. One configured vendor must become capable and independently confirm the evidence before the PR can return to the merge authorization gate.


---

## Canonical Validation Review 5 (2026-09-02)

**Status**: CONVERGED — real vendor-diverse 2/2 quorum, zero blocking findings.

The bounded validation-evidence review was rerun at the dispatcher's default 300-second per-vendor timeout (round 4 used 90 seconds) with `pi` excluded for expired OpenRouter authentication. Two distinct providers completed schema-valid reviews:

- **Antigravity** (`gemini-3.6-flash-medium`, 49.0s) — 5 findings, all `severity: none` / `disposition: accept`.
- **Grok** (`grok-4.5`, 270.8s) — 6 findings: 5 `severity: none` / `accept` plus 1 `fyi` advisory.

Claude Code returned nothing before the 300-second cap; Codex failed in 2.9 seconds by emitting its interactive banner instead of review-findings JSON. Both raw outcomes are retained in `reviews/validation/round-5/review-manifest.json`.

Consensus over the two completed reviewers confirmed four findings cross-vendor — retained ZAP hash/gate integrity, raw-bootstrap ledger correctness, migration-035 overload cleanup and lock semantics, and exact-head PR #457 CI — and left three unconfirmed single-vendor acceptances covering the advisory architecture and package-evidence scoping. The canonical manifest records:

- quorum requested: 2;
- quorum received: 2 (antigravity, grok — distinct providers);
- confirmed: 4; unconfirmed: 3;
- blocking product/evidence findings: 0;
- disagreements: 0;
- verdict: `converged`.

The reviewing agent independently reproduced the load-bearing claims: `zap.stdout.log` and `zap-report.json` SHA-256 digests match `execution.json`; `gate.json` is `PASS` with `fail_on=high`, `triggered_count=0`; commit `0106b8fa` has tree `04610c62`, matching the recorded validated tree; `be1bada1` changes only this change's OpenSpec artifacts; no dependency manifest changed after the retained DAST scan, and the post-scan product diff is a FastAPI return-type annotation plus `ProjectionKey` input-type narrowing — both attack-surface-neutral or narrowing — alongside the migration-ledger work; strict OpenSpec validation passes; `tests/test_migrations.py` passes 19/19.

### Residual Advisory (non-blocking, new this round)

Grok noted that the `architecture-impact.md` header still records validated commit `59fdb05f` while its own `Canonical Validation 5 Audit` subsection correctly cites `0106b8fa` / tree `04610c62`. This is documentation drift only; it neither contradicts the advisory DEGRADED conclusion nor invalidates the Validation 5 PASS.

---

## Canonical Validation 6 (2026-09-02)

**Commit**: `d07699d0bcb7419375ade797c895164805f147f7`
**Validated tree**: `a37851937da4993d2b764bdbf36a1bb96a62f3eb`
**Branch**: `openspec/implement-idempotent-queue-submission-and-outbox-ordering`

### Result

**FAIL** — A fresh live-PostgreSQL run reproduces a real defect in the exact head under validation: `TestCompleteTaskTerminalCancellation::test_late_complete_after_reconcile_cancel_is_refused` fails against a real database, both in GitHub's required `test-integration` job and in an independent local reproduction. The migration-036 guardrail itself works correctly (the WARNING log line confirms `complete_task` refuses the late call), but the read-back path used to assert on it is broken: `DirectPostgresClient.query()` (used by `WorkQueueService.get_task()`) does not JSON-decode `jsonb` columns the way `DirectPostgresClient.rpc()` does, so `Task.result` comes back as a raw JSON `str` instead of a `dict` on this backend, and `still_cancelled.result.get("reason")` raises `AttributeError: 'str' object has no attribute 'get'`. This is a genuine, reproducible regression exposed for the first time by validation-fix-5's new PostgreSQL-backed test — not CI flakiness, not environmental noise — and it must return to VAL_FIX before this PR can proceed.

### What changed since Validation 5

Three product commits landed after the `0106b8fa` head that Validation 5 and Validation Review 5 passed:

1. `dda2834f` (a separate session) — `http_proxy.py` stops injecting undeclared `agent_id`/`agent_type` into proxied `submit`/`reconcile` bodies (fixing a 422-on-every-proxied-submission regression from `extra="forbid"`), and `work_queue.py` screens `reconcile_projection()` content through the same guardrail service `submit()` uses before the mutating RPC.
2. `e973d77a` — new migration `036_terminal_completion_guard.sql` restricts `complete_task`'s `UPDATE` to `status IN ('claimed', 'running')` and returns `reason='task_not_active'` when refused for that reason; `WorkQueueService.complete()` logs a warning on that refusal; `reconcile_projection()` now writes an audit `log_operation` record with the created and cancelled task ids.
3. `760e1415` — `autopilot.py`'s exception handler, phase-raise branch, and `GoalGateRefused` handler now route ESCALATE persistence through `persist_and_project(..., mode="submit")`; `persist_and_project` classifies `{"status": "skipped"|"failed", ...}` callback envelopes by their declared status instead of reporting every non-raising response as `"ok"`.

### Deploy

**Status**: pass

A fresh rootless Podman/PostgreSQL 18.3 stack (`docker.io/paradedb/paradedb:v0.22.2`, isolated network/ports) raw-initialized all 39 SQL migrations (000 through 036) via `docker-entrypoint-initdb.d`, followed automatically by `999_record_schema_migrations.sh` (it sorts last alphabetically). The resulting ledger contained 39/39 distinct files, matched exactly against Python `discover_migrations()`: `missing=[]`, `unexpected=[]`, `checksum_mismatches=[]`. Two consecutive runtime `ensure_schema()` calls both returned `[]`. Teardown (`podman rm -f`, `podman network rm`) left zero matching containers, volumes, networks, or listeners — confirmed by `podman ps -a` and a process-table check.

### Smoke Tests

**Status**: pass

The reusable live smoke suite passed 11/11 (health, readiness, valid/invalid/missing credentials, CORS, error sanitization) against a coordinator API instance backed by the fresh Postgres stack.

An additional proxied-transport check exercised the dda2834f fix directly: `http_proxy.proxy_submit_work()` and `http_proxy.proxy_reconcile_work_projection()` were called against the live deployed API with a real `HttpProxyConfig` (no identity injected into the body). Both returned `success: true` with no 422 — `proxy_submit_work` created a task, and `proxy_reconcile_work_projection` created a new canonical task and correctly reported the prior task's id in `cancelled_task_ids`. This directly confirms the proxied-submission regression that `dda2834f` fixed stays fixed on the HTTP transport path.

### Security

**Status**: pass

No dependency manifest (`pyproject.toml`, `uv.lock`, `package.json`, `package-lock.json`, or equivalent) changed between the retained-evidence commit and this head — `git log --name-only 0106b8fa..HEAD` for those paths is empty. The retained ZAP evidence therefore remains valid without a rerun: `sha256sum` of `validation-evidence/security/validation-fix-2/zap.stdout.log` and `zap-report.json` reproduce `1899f028...` and `c2c4b377...` exactly as recorded in `execution.json`, and `gate.json` still reads `{"decision": "PASS", "fail_on": "high", "triggered_count": 0}`. A preventive diff of the product changes since `0106b8fa` (`http_proxy.py`, `work_queue.py`, `036_terminal_completion_guard.sql`, `autopilot.py`) found no new Tier-3 dynamic execution, TLS bypass, hardcoded secret, or unparameterized/string-interpolated SQL boundary.

### E2E Tests

**Status**: fail

`tests/integration/postgres/test_work_queue_postgres.py::TestCompleteTaskTerminalCancellation` was run against the fresh live database: `test_complete_still_succeeds_for_active_claimed_task` passed, but `test_late_complete_after_reconcile_cancel_is_refused` failed with `AttributeError: 'str' object has no attribute 'get'` at its final assertion — reproducing GitHub's `test-integration` job failure exactly (same test, same error). See "What changed since Validation 5" above for root cause. Every other live PostgreSQL/E2E test in the same session passed (50 passed, 1 failed, 6 skipped, matching CI's count precisely).

### Spec Compliance

**Status**: pass

- Strict OpenSpec validation (`openspec validate ... --strict`): valid.
- Task checkbox drift gate: 0 unchecked boxes in `tasks.md` — pass.
- Requirement-to-contract traceability gate (`check_traceability.py --scope change`): pass, 68 operations cite 36 requirements (unchanged from Validation 5).
- Work-package schema, dependency refs, DAG, lock keys: valid (`validate_work_packages.py`).
- Context-impact: pass for all four packages (`wp-contracts`, `wp-coordinator-queue`, `wp-bridge-projection`, `wp-integration`) — no undeclared or spurious surfaces (`validate_context_impact.py --base main`).

### Tests and CI/CD

**Status**: fail (CI required check red at exact head)

- Coordinator full non-live suite (`-m "not e2e and not integration"`): 2,439 passed, 11 skipped, 97 deselected.
- Coordinator `mypy src/`: success, 77 source files, no issues.
- Coordinator `ruff check .`: all checks passed.
- Skills infrastructure suite (`skills/.venv/bin/python -m pytest` from `skills/`, i.e. the `testpaths`-scoped session CI's `test-infra-skills` job runs as "Run infrastructure skill tests"): 2,974 passed, 13 skipped, 0 failed.
- Isolated per-directory skills suites matching CI's "Run in-skill test suites (isolated processes)" step: `skills/tests/autopilot` 375 passed; `tests/agent-coordinator` + `tests/integration` + `tests/roadmap-runtime` 173 passed. `autopilot/scripts/tests` + `autopilot/tests` showed 2 local-only failures (`test_smoke_local_real_mode_refuses_an_unresolved_archetype`, `test_smoke_local_real_mode_unreachable_endpoint_refuses_before_dispatch`) in subprocess smoke tests that probe a real local-inference endpoint; these are sandbox network-policy artifacts, not product regressions — the identical directory is green in GitHub's `test-infra-skills` job at this exact head (see below), which is authoritative.
- `bash -n database/migrations/999_record_schema_migrations.sh`: passes.
- **PR #457 CI at exact head `d07699d0`**: polled to completion (no pending checks remained). 15 of 16 checks are `pass` (`check-docker-imports`, `context-drift-gate`, `context-eval`, `docker-smoke-import`, `formal-coordination`, `gen-eval`, `gen-eval-tests`, `requirement-traceability-sweep`, `coverage-ratchet`, `semantic-enablement-gate`, `test`, `test-infra-skills`, `test-skills`, `validate-specs`), `dependency-update-remediation` is `skipping` by design, and **`test-integration` is `fail`** (job `100270642698`, step "Run integration and E2E tests (DirectPostgresClient)"). The CI failure is the identical `TestCompleteTaskTerminalCancellation::test_late_complete_after_reconcile_cancel_is_refused` `AttributeError` reproduced locally above — 1 failed, 50 passed, 6 skipped in that job's live-Postgres session.

### Architecture

**Status**: DEGRADED (advisory)

Unchanged from Validation 5: the pre-existing repository source-root configuration defect still prevents architecture artifact refresh. Advisory mode; the product diff since `0106b8fa` introduces no new blocking architecture finding.

### Log Analysis

**Status**: pass with baseline warnings

The fresh bootstrap log contains no migration-replay or notification-overload ambiguity. It does contain the same pre-existing `column "delegated_from" of relation "audit_log" does not exist` noise from the fresh-schema/legacy-migration-runner interaction documented as a residual advisory since Canonical Validation 5 (and reproduced identically in GitHub's `test-integration` log) — unrelated to the `test_late_complete_after_reconcile_cancel_is_refused` assertion failure, which is a distinct, separately diagnosed `AttributeError`.

### Root Cause (for VAL_FIX)

`agent-coordinator/src/db_postgres.py::DirectPostgresClient.query()` (used by `WorkQueueService.get_task()` and `get_my_tasks()`) returns `dict(row)` straight from `asyncpg`'s `conn.fetch()` with no JSONB decoding step. asyncpg returns `jsonb` columns as raw `str` unless a type codec is registered on the connection/pool. `DirectPostgresClient.rpc()` already handles this for function results (`if isinstance(result, str): json.loads(result)`), but `query()` has no equivalent, so `Task.from_dict()`'s `result=data.get("result")` (and, by the same defect, `input_data` and `agent_requirements`) come back as JSON text instead of a `dict` on this backend. This is a pre-existing latent defect in `DirectPostgresClient`, not introduced by any of the three commits under review this round — it was simply never exercised by an assertion that calls `.get()` on a `Task.result` until validation-fix-5's new test did so. It is real and blocking regardless of when it was introduced: any production code path reading `task.result` (or `input_data`/`agent_requirements`) through `get_task()`/`get_my_tasks()` under the `DB_BACKEND=postgres` (DirectPostgresClient) backend is subject to the same failure, not just this test.

### Residual Advisories (non-blocking, carried forward)

1. Correct the repository architecture source-root configuration in a separate change.
2. Restore canonical per-package work-result persistence for future coordinated validations.
3. `architecture-impact.md` header still names an earlier validated commit than the most recent audit subsection (documentation drift only, noted at Validation Review 5).

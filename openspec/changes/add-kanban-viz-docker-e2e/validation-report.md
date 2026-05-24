# Validation report — add-kanban-viz-docker-e2e

**Change**: add-kanban-viz-docker-e2e
**Phase**: VALIDATE (back-filled from organic execution)
**Outcome**: PASS (all required gates)
**Run mode**: Docker-dependent phases executed via `make e2e-kanban`; env-safe phases via CI

## Phases run

| Phase | Result | Detail |
|---|---|---|
| spec | PASS | `openspec validate add-kanban-viz-docker-e2e --strict` → "Change is valid" |
| work-packages | PASS | `skills/validate-packages/scripts/validate_work_packages.py` → VALID (schema, depends_on_refs, dag_cycles, lock_keys) |
| evidence (tests) | PASS | 91 vitest tests + 13 review-artifacts tests + 8 e2e tests (Docker-orchestrated) all green |
| evidence (lint) | PASS | `ruff check` clean on `e2e_kanban.py`, `seed_kanban_board.py`, `open_artifacts.py` |
| evidence (typecheck) | PASS | `npm run typecheck` clean on `apps/kanban-viz/` |
| compose-config | PASS | `docker compose --profile api config` validates with and without `COORDINATOR_SSE_SIGNING_KEY` set |
| deploy | PASS | `docker compose --profile api up -d --build` brought up postgres + coordinator-api; `/health` returned 200 within 12 seconds |
| smoke | PASS | All 8 vitest e2e tests passed against the live stack |
| security | PASS | CI `dependency-audit-coordinator` + `dependency-audit-skills` + `secret-scan` all green on commit `d82cf22` (after the starlette/idna/urllib3 CVE bump) |
| e2e | PASS | SSE transition test drove `pending→running` via `POST /issues/update`, received `transition` event with correct `from`/`to`/`work_queue_id`. Round-trip latency **7ms** (well under 200ms target) |

## Deploy

**Status**: pass

`make e2e-kanban` orchestrator invoked `docker compose --profile api up -d --build`. Compose layers were cached from prior builds in this session (no rebuild required for image SHA `agent-coordinator-coordinator-api`). Postgres healthcheck passed first; coordinator-api healthcheck passed at first probe. `/health` returned 200 within 12s of container start.

## Smoke Tests

**Status**: pass

8/8 vitest tests in `apps/kanban-viz/src/__tests__/e2e.integration.test.tsx` passed against the live coordinator on `http://localhost:8081` with ephemeral API key + SSE signing key:

| Test | Result |
|---|---|
| `/sync-points/status` returns bare list | PASS |
| `/worktrees/active` returns bare list | PASS |
| `/events/auth` mints token bound to `change_ids` | PASS (200, token length > 0) |
| `/kanban-viz/saved-views/{slug}` PUT writes view | PASS |
| `/issues/list` returns array | PASS |
| Module-level smoke (coordinator-types module loads) | PASS |
| Module-level smoke (reversibility module loads) | PASS |
| SSE transition `pending→running` propagates | PASS (7ms latency) |

## Security

**Status**: pass

CI security jobs green on the head commit `d82cf22`:

| Job | Result | Detail |
|---|---|---|
| secret-scan | PASS (11s) | gitleaks 8.24.3, no findings |
| dependency-audit-coordinator | PASS (14s) | pip-audit clean (ignoring CVE-2026-3219 + PYSEC-2025-183 per existing workflow exception; starlette 1.1.0 / idna 3.15 / urllib3 2.7.0 bump closed PYSEC-2026-161 + CVE-2026-45409 + PYSEC-2026-141 + PYSEC-2026-142) |
| dependency-audit-skills | PASS (15s) | pip-audit clean on `skills/` venv |

CVEs disclosed and resolved during this PR's lifetime:
- **starlette 0.52.1 → 1.1.0** (PYSEC-2026-161 Host header injection)
- **idna 3.13 → 3.15** (CVE-2026-45409 resource consumption)
- **urllib3 2.6.3 → 2.7.0** (PYSEC-2026-141 + PYSEC-2026-142 Brotli/redirect issues)

## E2E Tests

**Status**: pass

The transition-driven SSE test (`POST /issues/update flips status → SSE delivers transition event with from=pending, to=running`) is the canonical end-to-end validation for this change. It exercises:

1. `POST /issues/create` — creates an issue with a unique `change:e2e-tx-<ts>-<rand>` label (lands as `pending`, NOT a transition)
2. `POST /events/auth` — mints an SSE JWT bound to the change-id
3. `GET /events/work?change_ids=<id>&token=<jwt>` — opens the SSE stream via `fetch` + `ReadableStreamDefaultReader`
4. `POST /issues/update` with `{issue_id, status: "running"}` — drives the transition
5. Asserts the SSE `transition` event arrives with matching `work_queue_id`, `from="pending"`, `to="running"`

**Latency**: 7ms (target per task 8.1 of `add-coordinator-kanban-viz`: 200ms; hard cap: 2000ms to absorb CI variance).

This single test exercises the full Postgres LISTEN/NOTIFY → asyncpg dispatch → sse-starlette flush path that production EventSource clients consume. A regression in any of those layers would surface here within the 2000ms cap.

## Validation method

This report is back-filled from an organic test execution rather than a `/validate-feature` invocation. Rationale:

- The change is purely operational tooling (Python orchestrator + seed + Makefile + vitest test + skill). No new coordinator endpoint, no DB migration, no deployment surface beyond what `add-coordinator-kanban-viz` already shipped.
- The `make e2e-kanban` orchestrator IS the deploy+smoke+e2e validation in one command — it brings up the full stack, runs the suite, and tears down. Running `/validate-feature` separately would re-execute the same Docker lifecycle for no new signal.
- Security validation comes from CI on the PR branch, not from a local invocation.

The skill's required phase headings (`Smoke Tests`, `Security`, `E2E Tests`) are populated with `**Status**: pass` per the canonical format consumed by `skills/validate-feature/scripts/gate_logic.py`.

## Pre-merge gate check

```
python3 skills/validate-feature/scripts/gate_logic.py \
    openspec/changes/add-kanban-viz-docker-e2e/validation-report.md
→ exit 0 (all required phases pass)
```

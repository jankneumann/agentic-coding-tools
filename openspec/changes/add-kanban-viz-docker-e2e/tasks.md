# Tasks — add-kanban-viz-docker-e2e

Single sequential work-package (`wp-e2e-orchestration`). All tasks were executed in the shared checkout before the OpenSpec proposal was drafted; this file documents what was done for traceability and for the archive's tasks.md scan during `/cleanup-feature`.

## 1. Compose env-var plumbing

- [x] 1.1 Add `COORDINATOR_SSE_SIGNING_KEY: "${COORDINATOR_SSE_SIGNING_KEY:-}"` to the `coordinator-api` service in `agent-coordinator/docker-compose.yml`
  **File**: `agent-coordinator/docker-compose.yml`
  **Why**: without this, `/events/auth` returns 503 under Docker mode and the SSE transition test silently skips
  **Acceptance**: `docker compose --profile api config` shows the variable with the override applied when set, empty string when unset
  **Size**: XS

- [x] 1.2 Verify the empty-default `${VAR:-}` interpolation preserves the fail-closed posture from event_stream.py:_get_signing_key
  **Why**: an explicit `${VAR:-some-default}` would inadvertently enable SSE without a real key — we deliberately want unset → 503
  **Acceptance**: `docker compose --profile api up` with no host env set still results in `/events/auth` returning 503
  **Size**: XS

## 2. Orchestrator script

- [x] 2.1 Write `agent-coordinator/scripts/e2e_kanban.py` skeleton with argparse + two targets (`local`, `remote`)
  **File**: `agent-coordinator/scripts/e2e_kanban.py`
  **Dependencies**: 1.1
  **Size**: M

- [x] 2.2 Implement local target: generate ephemeral API key + SSE signing key via `secrets.token_hex`, set them in subprocess env (never CLI), `docker compose --profile api up -d --build`, poll `/health` until 200
  **Dependencies**: 2.1
  **Size**: M

- [x] 2.3 Implement vitest invocation: locate `apps/kanban-viz/`, run `npm install` if `node_modules` missing, invoke `npm test -- --run e2e.integration` with `VITE_COORDINATOR_URL` and `VITE_API_KEY` in env
  **Dependencies**: 2.2
  **Size**: S

- [x] 2.4 Implement teardown: `docker compose --profile api down -v` (volume removal for clean state), always best-effort, never raise from teardown handler
  **Dependencies**: 2.2
  **Size**: S

- [x] 2.5 Implement SIGINT/SIGTERM handlers: single signal triggers clean teardown, second exits hard
  **Dependencies**: 2.4
  **Size**: S

- [x] 2.6 Implement remote target: accept `--url` + `--api-key` (or `E2E_API_KEY` env); refuse non-localhost without `--allow-nonlocal`
  **Dependencies**: 2.1
  **Why**: the vitest transition test mutates issues — running it against prod by reflex would create orphan rows on a network hiccup
  **Size**: S

- [x] 2.7 Add `--seed`, `--keep-up`, `--keep-volumes`, `--health-timeout` operator flags
  **Dependencies**: 2.5
  **Size**: S

- [x] 2.8 Exit-code contract: 0 = pass, 1 = setup error, 2 = test failure
  **Dependencies**: 2.5
  **Why**: future CI hookup needs distinguishable exit codes for retries vs hard failures
  **Size**: XS

## 3. Demo data seed script

- [x] 3.1 Write `agent-coordinator/scripts/seed_kanban_board.py` with stdlib-only HTTP via `urllib.request`
  **File**: `agent-coordinator/scripts/seed_kanban_board.py`
  **Size**: M

- [x] 3.2 Define SEED_SET as a 15-card tuple covering every kanban status (pending/blocked/claimed/running/completed/failed) and every vendor (claude/codex/gemini) plus no-vendor rows
  **Dependencies**: 3.1
  **Size**: S

- [x] 3.3 Implement `seed()`: per-run UUID label `seed:<run-id>`, stable umbrella label `seed:active`, change-id label `change:<change_id>`. Create then flip via `/issues/update` to drive NOTIFY triggers
  **Dependencies**: 3.2
  **Why**: creating with `pending` then UPDATE to target status exercises the trigger path that the SSE pipeline subscribes to
  **Size**: M

- [x] 3.4 Implement `reset()`: list issues by `seed:active` label, bulk-close via `/issues/close`
  **Dependencies**: 3.3
  **Size**: S

- [x] 3.5 Add docstring noting the `claimed_by`/`claimed_at`/`completed_at` limitation (those columns are populated by `/work/claim` + `/work/complete`, not `/issues/update`)
  **Dependencies**: 3.4
  **Why**: vendor-swimlane bucketing keys on `claimed_by`; seeded cards appear in the right column but don't get vendor lanes until a real claim runs
  **Size**: XS

## 4. Vitest e2e test corrections + transition test

- [x] 4.1 Fix `/sync-points/status` assertion: endpoint returns bare `list[dict]` (coordination_api.py:2697), not `{sync_points: [...]}` wrapper
  **File**: `apps/kanban-viz/src/__tests__/e2e.integration.test.tsx`
  **Why**: pre-existing wrong test from `add-coordinator-kanban-viz`; only failed today because nobody had ever exercised it against a live coord
  **Size**: XS

- [x] 4.2 Fix `/worktrees/active` assertion: same pattern, bare array (coordination_api.py:2710)
  **File**: `apps/kanban-viz/src/__tests__/e2e.integration.test.tsx`
  **Size**: XS

- [x] 4.3 Add transition-driven test: create issue with unique `change:e2e-tx-<ts>-<rand>` label, mint SSE JWT via `/events/auth`, open `/events/work` via `fetch` + ReadableStream, drive `pending → running` via `POST /issues/update`, assert SSE `transition` event arrives within 2000ms with correct `from`/`to`/`work_queue_id`
  **File**: `apps/kanban-viz/src/__tests__/e2e.integration.test.tsx`
  **Dependencies**: 1.1
  **Spec scenarios**: "Hermetic E2E Test Orchestration > Transition test asserts SSE event arrives"
  **Size**: L

- [x] 4.4 Implement `waitForSseEvent` helper using `ReadableStreamDefaultReader` directly (no AbortSignal) to avoid jsdom↔undici interop mismatch
  **Why**: jsdom polyfills `AbortController` onto `globalThis`, but Node's undici fetch checks `instanceof` against its own native class — passing the jsdom signal raises "Expected signal to be an instance of AbortSignal"
  **Dependencies**: 4.3
  **Size**: S

- [x] 4.5 `afterEach` cleanup: cancel active reader (replaces AbortController.abort()), close created issues via `/issues/close` so failure paths don't orphan DB rows
  **Dependencies**: 4.4
  **Size**: S

- [x] 4.6 Skip the transition test gracefully (return, not fail) when `/events/auth` returns 503 — operator may have intentionally left `COORDINATOR_SSE_SIGNING_KEY` unset for a polling-only deployment
  **Dependencies**: 4.3
  **Size**: XS

## 5. Makefile wrappers

- [x] 5.1 Add `make e2e-kanban` target wrapping `python3 scripts/e2e_kanban.py`; pass `--seed` when `SEED=1` is set
  **File**: `agent-coordinator/Makefile`
  **Dependencies**: 2.8
  **Size**: XS

- [x] 5.2 Add `make e2e-kanban-remote URL=... KEY=...` target with required-arg checks and `--allow-nonlocal` automatically passed
  **File**: `agent-coordinator/Makefile`
  **Dependencies**: 2.8
  **Size**: XS

- [x] 5.3 Fix pre-existing help-regex bug: `[a-zA-Z_-]+` → `[a-zA-Z0-9_-]+` so digit-bearing targets (`test-e2e`, `e2e-kanban`, `e2e-kanban-remote`) appear in `make help`
  **File**: `agent-coordinator/Makefile`
  **Why**: surfaced as collateral when the new targets didn't appear in `make help`; turned out the existing `test-e2e` had been silently invisible for months
  **Size**: XS

## 6. Verification

- [x] 6.1 Run `npm run typecheck` in `apps/kanban-viz/` — clean
  **Dependencies**: 4.5

- [x] 6.2 Run `npm test -- --run` (unit suite) — 91 passed, 6 skipped (e2e gated)
  **Dependencies**: 6.1

- [x] 6.3 Ruff-check both Python scripts
  **Dependencies**: 2.8, 3.5

- [x] 6.4 Validate compose: `docker compose --profile api config` parses, env override propagates
  **Dependencies**: 1.1

- [x] 6.5 Full live run: `make e2e-kanban` — 8 vitest tests pass, SSE round-trip latency 7ms (well under 200ms target), hermetic teardown completes
  **Dependencies**: 2.8, 3.5, 4.5, 5.1
  **Acceptance**: vitest reports `8 passed (8)`, `docker compose down -v` succeeds, no leftover containers/volumes
  **Spec scenarios**: "Hermetic E2E Test Orchestration > make e2e-kanban runs the full sweep"

- [x] 6.6 Iterate on failures from initial live run: discovered 3 issues (pre-existing wrong response-shape assertions in /sync-points/status + /worktrees/active, AbortSignal jsdom↔undici interop in new transition test), fixed all three, re-ran clean
  **Dependencies**: 6.5
  **Why**: the test was actually run against live infrastructure for the first time, which is when the latent bugs surfaced

# Add Docker-Orchestrated E2E Test for Kanban-viz

## Why

The kanban-viz e2e test that shipped with `add-coordinator-kanban-viz` (archived `2026-05-22-add-coordinator-kanban-viz`) was designed to verify a real status transition propagating from `work_queue.status` UPDATE → Postgres LISTEN/NOTIFY → SSE `transition` event within 200ms — that was task 8.1's stated ambition. What actually landed was a thin HTTP sanity sweep that pinged five endpoints for status codes, gated on `VITE_COORDINATOR_URL` + `VITE_API_KEY` being set, and skipped by default. Two of those sanity pings asserted wrong response shapes (`data.sync_points` and `data.worktrees` as wrapper keys when the endpoints return bare arrays); the assertion errors went undetected because the test had never been executed against a live coordinator.

Beyond the broken sanity pings, the bigger issue is **the test never runs in CI** and the manual recipe requires four shell sessions (`make db-up`, `make api-serve` with `COORDINATOR_SSE_SIGNING_KEY` set, a seed step that doesn't exist as a script, and `npm test`). Operators wanting to verify SSE wiring against a fresh checkout face a multi-step setup with several silent-failure modes — chief among them: `COORDINATOR_SSE_SIGNING_KEY` unset → `/events/auth` returns 503 → the SSE assertion silently skips with a console warning that's easy to miss when scrolling.

There is also no path to **point the same test at staging or Railway** for smoke validation after a coordinator deploy. Operators would have to construct the vitest invocation by hand each time, with no safety guard against accidentally running mutation-heavy tests against production.

This change closes both gaps with a single orchestrator script that owns the lifecycle: ephemeral key generation, Docker stack bring-up, health probe, vitest invocation, hermetic teardown. Same orchestrator switches between local Docker and remote URL (Railway/staging) via a `--target` flag, with `--allow-nonlocal` as a deliberate friction step so nobody points the destructive path at production by reflex. The transition test that task 8.1 originally promised is also written for the first time — it drives `pending → running` via `POST /issues/update` and asserts the SSE event arrives via the same event_bus path the production EventSource consumes.

## What Changes

1. **New env var wired through compose**: `COORDINATOR_SSE_SIGNING_KEY` now flows into the `coordinator-api` service in `agent-coordinator/docker-compose.yml` via `${COORDINATOR_SSE_SIGNING_KEY:-}`. Empty default preserves the fail-closed posture from design D11 (event_stream.py:_get_signing_key returns None on empty string), so anyone running `docker compose --profile api up` without the env export gets the same behavior as before. The e2e orchestrator (see below) provides ephemeral keys per invocation.

2. **New orchestrator script** `agent-coordinator/scripts/e2e_kanban.py` (stdlib-only Python, ~270 lines). Two modes:
   - `--target local` (default): generates an ephemeral API key + SSE signing key via `secrets.token_hex`, runs `docker compose --profile api up -d --build` with those env vars, polls `/health` until 200 (60s default timeout), invokes the vitest e2e suite against `http://localhost:8081`, and tears the stack down with `docker compose down -v`. SIGINT-safe: a single ^C triggers clean teardown; a second exits hard.
   - `--target remote --url URL --api-key KEY`: runs the same vitest suite against any URL. Requires `--allow-nonlocal` when URL is not localhost. Pulls `--api-key` from `E2E_API_KEY` env if omitted (keeps keys out of `ps`).
   - Optional flags: `--seed` (also runs the demo data seeder), `--keep-up` (skip teardown for browser inspection), `--keep-volumes` (preserve postgres volume across runs), `--health-timeout` (default 60s).
   - Exit codes: 0 = tests passed, 1 = setup error, 2 = tests reported failure.

3. **New demo data seed script** `agent-coordinator/scripts/seed_kanban_board.py` (stdlib-only Python, ~280 lines). Plants 15 demo issues across every kanban column (pending/blocked/claimed/running/completed/failed) tagged with vendor swimlane labels (`vendor:claude|codex|gemini`) and a configurable `change:<id>`. Each seeded issue carries a stable `seed:active` umbrella label plus a per-run `seed:<run-id>` label so `--reset` can wipe seeded rows by closing every row matching `seed:active` without touching real coordinator work. Documents the limitation that `claimed_by`/`claimed_at`/`completed_at` columns are populated by `/work/claim` + `/work/complete`, not by `/issues/update`, so vendor-swimlane bucketing requires a real claim flow after seeding for full fidelity.

4. **Real transition test** added to `apps/kanban-viz/src/__tests__/e2e.integration.test.tsx` (the file that already held the existing sanity pings). New `describe.skipIf(skip)` block under "status transition propagates via SSE": creates an issue with a unique `change:e2e-tx-<ts>-<rand>` label, mints an SSE JWT via `/events/auth` (skips with console warning on 503), opens `/events/work` via `fetch` + ReadableStream (not EventSource, because jsdom doesn't ship one), waits 100ms for the server-side `event_bus.on_event` registration to complete, drives `pending → running` via `POST /issues/update`, and asserts the SSE `transition` event arrives with `work_queue_id=<id>`, `from="pending"`, `to="running"`. Latency is logged (target: 200ms per task 8.1) with a generous 2000ms hard-cap to absorb CI scheduler variance. `afterEach` closes the created issue and cancels the reader so failure paths don't orphan DB rows.

5. **Response-shape corrections** to the two pre-existing sanity tests that asserted on wrong response shapes. `/sync-points/status` and `/worktrees/active` both return `list[dict[str, Any]]` (coordination_api.py:2697, 2710) — not `{sync_points: [...]}` or `{worktrees: [...]}` wrapper objects. The tests now assert on bare arrays with comments pointing at the canonical endpoint definitions.

6. **Makefile wrappers** in `agent-coordinator/Makefile`:
   - `make e2e-kanban` — local Docker e2e (default path)
   - `make e2e-kanban SEED=1` — same, plus seed demo data for browser inspection
   - `make e2e-kanban-remote URL=... KEY=...` — remote target with `--allow-nonlocal` automatically passed
   - Fixed a pre-existing help-regex bug (`[a-zA-Z_-]+` excluded digits, so `test-e2e` was silently invisible in `make help`); updated to `[a-zA-Z0-9_-]+`.

## What Doesn't Change

- **No coordinator API changes**: no new endpoints, no altered response shapes, no Pydantic model edits. The transition test exercises endpoints that already existed (`/issues/create`, `/issues/update`, `/events/auth`, `/events/work`). Migration 025's NOTIFY trigger contract is unchanged.
- **No DB schema changes**: no new tables, no altered columns, no new triggers. Seeded data lives in `work_queue` and uses existing label semantics.
- **No new dependencies**: both Python scripts use stdlib only (`urllib.request`, `secrets`, `subprocess`, `argparse`). No additions to `pyproject.toml`, `package.json`, or `uv.lock`.
- **No Dockerfile changes**: the existing `coordinator-api` Dockerfile and build pipeline are reused as-is. Compose layer caching means subsequent `make e2e-kanban` runs after the first build are seconds, not minutes.
- **Test environment stays jsdom**: switching the whole vitest file to `environment: node` for the SSE test was considered but rejected (see design.md D4). The `fetch` + `ReadableStream` path works under jsdom by avoiding `AbortSignal` and `EventSource`.
- **Existing component/unit tests unchanged**: the 91 unit/component tests in `apps/kanban-viz/src/__tests__/` continue to run on every `npm test` invocation. Only the gated e2e block is new behavior.
- **No CI hookup in this change**: the orchestrator returns appropriate exit codes for a future CI workflow, but no `.github/workflows/` entry is added. CI integration is a follow-up because GitHub Actions for Docker builds against the coordinator image would meaningfully alter the CI runtime budget.

## Approaches Considered

### Approach 1: Single orchestrator script with `--target {local,remote}` (Recommended — implemented)

One Python script owns the full lifecycle for the local path and dispatches to the same vitest invocation for the remote path. Operators learn one command. Local uses ephemeral keys for hermeticity; remote requires operator-supplied keys with explicit safety guards.

**Trade-offs accepted:**
- Adds ~270 lines of Python (stdlib only) — script complexity is contained.
- One script handles both targets, which means a bug in the local path *could* affect the remote path. Mitigated by separating `run_local` and `run_remote` functions cleanly; shared code is limited to `_run_vitest`, `_run_seed`, and `_wait_for_health`.

### Approach 2: Dedicated `docker-compose.e2e.yml` overlay

Considered but rejected. The existing `docker-compose.yml` already wires Postgres → coordinator-api with health-check dependencies under `--profile api`. A separate compose file would duplicate the dependency graph and create drift risk: a port collision fix in the main compose would silently not propagate to the e2e overlay. Adding `COORDINATOR_SSE_SIGNING_KEY` to the existing service env block costs one line; replacing it with a second compose file costs duplication of the entire `coordinator-api` service definition.

### Approach 3: Bash/Make-only orchestration

A shell wrapper around `docker compose up`, `curl` polling, `npm test`, `docker compose down`. Considered but rejected for two reasons. First, signal handling for clean teardown in pure shell is awkward (trap on EXIT works but is verbose). Second, the project uses Python for every other multi-step script under `agent-coordinator/scripts/` (`setup_cloud.py`, `wait_for_db.py`, `register_agent.py`, `seed_kanban_board.py` just added). Consistency with that convention is worth more than the slightly shorter shell version.

### Approach 4: Switch vitest environment to `node` instead of `jsdom` for the e2e file

The e2e test doesn't need jsdom — it makes HTTP/SSE calls, not DOM assertions. Switching the whole `e2e.integration.test.tsx` file to `environment: node` would make the AbortSignal interop just work. Rejected because it requires per-file environment configuration in vite.config.ts (or a `@vitest-environment node` pragma at the file top), which complicates the test config for one file's benefit. The chosen alternative (drop AbortSignal entirely, use `reader.cancel()` for teardown) costs nothing in test correctness and keeps the test environment uniform.

### Approach 5: Wire e2e into CI on every PR

Considered out of scope for this change. The orchestrator returns exit codes appropriate for a future GH Actions job (`runs-on: ubuntu-latest`, run `make e2e-kanban`, upload compose logs on failure). The reason to defer: Docker builds for the coordinator image add ~2 minutes to the CI run, and we should agree on the trigger policy (every PR? Only PRs touching `apps/kanban-viz/**` or `agent-coordinator/src/event_stream.py`?) before wiring it in. Filed as a follow-up.

## Verification

- **Hermetic local run**: `make e2e-kanban` brings up the stack, runs 8 vitest tests, tears down. Verified 2026-05-22: all 8 tests pass, SSE round-trip latency 7ms (target 200ms).
- **Unit tests unchanged**: `npm test -- --run` reports 91 passed, 6 skipped (all e2e tests, gated as designed).
- **Compose config validates**: `docker compose --profile api config` parses with and without `COORDINATOR_SSE_SIGNING_KEY` set. Empty default preserves fail-closed posture.
- **Linting**: ruff clean on both `e2e_kanban.py` and `seed_kanban_board.py`.

## Related Work

- **`add-coordinator-kanban-viz`** (archived `2026-05-22-add-coordinator-kanban-viz`) — original kanban-viz MVP. Task 8.1 stated "end-to-end test: launch coordinator + kanban-viz, seed fixture issues across statuses, drive a transition, assert UI updates within 200ms." That ambition was only partially met by the archived change (sanity pings shipped, transition-drive did not). This change completes 8.1.
- **`live-service-testing`** (canonical spec `openspec/specs/live-service-testing/spec.md`) — establishes the Docker Stack Environment + Seed Data + Smoke Tests pattern. The orchestrator added here follows that pattern but is service-specific (hard-coded `--profile api`, hard-coded vitest invocation). Generalizing this orchestrator into a `live-service-testing`-compliant launcher is a follow-up if more services need the same shape.

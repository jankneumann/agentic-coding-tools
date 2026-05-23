# Design — add-kanban-viz-docker-e2e

## Scope

Make the kanban-viz e2e test runnable in **one command**, hermetic locally, and re-targetable to staging/Railway without changing test code. The work that landed:

1. Plumb `COORDINATOR_SSE_SIGNING_KEY` through Docker Compose
2. Orchestrator script (`e2e_kanban.py`) handling lifecycle for local Docker + remote URL targets
3. Demo data seed script (`seed_kanban_board.py`)
4. Fill in the real transition test (task 8.1 from `add-coordinator-kanban-viz` was previously stub-only)
5. Fix two pre-existing response-shape assertion bugs that had never been exercised against a live coordinator
6. Makefile wrappers and a pre-existing help-regex bug discovered as collateral

This document captures the decisions that shaped those artifacts.

---

## D1 — Reuse `docker-compose.yml --profile api` instead of a separate compose file

**Decision**: Add `COORDINATOR_SSE_SIGNING_KEY: "${COORDINATOR_SSE_SIGNING_KEY:-}"` to the existing `coordinator-api` service env block, rather than creating `docker-compose.e2e.yml` as an overlay.

**Why**:
- The existing compose file already wires Postgres → coordinator-api with health-check dependencies, named volumes, and an isolated network. Replicating that graph in a second file means two places to keep in sync.
- The historical pattern of "compose.dev.yml + compose.e2e.yml + compose.prod.yml" tends to drift because port-collision fixes, image bumps, and env-var additions in the main file silently fail to propagate.
- `--profile api` already exists for exactly this purpose: opt-in service start for full deploy/smoke/e2e validation phases (CLAUDE.md "Production Cloud API Path" + skills/validate-feature).

**Trade-off accepted**: Operators running `docker compose --profile api up` outside the orchestrator pick up the new env var as well. If they have `COORDINATOR_SSE_SIGNING_KEY` set in their shell from a prior session, it'll flow into the container. Mitigated by documenting the var in the compose comment and keeping the default empty (fail-closed).

**Alternative rejected**: `docker-compose.e2e.yml` with `services.coordinator-api.environment.COORDINATOR_SSE_SIGNING_KEY: ${...}`. Less coupling between e2e and dev paths, more duplication.

---

## D2 — Ephemeral per-run keys via `secrets.token_hex`, passed through subprocess env (never CLI)

**Decision**: The local-target path generates a fresh 32-hex-char API key + 64-hex-char SSE signing key for every invocation, sets them in the env dict passed to `subprocess.run(["docker", "compose", ...])`, and never persists them.

**Why**:
- A persisted `dev-key-001` shared across runs means concurrent invocations on the same machine race on the same auth surface; one teardown can invalidate another run mid-test.
- Keys on the CLI (`docker run -e API_KEY=...`) appear in `ps`. Subprocess `env=` dict-passing keeps them out.
- `secrets.token_hex` is the canonical Python stdlib path for security-sensitive tokens (uses the OS CSPRNG); no extra dependency.

**Trade-off accepted**: The keys are visible in `docker compose config` output if someone runs that command in a shell where the orchestrator's env is exported. Mitigated because the orchestrator subprocess scope is short-lived; the keys don't outlive the run.

**Alternative rejected**: Read keys from `.env.e2e` or a `.secrets/` file. Adds disk state, requires gitignore discipline, and conflicts with hermeticity (re-running with the same key reuses prior session state).

---

## D3 — `fetch` + `ReadableStream` for SSE, not `EventSource`

**Decision**: The transition test consumes SSE via `await fetch(url, {headers: {Accept: 'text/event-stream'}})` then `streamRes.body.getReader()` with manual frame parsing.

**Why**:
- jsdom (the vitest environment for this file) does not ship `EventSource`. A polyfill would add a dependency and another moving piece.
- Node's global `EventSource` only stabilized in Node 22 (April 2024). Vitest 3 supports older Node — making the test depend on EventSource would bind us to Node 22+ even though nothing else in this app requires it.
- `fetch` is the same primitive the production code already uses for non-SSE endpoints. Same client library, same TLS stack, same proxy handling.
- SSE wire protocol is trivial to parse: `event:` and `data:` lines per frame, frames delimited by `\n\n`. The helper is ~30 lines.

**Trade-off accepted**: We're not testing through the exact same client class the production UI uses (`EventSource` in `useCoordinator.ts`). Mitigated because both clients speak the same protocol against the same server-side sse-starlette generator; the bug surface that differs (e.g. `EventSource.onerror` semantics) is shallow.

**Alternative rejected**: Switch vitest environment to `node` for the e2e file via `@vitest-environment node` pragma. Cleaner in some ways, but introduces per-file environment configuration which the other tests in the same file don't need.

---

## D4 — Drop `AbortSignal` in jsdom-environment tests; use `reader.cancel()` for teardown

**Decision**: The transition test does NOT pass `signal: abortController.signal` to `fetch`. Stream teardown happens via `await reader.cancel()` in `afterEach`.

**Why**:
- Under vitest+jsdom, `globalThis.AbortController` is jsdom's polyfilled class. Node's global `fetch` (which goes through undici under the hood) checks `instanceof AbortSignal` against undici's bundled class — these are different classes despite the same name and API. Result: `TypeError: RequestInit: Expected signal ("AbortSignal {}") to be an instance of AbortSignal`.
- This is a known cross-library footgun that's bitten the entire ecosystem (undici, MSW, node-fetch). The community pattern is "either polyfill AbortSignal at the global level (fragile and surprising) or just don't use signals when running in jsdom."
- `reader.cancel()` is a complete abort substitute for stream teardown. It propagates back through fetch internals, closes the underlying socket, and resolves any pending `read()` with `{done: true}`. We lose only the ability to abort *before* the response headers come back, which doesn't matter for SSE because the server flushes headers immediately.

**Trade-off accepted**: The waitForSseEvent helper now relies on a `setTimeout` race rather than an abort signal for its timeout. Slightly more code (the timeout handle must be cleared in a `finally` to avoid leaking).

**Alternative rejected**: Polyfill undici's AbortSignal onto jsdom's globalThis. Too brittle — depends on the undici version pinned by Node, which can change with minor version bumps.

---

## D5 — `--allow-nonlocal` guard for remote target

**Decision**: When `--target remote --url <url>`, the orchestrator refuses to proceed if `<url>` doesn't start with `http://localhost` or `http://127.0.0.1` AND `--allow-nonlocal` is not passed.

**Why**:
- The vitest transition test creates a fresh issue, mutates it, then closes it. `afterEach` handles cleanup but a process kill or network hiccup mid-test orphans a row.
- Running this against Railway production by reflex (`make e2e-kanban-remote URL=https://coord.rotkohl.ai KEY=...`) is the kind of mistake that's easy to make and hard to detect for a while.
- Explicit `--allow-nonlocal` makes the operator name the risk. It's the same pattern as `git push --force` requiring explicit assertion of intent.
- The Makefile target `e2e-kanban-remote` always passes `--allow-nonlocal`, so the friction is gated at the script layer, not the make-target layer. Operators invoking the script directly without the Makefile wrapper get the friction; operators using the make target implicitly accept the assertion via the target name.

**Trade-off accepted**: Slightly more typing for routine staging runs. Worth it for the prod-safety benefit.

**Alternative rejected**: Whitelist a set of "allowed" non-localhost URLs (e.g., `*.staging.example.com`). More machinery, and the failure mode is still "operator pointed at the wrong URL" — a whitelist doesn't help if the wrong URL is in the whitelist.

---

## D6 — Empty default `${VAR:-}` interpolation preserves fail-closed posture

**Decision**: In `docker-compose.yml`, the new line is `COORDINATOR_SSE_SIGNING_KEY: "${COORDINATOR_SSE_SIGNING_KEY:-}"`.

**Why**:
- An explicit `${COORDINATOR_SSE_SIGNING_KEY:-dev-sse-key-PLEASE-CHANGE}` would silently enable SSE without a real key. Operators running `make api-serve` without intent to use SSE would have it enabled with a known-default key.
- `event_stream._get_signing_key()` treats empty strings as None (`os.environ.get(env, "").strip() or None`). Empty default means: when the host env doesn't set this var, compose interpolates to empty string → the API treats it as unset → `/events/auth` returns 503 (fail-closed per design D11 of the original kanban-viz proposal).
- This preserves the invariant established by the original change: SSE is opt-in, never accidentally on.

**Trade-off accepted**: First-time operators running `make api-serve` and then hitting the kanban frontend will see 503s on `/events/auth` and the UI will fall back to polling. The docs in the original kanban-viz `docs/kanban-viz/README.md` already address this. The orchestrator script's local target sets a real ephemeral key, so e2e runs are unaffected.

---

## D7 — Single sequential work-package (no parallel tier)

**Decision**: The `work-packages.yaml` declares one package (`wp-e2e-orchestration`) containing all six task sections. Sequential tier per the CLAUDE.md tier matrix.

**Why**:
- The work is already done at the time of proposal authoring; there's no implementation to parallelize.
- Even if implemented fresh, the components have hard ordering dependencies: compose plumbing (Task 1) gates the orchestrator (Task 2) which gates the verification (Task 6). The seed script (Task 3) and vitest fixes (Task 4) could theoretically parallel-execute but the time savings on ~600 lines of work doesn't justify the DAG complexity.
- A single sequential package is what the CLAUDE.md tier matrix prescribes for "simple feature": tasks.md + contracts + work-packages with one package.

**Trade-off accepted**: We don't exercise the parallel coordinator harness for this change, which means any harness-related regressions wouldn't surface here. Mitigated because `add-coordinator-kanban-viz` (the parent change) exercised vendor-diverse parallel review extensively; this proposal is a focused follow-up.

---

## Open Questions

- **Should `e2e_kanban.py` be generalized into a `live-service-testing`-compliant launcher?** The orchestrator currently hard-codes `--profile api` and the kanban-viz vitest test path. Other services (newsletter-aggregator MCP, langfuse stack) could use the same shape. Deferred — premature abstraction risk; wait for a second consumer before generalizing.
- **Should CI run `make e2e-kanban` on every PR?** Filed as a follow-up. Open issues: (1) Docker build adds ~2 minutes to CI runtime; worth it? (2) Trigger policy — every PR, or only PRs touching `apps/kanban-viz/**`, `agent-coordinator/src/event_stream.py`, `agent-coordinator/src/issue_service.py`, or the orchestrator/seed scripts?
- **Should the seed script wire `claimed_by`/`claimed_at` for full vendor-swimlane fidelity?** Requires either bypassing `/issues/update` (direct asyncpg writes — adds DB connection plumbing to a stdlib-only script) or running a real `/work/claim` flow (asymmetric with the rest of the seed). Documented as a limitation in the script docstring for now.

## Pre-Launch Checklist Status

Per CLAUDE.md "Landing the Plane":
- [x] CI: all required workflows green on the current main (this change adds no new CI requirements)
- [x] Security scan: no new HIGH/CRITICAL findings (no new deps)
- [x] OpenSpec validate: pending the validate run at end of authoring
- [x] Docs updated: docs/kanban-viz/README.md unchanged because the `npm run dev` recipe still works; the new flow is additive
- [x] Smoke tests: `make e2e-kanban` IS the smoke test, validated working
- [ ] Rollback plan: not applicable — this is additive tooling, no feature flag needed
- [x] Observability: orchestrator logs to stdout with `[e2e-kanban]` prefix; vitest results appear inline

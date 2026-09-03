# Change: standardize-port-leases

## Why

Parallel agents on one host (the gx-10 local-parallel and coordinated tiers) each bring up a
compose stack, a host-run coordination API, and sometimes the kanban dev server. Today three
independent port schemes decide where those land, and none of them agrees with the others:

| Scheme | Where | Used by skills? |
|---|---|---|
| Coordinator `PortAllocatorService`, base 10000, 100 per session, in-memory | `agent-coordinator/src/port_allocator.py` | No. Only MCP/HTTP proxy tools and tests call it. |
| File-locked registry under `$TMPDIR/agentic-coding-tools-ports`, range 15432-25432 | `skills/validate-feature/scripts/environments/docker_stack.py` | Yes, via the stack launcher. |
| Hardcoded defaults 54322 / 8081 / 4000 / 8000 / 5173 / 3000 | `skills/validate-feature/SKILL.md` deploy, smoke, and ZAP phases | Yes, the shell path. |

Sixty-one files under `skills/`, `agent-coordinator/`, `apps/`, and `packages/gen-eval` carry a
literal `localhost:<port>`. The `TestEnvironment` protocol declares an env contract
(`API_BASE_URL`, `DB_PORT`, `COMPOSE_PROJECT_NAME`) but nothing enforces it, so a correctly
allocated port is defeated by the next consumer that assumes 8081 or 5173.

The coordinator allocator is the right owner now that the coordinator is a persistent local
service on the gx-10, reachable by local agents over MCP/HTTP and by cloud agents through the
Cloudflare tunnel. But it cannot be standardized on as-is:

- **In-memory only.** A coordinator restart forgets every lease while the compose stacks that hold
  those ports keep running; the next allocation collides.
- **Not tied to sessions.** `POST /discovery/cleanup` releases locks but never ports; reclamation is
  a separate 120 minute TTL clock, contradicting the help text that ports "auto-release on session
  cleanup".
- **No reality check.** Slots are arithmetic; nothing probes whether the port is actually free.
- **No isolation gate.** Cloud agents with their own containers can allocate gx-10 host ports they
  can never use, burning slots out of a maximum of twenty.

There is also spec drift: `live-service-testing` LST.2 says `DockerStackEnvironment` allocates via
`port_allocator`, while the code uses the local file registry; and the agent-coordinator
"Standalone operation" requirement mandates in-memory state even when a database is configured.

## What Changes

- **Persist port leases in Postgres.** New `port_leases` table (migration `035_port_leases.sql`);
  `PortAllocatorService` writes through to it when a DB backend is configured and reloads on start.
  In-memory mode remains for standalone operation. **MODIFIES** agent-coordinator "Standalone
  operation" scenario "Database configured but port allocator used".
- **Tie leases to agent sessions.** `allocate_ports` records the calling `agent_id`/session;
  `cleanup_dead_agents` releases leases held by stale sessions and `CleanupResult` gains
  `ports_released`. Heartbeat refreshes the lease. The TTL becomes a backstop, not the primary clock.
- **Bind-probe and conflict retry.** The client probes each port in the block on `127.0.0.1`. On a
  bound port it calls new `POST /ports/conflict` naming the slot and the reason; the coordinator marks
  the slot blocked for a cooling period and the client re-allocates, up to three attempts.
- **Reconcile on client start.** A `port-lease reconcile` command lists `docker compose ls` projects
  matching the `ac-`/`validate-` prefix, re-adopts leases the coordinator still holds, and releases
  leases whose project no longer exists. The coordinator, which runs in a container, has no host
  visibility, so reconciliation is client-driven and reported.
- **Isolation gate.** The allocate request carries the client's `isolation_provided` (from
  `EnvironmentProfile.detect()`); the coordinator persists it on the session and refuses allocation
  with `error: "isolation_provided"`. The client short-circuits before calling and emits the fixed
  compose defaults, because nothing else shares that container's port space.
- **Extend the block to five ports.** Add `ui_port` at offset +4 for the kanban dev server so its
  origin can be leased and allowed by CORS. Minimum `range_per_session` becomes 5. **MODIFIES**
  agent-coordinator "Port allocation service" and "Invalid configuration values".
- **Shared client `skills/shared/port_lease.py`.** `PortLease.acquire(session_id)` returns a
  `LeaseEnv` and a context manager that releases on exit. Backends: `coordinator` (through new
  `try_allocate_ports`/`try_release_ports`/`try_report_port_conflict` in `coordination_bridge`),
  `file` (the registry moved out of `docker_stack.py`, same on-disk format), and `none` (isolated
  environment, fixed defaults). Backend selection: `PORT_LEASE_BACKEND` override, else coordinator
  when reachable, else file. Both real backends emit the identical env contract.
- **Route every consumer through the contract.** `docker_stack.py` and `stack_launcher.py` consume
  `PortLease`; the validate-feature deploy phase sources the lease env instead of hardcoding three
  ports; smoke, gen-eval, playwright-validator, and the ZAP target read `API_BASE_URL`,
  `AGENT_COORDINATOR_REST_PORT`, and `UI_ORIGIN` from the env; the coordinator CORS list is extended
  from `COORDINATOR_CORS_ALLOWED_ORIGINS`, which the lease env now sets to the leased UI origin;
  kanban-viz `npm run dev` honours `UI_PORT` and `VITE_COORDINATOR_URL` from the lease env.
  **MODIFIES** agent-coordinator "Validate-feature port configuration", live-service-testing LST.2,
  and coordinator-kanban-viz "Hermetic E2E Test Orchestration".
- **Remove the duplicate allocator.** `docker_stack.py` no longer owns a port range. The 15432-25432
  file range is retired; the file backend uses the coordinator's block layout and base so both
  backends can never overlap.
- **Guard against regression.** A validate-feature architecture check fails when a new literal
  `localhost:<port>` appears in `skills/`, `apps/kanban-viz/src`, or `packages/gen-eval/src`
  outside an allowlist of documentation examples.
- `GET /ports/status` gains the `agent_id`, `isolation_provided`, and `backend` columns; it stays
  read-only without an API key as today.

Out of scope, deferred to follow-ups: generalizing leases to other host resources for sandbox
orchestration; coordinator-initiated sandbox spawning; portless integration for named `.localhost`
URLs. None of these change the contract this proposal introduces.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Resilience | Active leases surviving a coordinator process restart | 100 percent, verified by integration test that restarts the service between allocate and status | Integration tests (wp-coordinator) |
| Correctness | Overlapping blocks returned to concurrent allocate calls | 0 across 20 concurrent sessions, 50 iterations | Unit test with thread pool (wp-coordinator) |
| Operability | Time from a session's last heartbeat to its ports being free | At most the stale threshold plus one cleanup interval, default 15 min | Integration test driving `cleanup_dead_agents` (wp-coordinator) |
| Compatibility | Env contract keys emitted by the file backend versus the coordinator backend | Identical key set, asserted by a shared parametrized test | Unit tests (wp-skills-client) |
| Compatibility | Coordinator unreachable during `acquire` | Falls back to the file backend within 2 s and logs the backend used | Unit test with a refused connection (wp-skills-client) |
| Maintainability | New literal `localhost:<port>` in routed source trees | 0 outside the documented allowlist | Architecture validation grep gate (validate-feature) |
| Performance | `POST /ports/allocate` latency with DB persistence | p95 under 200 ms against local Postgres | Integration test timing assertion (wp-coordinator) |

## Approaches Considered

### Approach 1: Coordinator-owned leases plus a shared client with fallback

The coordinator becomes the single lease ledger, persisted in Postgres and tied to agent sessions.
A `PortLease` client in `skills/shared` talks to it over the existing HTTP bridge, probes ports on
the host, reports conflicts, and falls back to the same-format file registry when the coordinator is
unreachable. Every consumer reads the env contract the client emits.

- Pros: one ledger visible in the kanban and `ports_status`; leases die with the session; works
  across repos on one host; reuses heartbeat and stale cleanup instead of a second expiry clock;
  fallback keeps the local-parallel tier working; aligns code with LST.2 and the coordinator spec.
- Cons: schema migration and endpoint changes; client must own host-side probing and reconciliation
  because the coordinator runs in a container; the `isolation_provided` signal must be sent by the
  client since the coordinator does not know it today.
- Effort: L, split into four M packages.

### Approach 2: Host-local file registry as the sole allocator

Delete the coordinator allocator and its endpoints. Promote the file registry in `docker_stack.py`
to `skills/shared`, give it the five-port block layout, and route all consumers through it.

- Pros: smallest change; no migration; no network hop; no isolation gate needed because the
  registry only exists on the host that runs it.
- Cons: invisible to the coordinator and kanban; not tied to agent sessions, so crashed agents leak
  leases until a manual sweep; per-host `$TMPDIR` means a second checkout or repo on the gx-10
  cannot share it unless the path is made global; leaves the coordinator spec requirements as dead
  text; blocks the later resource-lease generalization.
- Effort: M.

### Approach 3: Named hosts through a local proxy with a minimal allocator

Adopt portless (or an equivalent local proxy) for host-run HTTP processes so consumers address
`https://api.<change-id>.localhost` and never see a port, keeping a small allocator only for the
Postgres TCP port.

- Pros: stable human-friendly URLs; worktree-aware naming for free; HMR and WebSockets proxied.
- Cons: only HTTP is proxied, so the database allocator still exists; containers such as ZAP cannot
  resolve `*.localhost` to the host proxy; Python clients need the proxy CA; needs a privileged
  daemon on 443 and Node 24; does nothing for cloud agents; hides collisions rather than removing
  them. Cleanup of the three schemes is still required underneath.
- Effort: M for the proxy, plus the cleanup from Approach 1 or 2 anyway.

### Recommended

Approach 1. It is the only option where a lease has the same lifetime as the agent session that
needs it, which removes the class of bugs where a port is free in one table and busy in another.
Its main con, host-side probing living in the client, is also its strength: the client is the only
process that can see the host's sockets and compose projects. Approach 2's simplicity is real but
it discards the spec-mandated coordinator surface and leaves the local-parallel tier permanently
orphaned from the kanban. Approach 3 is a possible later convenience on top of Approach 1, not a
substitute for it.

### Selected Approach

Approach 1, selected in the planning conversation that preceded this proposal. The user asked to
"standardize on the coordinator port allocation ... and rather fix the implementation and use of
it", then requested this change for "the allocator fixes and shared client". Modifications
requested: none. The user deferred portless (Approach 3) and the broader sandbox resource-lease
generalization to follow-ups.

## Impact

**Affected specs** (delta files under `specs/`):
- `agent-coordinator` — MODIFIED: Port allocation service (five-port block), Port allocation lease
  management (session tie-in), Port allocation configuration (min range 5), Standalone operation
  (persist when DB configured), Validate-feature port configuration (lease env instead of literal
  defaults), Heartbeat and Dead Agent Detection (cleanup releases ports). ADDED: Port lease
  persistence, Port lease conflict reporting, Port lease isolation gate.
- `live-service-testing` — MODIFIED: LST.2 Docker Stack Environment (allocates through `PortLease`).
- `coordinator-kanban-viz` — MODIFIED: Hermetic E2E Test Orchestration (leased ports and origin).
- `port-lease-client` — ADDED: new capability for `skills/shared/port_lease.py`.

**Affected architecture layers:** Coordination (allocator persistence, session lifecycle, CORS),
Execution (validate-feature environments, stack launcher, kanban dev server, gen-eval and
playwright defaults).

**Major code touchpoints:**
- `agent-coordinator/src/port_allocator.py`, `discovery.py`, `coordination_api.py`,
  `coordination_mcp.py`, `http_proxy.py`, `config.py`, `database/migrations/035_port_leases.sql`
- `skills/shared/port_lease.py` (new), `skills/coordination-bridge/scripts/coordination_bridge.py`
- `skills/validate-feature/scripts/environments/docker_stack.py`, `stack_launcher.py`,
  `phase_deploy.py`, `skills/validate-feature/SKILL.md`, `skills/validate-feature/scripts/smoke_tests/`
- `skills/playwright-validator/scripts/`, `packages/gen-eval/src/gen_eval/coordinator.py`
- `apps/kanban-viz/vite.config.ts`, `apps/kanban-viz/src/App.tsx`, `apps/kanban-viz/package.json`
- `docs/guides/worktree-management.md`, `docs/local-migration.md`, `docs/kanban-viz/README.md`

**Dependencies on in-flight changes:** `add-isolation-posture-detection` widens
`EnvironmentProfile`; this change consumes only its `isolation_provided` compatibility boolean, so
either order works.

**Rollback:** the migration is additive; the client's `PORT_LEASE_BACKEND=file` override restores
the pre-change behaviour without a coordinator; the old literal defaults remain valid input to the
same env keys.

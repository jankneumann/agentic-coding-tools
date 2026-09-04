# Design: standardize-port-leases

## Context

The coordinator is now a persistent local service on the gx-10, started from the compose stack in
`agent-coordinator/`, reachable by local agents over MCP/HTTP and by cloud agents through the
Cloudflare tunnel at `coord.rotkohl.ai`. Tier selection in `implement-feature` and
`validate-feature` therefore lands on `coordinated` almost always; `local-parallel` is the
degraded path when the coordinator is down.

Port allocation has not caught up. `PortAllocatorService` is in-memory
(`agent-coordinator/src/port_allocator.py:67`), has no session link, and is not called by any
skill. `DockerStackEnvironment` carries its own file registry
(`skills/validate-feature/scripts/environments/docker_stack.py:30-199`), and the validate-feature
shell path hardcodes a third set of ports. Consumers assume literal ports in 61 files.

The coordinator runs inside a container. It cannot bind-probe host ports or list host compose
projects. Any design that needs host truth must put that logic in the client.

`isolation_provided` is computed client-side by `skills/shared/environment_profile.py`. The
coordinator layer of that detection reads a field the coordinator never sets, so today the
coordinator does not know whether a session is isolated.

## Goals / Non-Goals

Goals:
- One lease ledger, owned by the coordinator, durable across restarts, released with the session.
- One client, `skills/shared/port_lease.py`, that every skill and app consumes, with a fallback that
  emits an identical env contract when the coordinator is down.
- No literal ports in routed consumers; a gate that keeps it that way.
- Spec, code, and docs agree.

Non-goals:
- Generalizing leases to GPUs, worktree paths, or sandbox handles (follow-up: resource leases).
- Coordinator-initiated sandbox creation, especially over the tunnel path.
- Named `.localhost` URLs via a local proxy (portless); may layer on later.
- Changing lock, work-queue, or archetype behaviour.

## Decisions

### D1. Coordinator is the lease ledger; the client is the host's eyes

The coordinator stores and arbitrates leases. The client performs bind probes, compose-project
listing, and reconciliation reports, because it is the only party on the host. This keeps the
coordinator free of host Docker socket access, consistent with the tunnel security posture in
`docs/local-migration.md`, and with the `add-dispatch-sandbox-enforcement` fence that
`docker_manager.py` must not become a sandbox manager. Reconciliation lives in `port_lease.py`, not
in `docker_manager.py`.

### D2. Persist through the existing DB client; in-memory stays the standalone mode

`port_leases` follows the `file_locks` shape (`database/migrations/001_core_schema.sql:8-21`):
session id primary key, agent id, slot index, five ports, project name, `isolation_provided`,
`allocated_at`, `expires_at`, `blocked_until`. `PortAllocatorService` keeps its in-memory dict as
the hot path and writes through when `get_db()` is configured. On startup it loads unexpired rows
and prunes expired ones. Write failure aborts the allocation. Blocked slots are rows with a null
session and a non-null `blocked_until`. The migration is `036_port_leases.sql`.

### D3. Leases belong to sessions; heartbeat refreshes, cleanup releases

`allocate_ports` records the principal's `agent_id`. `DiscoveryService.cleanup_dead_agents`
releases leases for the agents it disconnects and reports `ports_released`. `heartbeat` extends
`expires_at`. The TTL remains only as a backstop for sessions that never heartbeat. Stale is
defined once, by `cleanup_dead_agents`' threshold; the lease code does not introduce a second
staleness rule (noted against `add-map-state-ir`, which derives `stale` from the same heartbeat).

### D4. Five-port block, `ui_port` at offset +4

The kanban dev server needs a leased origin so CORS can be derived rather than hardcoded. Adding
one offset keeps the arithmetic and raises the minimum `range_per_session` to 5. The default
spacing of 100 is untouched.

### D5. Isolation gate is client-reported and downgrade-only

The client sends `isolation_provided` from `EnvironmentProfile.detect()`. The coordinator stores
it on the session and refuses allocation when true. Once stored as true it cannot be lowered by a
later request, mirroring the `clamp-trust-by-isolation-posture` rule that self-reports may only
tighten. A worktree is not isolation for ports; when `add-isolation-posture-detection` lands, the
client reads its filesystem-isolation dimension through the `isolation_provided` compatibility
property, so this change has no dependency on that change's internals.

### D6. Conflict reports block a slot for a cooling period

A bind-probe failure is evidence that something outside the ledger holds the port. The client
reports it; the coordinator blocks that slot for `conflict_block_minutes` (default 30) and the
client re-acquires, at most three times. Blocking rather than skipping once prevents two clients
from alternately discovering the same foreign listener.

### D7. File backend is a fallback in a disjoint slot range

The registry moves out of `docker_stack.py` into the client as `FileBackend`, keeps its fcntl
lock and atomic replace, and adopts the coordinator's slot layout, base, spacing, and project-name
format read from `PORT_ALLOC_*`. The old 15432-25432 range is retired.

Identical arithmetic makes the two backends *agree* when a host flips between them sequentially,
but it does not make them safe **concurrently**, which is the case the fallback exists for. During
a coordinator outage the file registry has no visibility of leases already granted from the
ledger, so the same arithmetic over the same config selects the very same slots — the fallback
would hand out blocks that are already held.

The bind probe does not close this gap. Probing does not *reserve*: two clients can each probe a
free port successfully, and only then does either compose stack bind. The probe detects foreign
listeners, not a peer mid-allocation.

So the slot space is partitioned. `PORT_ALLOC_SLOTS` is split into a coordinator range
`[0, PORT_ALLOC_FILE_SLOT_BASE)` and a file range `[PORT_ALLOC_FILE_SLOT_BASE, PORT_ALLOC_SLOTS)`,
with `PORT_ALLOC_FILE_SLOT_BASE` defaulting to 75% of the total. Each backend allocates only
within its own range, so a lease granted by one can never collide with a lease granted by the
other, whatever the ordering and whether or not the coordinator is reachable. The cost is a
smaller pool per backend, which is the right trade: the fallback is for outages, not for steady
state, and an unusable-but-disjoint pool beats a larger pool that silently double-allocates.

Partitioning is chosen over having the file backend reconcile against the ledger because
reconciliation is precisely what is unavailable when the fallback engages. A rule that only holds
while the coordinator is reachable is not a fallback rule.

### D8. Backend order is override, isolation, coordinator, file

`PORT_LEASE_BACKEND` wins for operators and tests. Isolation short-circuits to `none` with fixed
compose defaults, because nothing else shares that container. Coordinator is tried with a 2 s
health check, then file. The chosen backend is emitted so reports and the kanban can show it.

### D9. Consumers read the contract; nothing else

`docker_stack.py`, `stack_launcher.py`, and `phase_deploy.py` take their env from `PortLease`.
The validate-feature deploy phase evaluates `port-lease acquire --format shell` once and exports
the result; the three literal defaults go away. Smoke tests, gen-eval, playwright-validator, and
the ZAP target read `API_BASE_URL`, `UI_ORIGIN`, or `AGENT_COORDINATOR_REST_PORT` with no literal
fallback. The coordinator extends its CORS list from `COORDINATOR_CORS_ALLOWED_ORIGINS`, which
already exists at `coordination_api.py:767`; the lease env sets it to the leased `UI_ORIGIN`.
kanban-viz reads `UI_PORT` in `vite.config.ts` with `strictPort`.

Edits to `skills/validate-feature/SKILL.md` are confined to the env-default lines in the deploy,
smoke, and security phases and one line in Teardown. The gen-eval invocation block (phase 4b) is
not restructured, because `extract-gen-eval-package` and
`factory-missions-architecture-alignment` are in-flight writers of that block.

### D10. Dispatch env allowlist carries the contract keys

`add-sandboxed-harness-execution` makes child env construction allowlist-based. The contract keys
in `contracts/schemas/port-lease-env.schema.json` are the allowlist source of truth; the
integration package adds them to `skills/shared/dispatch_env.py` if that module exists at merge
time, and otherwise records the obligation in `deferred-tasks.md`.

### D11. Mirrors are regenerated, not hand-edited

`skills/shared/port_lease.py` and the changed skill files are mirrored with `install.sh`, per the
`gate-drift-with-mirrors-hooks-and-blocking-ci` gate. Runtime copies under `.claude/skills` and
`.agents/skills` are never edited directly.

### Fitness Functions

| NFR (from proposal.md) | Verifying check | Status |
|------------------------|-----------------|--------|
| Resilience: 100 percent of active leases survive a restart | `agent-coordinator/tests/integration/test_port_leases_persist.py` allocates, recreates the service against the same DB, asserts `status()` | new |
| Correctness: 0 overlapping blocks across 20 concurrent sessions x 50 iterations | `agent-coordinator/tests/test_port_allocator.py::test_concurrent_allocations_disjoint` | new |
| Operability: ports free within stale threshold plus one cleanup interval | `agent-coordinator/tests/integration/test_cleanup_releases_ports.py` backdates `last_heartbeat`, runs `cleanup_dead_agents`, asserts `ports_released` | new |
| Compatibility: identical key set across backends | `skills/tests/shared/test_port_lease.py::test_env_contract_parity` parametrized over backends against the JSON schema | new |
| Compatibility: fallback within 2 s on refused connection | `skills/tests/shared/test_port_lease.py::test_coordinator_refused_falls_back` with a closed local port and a timing assertion | new |
| Maintainability: 0 new port literals outside allowlist | `skills/validate-feature/scripts/check_port_literals.py`, wired into the architecture phase | new |
| Performance: allocate p95 under 200 ms with persistence | `agent-coordinator/tests/integration/test_port_leases_persist.py::test_allocate_latency` over 50 calls | new |

## Alternatives Considered

- **Host-local file registry as the only allocator.** Rejected: invisible to the coordinator and
  kanban, no session lifetime, leaves spec text dead, blocks the resource-lease follow-up.
- **Coordinator reads the host Docker socket for reconciliation.** Rejected: widens the container's
  privileges and the tunnel-exposed surface; contradicts the `docker_manager.py` fence.
- **Coordinator infers isolation from `agents.yaml` `isolation` per agent type.** Rejected: that
  field describes the dispatch policy, not the environment a given session actually runs in; a
  `worktree` agent type can still be launched inside a cloud container.
- **Keep the 120 min TTL as the primary clock.** Rejected: two clocks for one resource is how
  ports end up free in one table and busy in another.
- **Named hosts via portless.** Deferred: only HTTP is proxied, containers cannot resolve
  `*.localhost` to the host proxy, and it needs a privileged daemon; it can sit on top later.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| Three in-flight writers of `validate-feature/SKILL.md` phase 4b | D9 confines edits to env-default lines; integration package rebases last and re-runs the gate |
| `isolation_provided` semantics change under `add-isolation-posture-detection` | D5 reads only the compatibility boolean; a follow-up task switches to the filesystem dimension once that change is merged |
| Allowlist-based dispatch env drops the lease keys | D10; contract schema is the allowlist source; integration checks `dispatch_env.py` presence |
| A blocked slot from a false-positive probe wastes a slot for 30 min | `conflict_block_minutes` is configurable; `ports_status` shows blocked slots with the reason |
| Coordinator DB write latency on allocate | Single-row insert; p95 fitness function guards it |
| File backend and coordinator both active on one host during a coordinator outage | Same arithmetic (D7) plus bind probe (D6) make an overlap fail loudly rather than silently |
| `GET /ports/status` stays unauthenticated and now shows agent ids | Read-only; agent ids are already visible on `/agents`; documented in the API contract |

## Migration Plan

1. Land `wp-contracts` and `wp-coordinator`: migration, persistence, session tie-in, new endpoints.
   Existing clients keep working; new fields are optional.
2. Land `wp-skills-client`: the client plus `docker_stack.py` and `stack_launcher.py` on it. The
   old registry format is not read; any stale `registry.json` under `$TMPDIR` is ignored.
3. Land `wp-consumers`: SKILL.md env routing, smoke and ZAP defaults, kanban dev port, gen-eval and
   playwright defaults, docs.
4. `wp-integration`: `install.sh` mirror, dispatch allowlist, regression gate, full test run, spec
   sync.

Rollback: the migration is additive and can stay. Setting `PORT_LEASE_BACKEND=file` restores
coordinator-free operation. Reverting the consumer commits restores literal defaults, which remain
valid values of the same env keys.

## Task Sizing Notes

The `and` splitting heuristic was run over `tasks.md`. Remaining matches are enumerations of
scenarios or fields inside a single outcome (for example "tests for X, Y, and Z" or "extend
`PortAllocation` and `PortAllocatorConfig`", which is one slot-arithmetic change across two
dataclasses). The two L-sized items, persistence (2.4) and the client module (3.3), are decomposed
into 2.4a-2.4c and 3.3a-3.3d and carry no checkbox of their own.

## MODIFIED Requirements

### Requirement: Port allocation service

The port allocator service SHALL assign conflict-free port blocks to sessions. Each block SHALL contain 5 ports at fixed offsets within the block: offset +0 for `db_port`, +1 for `rest_port`, +2 for `realtime_port`, +3 for `api_port`, +4 for `ui_port`. The configured `range_per_session` determines the spacing between blocks (default: 100), so the first session gets base..base+4, the second gets base+100..base+104, etc. The service SHALL operate in-memory when no database backend is configured and SHALL persist leases when one is configured (see "Port lease persistence").

#### Scenario: Successful port allocation
- **WHEN** an agent calls `allocate_ports` with a `session_id`
- **THEN** the service SHALL return a port assignment containing `db_port`, `rest_port`, `realtime_port`, `api_port`, and `ui_port` with no overlap with any active allocation
- **AND** the service SHALL return a `compose_project_name` unique to that session (format: `ac-<first 8 chars of session_id hash>`)
- **AND** the service SHALL return an `env_snippet` string in `export VAR=value` format, one variable per line, containing `AGENT_COORDINATOR_DB_PORT`, `AGENT_COORDINATOR_REST_PORT`, `AGENT_COORDINATOR_REALTIME_PORT`, `API_PORT`, `UI_PORT`, `COMPOSE_PROJECT_NAME`, `SUPABASE_URL`, `API_BASE_URL`, `UI_ORIGIN`, and `COORDINATOR_CORS_ALLOWED_ORIGINS`
- **AND** the allocation SHALL record the calling `agent_id` taken from the authenticated principal

#### Scenario: Duplicate session allocation
- **WHEN** an agent calls `allocate_ports` with a `session_id` that already has an active allocation
- **THEN** the service SHALL return the existing allocation unchanged
- **AND** the lease TTL SHALL be refreshed

#### Scenario: Port range exhaustion
- **WHEN** all available port blocks are allocated or blocked and a new allocation is requested
- **THEN** the service SHALL return `{success: false, error: "no_ports_available"}`
- **AND** no existing allocation SHALL be affected

### Requirement: Port allocation lease management

Port allocations SHALL be owned by the agent session that requested them. A session's heartbeat SHALL refresh its lease. The configurable TTL SHALL remain as a backstop for sessions that never heartbeat, and expired leases MUST be automatically reclaimed.

#### Scenario: Heartbeat refreshes lease
- **WHEN** an agent with an active port allocation calls `heartbeat()`
- **THEN** the allocation's `expires_at` SHALL be extended by the configured TTL
- **AND** the allocation SHALL remain unchanged otherwise

#### Scenario: Lease expires
- **WHEN** a port allocation's TTL elapses without a heartbeat or renewal
- **THEN** the port block SHALL be available for new allocations
- **AND** subsequent calls to `allocate_ports` with a new session MAY reuse the expired block's ports

#### Scenario: Explicit release
- **WHEN** an agent calls `release_ports` with a valid `session_id` **that its own authenticated `agent_id` owns**
- **THEN** the allocation SHALL be removed immediately from memory and from the persistent store when one is configured
- **AND** the ports SHALL be available for reuse

#### Scenario: Release of unknown session
- **WHEN** an agent calls `release_ports` with a `session_id` that has no active allocation
- **THEN** the service SHALL return success (idempotent)

#### Scenario: Release of another agent's lease is refused
- **WHEN** an agent calls `release_ports` with a `session_id` whose lease belongs to a different `agent_id`
- **THEN** the service SHALL NOT release the lease
- **AND** SHALL return `{success: true}` — the same idempotent response as for a session with no active lease

Returning a distinct `not_lease_owner` here would itself be the disclosure it was meant to prevent:
an unknown session already returns `success: true`, so any *other* response tells the caller the
session exists and belongs to someone else. Since `GET /ports/status` is unauthenticated and
publishes every `session_id`, that would let a caller confirm which sessions are live and owned.
The two rules cannot both hold, so the release path is uniformly idempotent from the caller's
point of view and the refusal is recorded server-side (audit) rather than signalled.

`not_lease_owner` remains the response for `POST /ports/conflict`, which is not idempotent and has
no "unknown session succeeds" case to collide with.

#### Scenario: Conflict report against another agent's lease is refused
- **WHEN** an agent calls `POST /ports/conflict` naming a `session_id` owned by a different `agent_id`
- **THEN** the service SHALL NOT release that lease and SHALL NOT block its slot
- **AND** SHALL return `{success: false, error: "not_lease_owner"}`

### Requirement: Lease operations are scoped to the owning agent

Every mutating port-lease operation SHALL verify that the authenticated caller's `agent_id`
matches the `agent_id` recorded on the lease before acting, and SHALL refuse otherwise.

This is not defence in depth, it is the only control. `GET /ports/status` is deliberately
unauthenticated and returns each active lease's `session_id` and `agent_id`, so a `session_id` is
public knowledge by design. Without an ownership check, any holder of any valid API key — the
coordinator is reachable over the Cloudflare tunnel — can enumerate leases and then release a
peer's lease mid-run, or force its slot into a `conflict_block_minutes` cooling period. The
result is an agent whose stack is still bound to ports the coordinator has handed to someone
else: the exact collision this capability exists to prevent, reachable on purpose rather than by
accident.

The repository already establishes this pattern for the sibling resource: `release_lock` in
`001_core_schema.sql` deletes `WHERE file_path = p_file_path AND locked_by = p_agent_id`. Port
leases SHALL carry the equivalent `AND agent_id = p_agent_id` guard.

#### Scenario: Ownership is enforced in the data layer, not only the handler
- **WHEN** a lease release is executed against the persistent store
- **THEN** the delete SHALL be predicated on both `session_id` and the caller's `agent_id`
- **AND** a mismatched caller SHALL delete zero rows

#### Scenario: Unowned leases are releasable only by cleanup
- **WHEN** a lease has a NULL `agent_id` because it was created before the owning agent registered
- **THEN** no authenticated caller SHALL release it through `release_ports`
- **AND** it SHALL be reclaimed only by TTL expiry or stale-session cleanup

### Requirement: Port allocation configuration

The port allocator SHALL read configuration from environment variables with sensible defaults.

#### Scenario: Default configuration
- **WHEN** no port allocator environment variables are set
- **THEN** `base_port` SHALL be 10000, `range_per_session` SHALL be 100, `ttl_minutes` SHALL be 120, `max_sessions` SHALL be 20, and `conflict_block_minutes` SHALL be 30

#### Scenario: Custom configuration
- **WHEN** `PORT_ALLOC_BASE`, `PORT_ALLOC_RANGE`, `PORT_ALLOC_TTL_MINUTES`, `PORT_ALLOC_MAX_SESSIONS`, `PORT_ALLOC_CONFLICT_BLOCK_MINUTES`, or `PORT_ALLOC_FILE_SLOT_BASE` are set
- **THEN** the allocator SHALL use those values

#### Scenario: Backend slot ranges are disjoint
- **WHEN** the allocator starts with `PORT_ALLOC_FILE_SLOT_BASE` unset
- **THEN** it SHALL default to 75% of `max_sessions`, rounded down
- **AND** the coordinator allocator SHALL only issue slots in `[0, PORT_ALLOC_FILE_SLOT_BASE)`
- **AND** the file backend SHALL only issue slots in `[PORT_ALLOC_FILE_SLOT_BASE, max_sessions)`

#### Scenario: File slot base out of range
- **WHEN** `PORT_ALLOC_FILE_SLOT_BASE` is 0, negative, or not less than `max_sessions`
- **THEN** the allocator SHALL refuse to start with a configuration error naming the variable
- **AND** it SHALL NOT fall back to a shared range, because a shared range silently reintroduces double-allocation during a coordinator outage

#### Scenario: Invalid configuration values
- **WHEN** `base_port` is below 1024 or `range_per_session` is below 5
- **THEN** the service SHALL raise a configuration error at startup
- **AND** no allocation SHALL be served

### Requirement: Standalone operation

The port allocator service MUST function without any database backend (ParadeDB, Supabase, or otherwise) or other coordination service being configured. When a database backend is configured, the allocator SHALL use it as the durable lease store.

#### Scenario: No database configured
- **WHEN** neither `POSTGRES_DSN` nor `SUPABASE_URL` is set and `DB_BACKEND` is not configured
- **THEN** `allocate_ports` SHALL return a valid five-port block that overlaps no live allocation, and `release_ports` SHALL return success, both using only in-memory state with no database connection attempted
- **AND** no database connection SHALL be attempted by the port allocator
- **AND** `ports_status` SHALL report `backend: "memory"`

#### Scenario: Database configured and port allocator used
- **WHEN** the full agent-coordinator is running with a database
- **THEN** every allocation, refresh, block, and release SHALL be written through to the `port_leases` table
- **AND** `ports_status` SHALL report `backend: "postgres"`
- **AND** other services (locks, memory, etc.) SHALL continue using the database as before

### Requirement: Validate-feature port configuration

The validate-feature skill SHALL obtain every port and origin it uses from the port-lease env contract (see the `port-lease-client` capability) and SHALL NOT carry literal port defaults in its deploy, smoke, security, or behavioral phases.

#### Scenario: Deploy phase sources the lease env
- **WHEN** the validate-feature deploy phase starts services
- **THEN** it MUST first evaluate `port-lease acquire --session-id "$VALIDATION_SESSION_ID" --format shell`
- **AND** the compose invocation MUST receive `AGENT_COORDINATOR_DB_PORT`, `AGENT_COORDINATOR_REST_PORT`, `AGENT_COORDINATOR_REALTIME_PORT`, and `COMPOSE_PROJECT_NAME` from that env
- **AND** the health check URL MUST be built from `${API_PORT}` (equivalently `API_BASE_URL`) with no literal fallback, because in this flow the coordination API is started **on the host** by `phase_deploy.py` and binds `API_PORT` (block offset +3); compose here provides only PostgreSQL, so `AGENT_COORDINATOR_REST_PORT` (offset +1) has no listener and polling it would fail as a connection error indistinguishable from a service that failed to start

#### Scenario: Downstream phases read the contract
- **WHEN** the smoke, gen-eval, playwright, or security phases need a service address
- **THEN** they MUST read `API_BASE_URL`, `UI_ORIGIN`, or `AGENT_COORDINATOR_REST_PORT` from the env
- **AND** the ZAP target MUST be `API_BASE_URL` (`http://localhost:${API_PORT}`) with no literal fallback, matching the host-run API the deploy phase actually started rather than the compose-published REST port

#### Scenario: Teardown releases the lease
- **WHEN** the validate-feature run reaches Teardown, on success or failure
- **THEN** it MUST call `port-lease release --session-id "$VALIDATION_SESSION_ID"`
- **AND** a failed release MUST be logged as a warning without changing the validation result

### Requirement: Heartbeat and Dead Agent Detection

The system SHALL detect unresponsive agents and reclaim their resources through heartbeat monitoring.

- Agents SHALL periodically update a heartbeat timestamp
- The system SHALL provide a cleanup function for agents whose heartbeat is stale
- Stale agent cleanup SHALL release held file locks
- Stale agent cleanup SHALL release port leases held by the **stale sessions**, identified by
  `session_id` — never every lease belonging to the stale session's `agent_id`. A single
  `agent_id` routinely holds several concurrent sessions (a `validate-feature` sweep alongside
  an interactive stack), and releasing by agent identity would reclaim a live session's block
  while its stack is still bound to it, contradicting the "Active agent not affected by cleanup"
  scenario below and producing the port collision this capability exists to prevent
- Stale agent cleanup SHALL mark agent status as disconnected
- The default stale threshold SHALL be 15 minutes to accommodate long-running operations

#### Scenario: Agent sends heartbeat
- **WHEN** agent calls `heartbeat()`
- **THEN** system updates the agent's `last_heartbeat` timestamp
- **AND** returns `{success: true, session_id: uuid}`

#### Scenario: Dead agent detection and cleanup
- **WHEN** cleanup function runs with configurable stale threshold (default 15 minutes)
- **THEN** agents with `last_heartbeat` older than threshold are marked as disconnected
- **AND** all file locks held by those agents are released
- **AND** the port leases held by those agents' **stale sessions** are released
- **AND** system returns the count of cleaned-up agents, released locks, and released port leases as `agents_cleaned`, `locks_released`, and `ports_released`

#### Scenario: Active agent not affected by cleanup
- **WHEN** cleanup function runs
- **AND** agent's `last_heartbeat` is within the stale threshold
- **THEN** agent's status, locks, and port leases are not affected

#### Scenario: One agent with both a stale and an active session
- **WHEN** cleanup function runs
- **AND** a single `agent_id` holds a lease from a session whose heartbeat is stale
- **AND** the same `agent_id` holds a second lease from a session heartbeating within the threshold
- **THEN** only the stale session's lease SHALL be released
- **AND** the active session's lease SHALL remain, with its slot NOT returned to the allocatable pool
- **AND** a subsequent allocation SHALL NOT be granted the active session's block

#### Scenario: Heartbeat fails due to database error
- **WHEN** agent calls `heartbeat()` and the coordination database is unreachable
- **THEN** system returns `{success: false, error: "database_unavailable"}`
- **AND** the agent continues operating without updated heartbeat

## ADDED Requirements

### Requirement: Port lease persistence

When a database backend is configured, the port allocator SHALL persist leases in a `port_leases` table so that leases survive a coordinator process restart.

#### Scenario: Leases reload on startup
- **WHEN** the coordinator starts with a database configured and `port_leases` contains unexpired rows
- **THEN** the allocator SHALL load those rows into memory before serving the first request
- **AND** a subsequent `allocate_ports` for a new session SHALL NOT return a block held by a reloaded lease

#### Scenario: Expired rows are pruned on startup
- **WHEN** the coordinator starts and `port_leases` contains rows whose `expires_at` is in the past
- **THEN** those rows SHALL be deleted
- **AND** their blocks SHALL be available for allocation

#### Scenario: Persistence write fails
- **WHEN** the database write for an allocation fails
- **THEN** the allocation SHALL NOT be returned to the caller
- **AND** the service SHALL return `{success: false, error: "database_unavailable"}`
- **AND** no in-memory slot SHALL remain reserved for that session

#### Scenario: Slot selection is atomic across worker processes
- **WHEN** two API worker processes concurrently select the same free slot for different sessions
- **THEN** at most one INSERT SHALL succeed, enforced by the `port_leases` primary key on `slot`
- **AND** the loser SHALL retry against the next free slot rather than failing the request
- **AND** it SHALL NOT surface `database_unavailable`, which would misreport a resolvable
  contention as a database outage
- **AND** the caller SHALL receive a valid non-overlapping block while free slots remain

The in-memory free-slot map is per-process and its mutex is process-local, so it does not
serialize anything when `API_WORKERS` is greater than 1 — a supported and used configuration.
The primary key is the only real arbiter, which makes conflict a normal, expected outcome of
allocation rather than an error: it must be retried, not reported.

#### Scenario: Concurrency is verified across processes, not only threads
- **WHEN** the allocator's concurrency test suite runs
- **THEN** it SHALL exercise allocation from **separate processes**, not only a thread pool within one
- **AND** SHALL assert that no two sessions ever receive overlapping blocks

A thread-pool test passes trivially under the process-local mutex and therefore cannot observe
the one topology where the race exists.

#### Scenario: Persistence delete fails during release
- **WHEN** a session releases its allocation and the database delete fails
- **THEN** the in-memory slot SHALL NOT be freed
- **AND** the service SHALL return `{success: false, error: "database_unavailable"}`
- **AND** the lease SHALL remain valid until its TTL expires

The in-memory and persisted views must fail in the same direction. Freeing the slot in memory
while the row survives would reallocate a block that reappears as held on the next restart's
reload — two sessions believing they own it, which is the collision this capability exists to
prevent. Keeping the lease is the safe direction: the TTL backstop reclaims it, so the worst case
is a slot idle for at most `ttl_minutes`, not a double-allocated one.

### Requirement: Port lease conflict reporting

The allocator SHALL accept conflict reports from clients that observed a port in a leased block already bound by an unrelated process, and SHALL block that slot for a cooling period.

#### Scenario: Client reports a bound port
- **WHEN** a client calls `POST /ports/conflict` with `session_id`, the conflicting `port`, and a `reason`
- **THEN** the service SHALL release the session's current allocation
- **AND** SHALL mark the block containing `port` as blocked until now plus `conflict_block_minutes`
- **AND** SHALL return `{success: true, blocked_until: <timestamp>}`

#### Scenario: Blocked slot is skipped
- **WHEN** a slot is blocked and `allocate_ports` is called
- **THEN** the allocator SHALL skip the blocked slot
- **AND** SHALL return the next free slot or `no_ports_available`

#### Scenario: Cooling period elapses and the slot returns to the pool
- **WHEN** a slot's `blocked_until` is in the past and `allocate_ports` is called
- **THEN** the allocator SHALL treat the slot as allocatable
- **AND** SHALL be able to return it
- **AND** the block SHALL NOT require operator action to be reclaimed

A blocking rule with no expiry path is a leak, not a cooling period: with `max_sessions` at 20 and
a 30-minute default, a handful of false-positive conflict reports would otherwise shrink the pool
permanently for the life of the process.

#### Scenario: Expired blocks are pruned on startup
- **WHEN** the coordinator starts and `port_leases` contains rows whose `blocked_until` is in the past
- **THEN** those rows SHALL be deleted alongside the rows pruned by `expires_at`
- **AND** their blocks SHALL be available for allocation

#### Scenario: Conflict report for unknown session
- **WHEN** `POST /ports/conflict` names a `session_id` with no active allocation
- **AND** the reported `port` falls in a slot that is currently **unleased**
- **THEN** the service SHALL block that slot until now plus `conflict_block_minutes`
- **AND** SHALL return `{success: true, blocked_until: <timestamp>}`

#### Scenario: Conflict report cannot block a slot leased to someone else
- **WHEN** `POST /ports/conflict` names a `session_id` with no active allocation
- **AND** the reported `port` falls in a slot leased to a different `agent_id`
- **THEN** the service SHALL NOT block that slot and SHALL NOT release that lease
- **AND** SHALL return `{success: false, error: "not_lease_owner"}`

Without this, the unknown-session path is a denial-of-service lever. Block layout is arithmetic
(10000, 10100, 10200, …) so every port is predictable without reading anything, and
`GET /ports/status` is unauthenticated anyway. A caller could otherwise walk the range reporting
fabricated conflicts against sessions it does not own, blocking every slot for
`conflict_block_minutes` and starving the pool — while each individual request looked like a
well-behaved client honestly reporting a bind failure.

Reporting a conflict on an unleased slot stays open, because that is the legitimate case: a
foreign process outside the ledger holds the port, and no lease exists to check ownership against.

### Requirement: Port lease isolation gate

The allocator SHALL refuse to lease host ports to sessions that already run in an environment with its own port namespace.

#### Scenario: Isolated session requests ports
- **WHEN** `allocate_ports` is called with `isolation_provided: true`
- **THEN** the service SHALL return `{success: false, error: "isolation_provided"}`

#### Scenario: A session that already holds a lease reports isolation
- **WHEN** a session holds a port lease and calls `allocate_ports` again with `isolation_provided: true`
- **THEN** the isolation gate SHALL be evaluated BEFORE the duplicate-session short-circuit
- **AND** the service SHALL release that session's existing lease, returning its slot to the pool
- **AND** SHALL return `{success: false, error: "isolation_provided"}`
- **AND** the session SHALL NOT remain recorded as isolated while still holding host ports

Ordering matters here because the two rules point opposite ways: the duplicate-session rule
returns the existing allocation unchanged, while the isolation gate refuses to lease at all.
Evaluating the short-circuit first would hand back a live host-port block to a session that has
just declared it does not need one, leaving the slot held indefinitely by a stack that will never
bind it.
- **AND** no slot SHALL be consumed
- **AND** the session record SHALL store `isolation_provided: true`

#### Scenario: Self-reported isolation may only tighten
- **WHEN** a session previously reported `isolation_provided: true` and later calls `allocate_ports` with `isolation_provided: false`
- **THEN** the service SHALL keep the stored `true` and refuse the allocation
- **AND** SHALL log the downgrade attempt to the audit trail

#### Scenario: Legacy client omits the flag
- **WHEN** `allocate_ports` is called without `isolation_provided`
- **THEN** the service SHALL treat it as `false`
- **AND** SHALL allocate normally

### Requirement: Port lease reconciliation

The allocator SHALL accept a reconciliation report from a host-side client listing the compose projects currently running on that host, because the coordinator itself has no host visibility.

A reconciliation report SHALL only ever affect leases allocated **from the reporting client's own
host**. Leases SHALL record the `host_id` of the session that acquired them, `POST /ports/reconcile`
SHALL carry that same `host_id`, and the service SHALL restrict both release and blocking to
leases whose recorded `host_id` matches.

Without that scoping, one client's report is authoritative over every lease in the system. The
coordinator serves both local agents and cloud agents over the tunnel; a cloud agent has no
access to the local host's filesystem, so its `docker compose ls` is necessarily empty. Its
reconcile call would report zero running projects and, once each lease aged past
`conflict_block_minutes`, the coordinator would release every local lease on every other host —
a fleet-wide outage triggered by a routine call from a correctly-behaving client. The same lever
in a misbehaving one is a single-request denial of service against every agent.

#### Scenario: Orphaned lease is released
- **WHEN** a client calls `POST /ports/reconcile` with its `host_id` and the list of running `compose_project_name`s for its host
- **AND** an active lease **recorded against that same `host_id`** has a project absent from the list and is older than `conflict_block_minutes`
- **THEN** the service SHALL release that lease
- **AND** SHALL return the released session ids

#### Scenario: Reconcile never touches another host's leases
- **WHEN** a client calls `POST /ports/reconcile` reporting zero running projects
- **AND** active leases exist that were allocated from a different `host_id`
- **THEN** those leases SHALL NOT be released, blocked, or otherwise modified
- **AND** the response SHALL report only sessions from the reporting host
- **AND** this SHALL hold regardless of how long those other-host leases have existed

#### Scenario: Running project without a lease
- **WHEN** the reconciliation list contains a project whose name matches an allocator-generated name but no lease exists
- **THEN** the service SHALL block the slot implied by the reported ports until `conflict_block_minutes` elapse
- **AND** SHALL return that project under `adopted_blocks`

#### Scenario: Reconciliation from an isolated session
- **WHEN** `POST /ports/reconcile` is called by a session with `isolation_provided: true`
- **THEN** the service SHALL return `{success: false, error: "isolation_provided"}`
- **AND** no lease SHALL change

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
- **WHEN** an agent calls `release_ports` with a valid `session_id`
- **THEN** the allocation SHALL be removed immediately from memory and from the persistent store when one is configured
- **AND** the ports SHALL be available for reuse

#### Scenario: Release of unknown session
- **WHEN** an agent calls `release_ports` with a `session_id` that has no active allocation
- **THEN** the service SHALL return success (idempotent)

### Requirement: Port allocation configuration

The port allocator SHALL read configuration from environment variables with sensible defaults.

#### Scenario: Default configuration
- **WHEN** no port allocator environment variables are set
- **THEN** `base_port` SHALL be 10000, `range_per_session` SHALL be 100, `ttl_minutes` SHALL be 120, `max_sessions` SHALL be 20, and `conflict_block_minutes` SHALL be 30

#### Scenario: Custom configuration
- **WHEN** `PORT_ALLOC_BASE`, `PORT_ALLOC_RANGE`, `PORT_ALLOC_TTL_MINUTES`, `PORT_ALLOC_MAX_SESSIONS`, or `PORT_ALLOC_CONFLICT_BLOCK_MINUTES` are set
- **THEN** the allocator SHALL use those values

#### Scenario: Invalid configuration values
- **WHEN** `base_port` is below 1024 or `range_per_session` is below 5
- **THEN** the service SHALL raise a configuration error at startup
- **AND** no allocation SHALL be served

### Requirement: Standalone operation

The port allocator service MUST function without any database backend (ParadeDB, Supabase, or otherwise) or other coordination service being configured. When a database backend is configured, the allocator SHALL use it as the durable lease store.

#### Scenario: No database configured
- **WHEN** neither `POSTGRES_DSN` nor `SUPABASE_URL` is set and `DB_BACKEND` is not configured
- **THEN** `allocate_ports` and `release_ports` SHALL still work correctly using in-memory state
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
- **AND** the health check URL MUST be built from `${AGENT_COORDINATOR_REST_PORT}` with no literal fallback

#### Scenario: Downstream phases read the contract
- **WHEN** the smoke, gen-eval, playwright, or security phases need a service address
- **THEN** they MUST read `API_BASE_URL`, `UI_ORIGIN`, or `AGENT_COORDINATOR_REST_PORT` from the env
- **AND** the ZAP target MUST be `http://localhost:${AGENT_COORDINATOR_REST_PORT}` with no literal fallback

#### Scenario: Teardown releases the lease
- **WHEN** the validate-feature run reaches Teardown, on success or failure
- **THEN** it MUST call `port-lease release --session-id "$VALIDATION_SESSION_ID"`
- **AND** a failed release MUST be logged as a warning without changing the validation result

### Requirement: Heartbeat and Dead Agent Detection

The system SHALL detect unresponsive agents and reclaim their resources through heartbeat monitoring.

- Agents SHALL periodically update a heartbeat timestamp
- The system SHALL provide a cleanup function for agents whose heartbeat is stale
- Stale agent cleanup SHALL release held file locks
- Stale agent cleanup SHALL release held port leases
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
- **AND** all port leases held by those agents are released
- **AND** system returns the count of cleaned-up agents, released locks, and released port leases as `agents_cleaned`, `locks_released`, and `ports_released`

#### Scenario: Active agent not affected by cleanup
- **WHEN** cleanup function runs
- **AND** agent's `last_heartbeat` is within the stale threshold
- **THEN** agent's status, locks, and port leases are not affected

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

#### Scenario: Conflict report for unknown session
- **WHEN** `POST /ports/conflict` names a `session_id` with no active allocation
- **THEN** the service SHALL still block the slot containing `port`
- **AND** SHALL return `{success: true, blocked_until: <timestamp>}`

### Requirement: Port lease isolation gate

The allocator SHALL refuse to lease host ports to sessions that already run in an environment with its own port namespace.

#### Scenario: Isolated session requests ports
- **WHEN** `allocate_ports` is called with `isolation_provided: true`
- **THEN** the service SHALL return `{success: false, error: "isolation_provided"}`
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

#### Scenario: Orphaned lease is released
- **WHEN** a client calls `POST /ports/reconcile` with the list of running `compose_project_name`s for its host
- **AND** an active lease's project is absent from that list and the lease is older than `conflict_block_minutes`
- **THEN** the service SHALL release that lease
- **AND** SHALL return the released session ids

#### Scenario: Running project without a lease
- **WHEN** the reconciliation list contains a project whose name matches an allocator-generated name but no lease exists
- **THEN** the service SHALL block the slot implied by the reported ports until `conflict_block_minutes` elapse
- **AND** SHALL return that project under `adopted_blocks`

#### Scenario: Reconciliation from an isolated session
- **WHEN** `POST /ports/reconcile` is called by a session with `isolation_provided: true`
- **THEN** the service SHALL return `{success: false, error: "isolation_provided"}`
- **AND** no lease SHALL change

## ADDED Requirements

### Requirement: Port allocation service

The port allocator service SHALL assign conflict-free port blocks to sessions without requiring any database backend. Each block SHALL contain 4 ports at fixed offsets within the block: offset +0 for `db_port`, +1 for `rest_port`, +2 for `realtime_port`, +3 for `api_port`. The configured `range_per_session` determines the spacing between blocks (default: 100), so the first session gets base..base+3, the second gets base+100..base+103, etc.

#### Scenario: Successful port allocation
- **WHEN** an agent calls `allocate_ports` with a `session_id`
- **THEN** the service SHALL return a port assignment containing `db_port`, `rest_port`, `realtime_port`, and `api_port` with no overlap with any active allocation
- **AND** the service SHALL return a `compose_project_name` unique to that session (format: `ac-<first 8 chars of session_id hash>`)
- **AND** the service SHALL return an `env_snippet` string in `export VAR=value` format, one variable per line, containing `AGENT_COORDINATOR_DB_PORT`, `AGENT_COORDINATOR_REST_PORT`, `AGENT_COORDINATOR_REALTIME_PORT`, `API_PORT`, `COMPOSE_PROJECT_NAME`, and `SUPABASE_URL`

#### Scenario: Duplicate session allocation
- **WHEN** an agent calls `allocate_ports` with a `session_id` that already has an active allocation
- **THEN** the service SHALL return the existing allocation unchanged
- **AND** the lease TTL SHALL be refreshed

#### Scenario: Port range exhaustion
- **WHEN** all available port blocks are allocated and a new allocation is requested
- **THEN** the service SHALL return `{success: false, error: "no_ports_available"}`
- **AND** no existing allocation SHALL be affected

### Requirement: Port allocation lease management

Port allocations SHALL have a configurable TTL and MUST be automatically reclaimed after expiry.

#### Scenario: Lease expires
- **WHEN** a port allocation's TTL elapses without renewal
- **THEN** the port block SHALL be available for new allocations
- **AND** subsequent calls to `allocate_ports` with a new session MAY reuse the expired block's ports

#### Scenario: Explicit release
- **WHEN** an agent calls `release_ports` with a valid `session_id`
- **THEN** the allocation SHALL be removed immediately
- **AND** the ports SHALL be available for reuse

#### Scenario: Release of unknown session
- **WHEN** an agent calls `release_ports` with a `session_id` that has no active allocation
- **THEN** the service SHALL return success (idempotent)

### Requirement: Port allocation configuration

The port allocator SHALL read configuration from environment variables with sensible defaults.

#### Scenario: Default configuration
- **WHEN** no port allocator environment variables are set
- **THEN** the service SHALL use base port 10000, range 100 per session, TTL 120 minutes, and max 20 sessions

#### Scenario: Custom configuration
- **WHEN** `PORT_ALLOC_BASE=20000` and `PORT_ALLOC_RANGE=50` are set
- **THEN** the first allocation SHALL use ports starting at 20000 (db=20000, rest=20001, realtime=20002, api=20003)
- **AND** each subsequent allocation SHALL use ports offset by 50 (second session: db=20050, rest=20051, etc.)

#### Scenario: Invalid configuration values
- **WHEN** `PORT_ALLOC_BASE` is less than 1024 or `PORT_ALLOC_RANGE` is less than 4
- **THEN** the service SHALL raise a configuration error at startup
- **AND** the error message SHALL specify which value is invalid and what the minimum acceptable value is

### Requirement: MCP tool exposure

The port allocator SHALL be accessible via MCP tools for local agents.

#### Scenario: MCP allocate_ports tool
- **WHEN** a local agent invokes the `allocate_ports` MCP tool with `session_id="worktree-1"`
- **THEN** the tool SHALL return a dict with `success: true`, `allocation` (containing `db_port`, `rest_port`, `realtime_port`, `api_port`, `compose_project_name`), and `env_snippet`

#### Scenario: MCP release_ports tool
- **WHEN** a local agent invokes the `release_ports` MCP tool with `session_id="worktree-1"`
- **THEN** the tool SHALL return `{success: true}`

#### Scenario: MCP ports_status tool
- **WHEN** a local agent invokes the `ports_status` MCP tool
- **THEN** the tool SHALL return a list of all active allocations with session IDs, port assignments, and remaining TTL in minutes

#### Scenario: MCP allocate_ports when range exhausted
- **WHEN** a local agent invokes `allocate_ports` and all port blocks are in use
- **THEN** the tool SHALL return `{success: false, error: "no_ports_available"}`

### Requirement: HTTP API exposure

The port allocator SHALL be accessible via HTTP endpoints for cloud agents.

#### Scenario: HTTP allocate endpoint
- **WHEN** a POST request is made to `/ports/allocate` with `{"session_id": "worktree-1"}` and a valid API key
- **THEN** the endpoint SHALL return 200 with port allocation details and env snippet

#### Scenario: HTTP status endpoint
- **WHEN** a GET request is made to `/ports/status`
- **THEN** the endpoint SHALL return a list of all active allocations with session IDs, ports, and remaining TTL

#### Scenario: HTTP release endpoint
- **WHEN** a POST request is made to `/ports/release` with `{"session_id": "worktree-1"}` and a valid API key
- **THEN** the endpoint SHALL return 200 with `{success: true}`

#### Scenario: HTTP allocate without API key
- **WHEN** a POST request is made to `/ports/allocate` without a valid API key
- **THEN** the endpoint SHALL return 401 Unauthorized

#### Scenario: HTTP allocate with missing session_id
- **WHEN** a POST request is made to `/ports/allocate` with an empty or missing `session_id`
- **THEN** the endpoint SHALL return 422 with a validation error

### Requirement: Standalone operation

The port allocator service MUST function without Supabase, database connections, or any other coordination service being configured.

#### Scenario: No database configured
- **WHEN** `SUPABASE_URL` is not set and `DB_BACKEND` is not configured
- **THEN** `allocate_ports` and `release_ports` SHALL still work correctly using in-memory state
- **AND** no database connection SHALL be attempted by the port allocator

#### Scenario: Database configured but port allocator used
- **WHEN** the full agent-coordinator is running with database
- **THEN** the port allocator SHALL still use in-memory state (not database)
- **AND** other services (locks, memory, etc.) SHALL continue using the database as before

## MODIFIED Requirements

### Requirement: Validate-feature port configuration

The validate-feature skill SHALL use environment variables for all port references instead of hardcoded values.

#### Scenario: Docker health check uses env var
- **WHEN** the validate-feature skill checks if the REST API is ready
- **THEN** the health check URL MUST use `${AGENT_COORDINATOR_REST_PORT:-3000}` instead of hardcoded `localhost:3000`

#### Scenario: Docker-compose invocation forwards port vars
- **WHEN** the validate-feature skill starts docker-compose
- **THEN** the invocation MUST explicitly pass `AGENT_COORDINATOR_DB_PORT`, `AGENT_COORDINATOR_REST_PORT`, and `AGENT_COORDINATOR_REALTIME_PORT` environment variables

#### Scenario: Hardcoded port in existing code example
- **WHEN** the validate-feature skill contains inline code examples referencing ports
- **THEN** those examples MUST use the `AGENT_COORDINATOR_REST_PORT` environment variable or `${AGENT_COORDINATOR_REST_PORT:-3000}` pattern

### Requirement: Integration test port configuration

Integration tests SHALL read port configuration from environment variables.

#### Scenario: Custom port via env var
- **WHEN** `AGENT_COORDINATOR_REST_PORT=13000` is set
- **THEN** integration tests MUST connect to `http://localhost:13000` instead of the default `http://localhost:3000`

#### Scenario: Default port when env var not set
- **WHEN** `AGENT_COORDINATOR_REST_PORT` is not set
- **THEN** integration tests SHALL default to `http://localhost:3000`

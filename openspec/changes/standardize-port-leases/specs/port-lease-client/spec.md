## ADDED Requirements

### Requirement: Port lease backend selection

The shared client `skills/shared/port_lease.py` SHALL choose exactly one backend per acquisition in this order: an explicit `PORT_LEASE_BACKEND` value, then `none` when `EnvironmentProfile.detect().isolation_provided` is true, then `coordinator` when `detect_coordination()` reports it available, then `file`. The chosen backend SHALL be recorded in the emitted env as `PORT_LEASE_BACKEND`.

#### Scenario: Coordinator reachable
- **WHEN** `PortLease.acquire(session_id)` is called with no override, outside an isolated environment, and the coordinator health check succeeds
- **THEN** the lease SHALL be obtained from `POST /ports/allocate`
- **AND** the emitted env SHALL contain `PORT_LEASE_BACKEND=coordinator`

#### Scenario: Coordinator unreachable
- **WHEN** `acquire` is called and the coordinator request fails or times out within 2 seconds
- **THEN** the client SHALL obtain the lease from the file backend
- **AND** SHALL log a warning naming the coordinator error
- **AND** the emitted env SHALL contain `PORT_LEASE_BACKEND=file`

#### Scenario: Isolated environment
- **WHEN** `acquire` is called and `isolation_provided` is true
- **THEN** the client SHALL NOT contact the coordinator or the file registry
- **AND** SHALL emit the fixed compose defaults with `PORT_LEASE_BACKEND=none`

#### Scenario: Explicit override
- **WHEN** `PORT_LEASE_BACKEND=file` is set
- **THEN** the client SHALL use the file backend even if the coordinator is reachable

### Requirement: Port lease env contract

Every backend SHALL emit the same key set: `AGENT_COORDINATOR_DB_PORT`, `AGENT_COORDINATOR_REST_PORT`, `AGENT_COORDINATOR_REALTIME_PORT`, `API_PORT`, `UI_PORT`, `DB_PORT`, `COMPOSE_PROJECT_NAME`, `SUPABASE_URL`, `API_BASE_URL`, `UI_ORIGIN`, `COORDINATOR_CORS_ALLOWED_ORIGINS`, `PORT_LEASE_BACKEND`, and `PORT_LEASE_SESSION_ID`. The contract is defined in `contracts/schemas/port-lease-env.schema.json`.

#### Scenario: Contract is backend-independent
- **WHEN** a lease is acquired from each of the `coordinator`, `file`, and `none` backends
- **THEN** the set of emitted keys SHALL be identical across the three
- **AND** each emitted value SHALL validate against the contract schema

#### Scenario: Shell format
- **WHEN** `port-lease acquire --format shell` is run
- **THEN** stdout SHALL contain one `export KEY=value` line per key and nothing else
- **AND** the output SHALL be safe to pass to `eval`

#### Scenario: JSON format
- **WHEN** `port-lease acquire --format json` is run
- **THEN** stdout SHALL contain a single JSON object with the contract keys

### Requirement: Bind probe and conflict retry

Before returning a lease from the `coordinator` or `file` backend, the client SHALL attempt to bind each port in the block on `127.0.0.1`. On a bound port it SHALL report the conflict to the backend and re-acquire, at most three times.

#### Scenario: All ports free
- **WHEN** every port in the returned block binds successfully
- **THEN** the lease SHALL be returned unchanged

#### Scenario: One port already bound
- **WHEN** a port in the block is held by another process
- **THEN** the client SHALL call `POST /ports/conflict` (coordinator) or mark the slot blocked in the registry (file)
- **AND** SHALL request a new block
- **AND** the returned lease SHALL NOT contain the bound port

#### Scenario: Three consecutive conflicts
- **WHEN** three successive blocks each contain a bound port
- **THEN** `acquire` SHALL raise `PortLeaseError` listing the three blocked slots
- **AND** no lease SHALL remain held for the session

### Requirement: Context-managed release

`PortLease` SHALL expose a context manager that releases the lease on exit, and a `release(session_id)` call that is idempotent.

#### Scenario: Normal exit
- **WHEN** a `with PortLease.acquire(session_id) as lease:` block exits normally
- **THEN** the backend release SHALL be called once

#### Scenario: Exception exit
- **WHEN** the block exits by exception
- **THEN** the backend release SHALL still be called
- **AND** the original exception SHALL propagate

#### Scenario: Release failure
- **WHEN** the backend release raises
- **THEN** the client SHALL log a warning and return
- **AND** SHALL NOT raise from `__exit__`

### Requirement: Host reconciliation command

The client SHALL provide `port-lease reconcile`, which lists the host's compose projects and reports them to the active backend so orphaned leases are released and unleased projects are protected.

#### Scenario: Orphaned lease on the host
- **WHEN** `port-lease reconcile` runs and a lease's `compose_project_name` is not among `docker compose ls` results
- **THEN** the backend SHALL release that lease
- **AND** the command SHALL print the released session ids

#### Scenario: Compose CLI unavailable
- **WHEN** `port-lease reconcile` runs and no container runtime is found
- **THEN** the command SHALL exit 0 with a message that reconciliation was skipped
- **AND** no lease SHALL change

### Requirement: File backend layout parity

The file backend SHALL use the same block layout, base port, spacing, and project-name format as the coordinator allocator, read from the same `PORT_ALLOC_*` environment variables, so the two backends can never hand out overlapping blocks on one host.

#### Scenario: Same slot arithmetic
- **WHEN** the file backend allocates its first block with default configuration
- **THEN** the block SHALL be 10000..10004 with project name `ac-<hash>`
- **AND** the on-disk registry SHALL record the slot index, ports, session id, and expiry

#### Scenario: Registry lock contention
- **WHEN** two processes call the file backend concurrently
- **THEN** they SHALL receive distinct slots
- **AND** the registry file SHALL remain valid JSON

### Requirement: Hardcoded port regression gate

The validate-feature architecture check SHALL fail when a literal `localhost:<port>` or `127.0.0.1:<port>` appears in `skills/**/*.py`, `skills/**/SKILL.md`, `apps/kanban-viz/src/**`, or `packages/gen-eval/src/**` outside the allowlist in `skills/validate-feature/scripts/port_literal_allowlist.txt`.

#### Scenario: New literal introduced
- **WHEN** a changed file adds `http://localhost:8081` outside the allowlist
- **THEN** the check SHALL report the file and line
- **AND** the architecture phase SHALL be marked `fail`

#### Scenario: Allowlisted documentation example
- **WHEN** the literal appears in a file and line pattern listed in the allowlist
- **THEN** the check SHALL pass

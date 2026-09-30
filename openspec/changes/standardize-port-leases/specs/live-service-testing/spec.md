## MODIFIED Requirements

### Requirement: LST.2 Docker Stack Environment

`DockerStackEnvironment` SHALL obtain its port block through the shared `PortLease` client (`skills/shared/port_lease.py`) before starting services, and SHALL NOT own a port range of its own. It SHALL detect the container runtime by probing for `docker` CLI first, then `podman` CLI, raising `RuntimeError` if neither is found. It SHALL invoke `<runtime> compose up -d` with the lease env, setting `COMPOSE_PROJECT_NAME` to the lease's project name. `wait_ready()` SHALL verify PostgreSQL responds to `pg_isready -h localhost -p <db_port>` AND the coordination API (if running) responds with HTTP 200 on `GET /health`. On teardown, it SHALL run `<runtime> compose down -v` then release the lease through the same client.

Note: The coordination API runs on the host (started separately or via the stack launcher), not inside Docker compose. Docker compose provides only PostgreSQL (and optionally OpenBao). Smoke tests that require the API assume it is started by the caller or by `phase_deploy.py`.

#### Scenario: Docker stack starts with leased ports
- **WHEN** `DockerStackEnvironment.start()` is called and the `PortLease` client returns a block starting at 10000
- **THEN** docker compose SHALL be invoked with `AGENT_COORDINATOR_DB_PORT=10000` and `COMPOSE_PROJECT_NAME` set to the lease's project name
- **AND** `env_vars()` SHALL return the full lease env contract plus `POSTGRES_DSN`, `SESSION_ID`, and `ENV_TYPE=docker`

#### Scenario: Lease acquisition fails
- **WHEN** `start()` is called and neither the coordinator nor the file backend can provide a lease
- **THEN** `RuntimeError` SHALL be raised naming the backends tried
- **AND** no compose command SHALL be executed

#### Scenario: Docker stack health check succeeds
- **WHEN** `wait_ready(timeout_seconds=120)` is called against a running stack with PostgreSQL listening
- **THEN** `pg_isready` SHALL return 0 within the timeout and `wait_ready` SHALL return

#### Scenario: Docker stack health check timeout
- **WHEN** `wait_ready(timeout_seconds=10)` is called and PostgreSQL never starts
- **THEN** `TimeoutError` SHALL be raised after 10 seconds of polling

#### Scenario: Docker stack teardown releases resources
- **WHEN** `teardown()` is called on a running stack
- **THEN** `docker compose down -v` SHALL be invoked
- **AND** the lease SHALL be released through the `PortLease` client
- **AND** a second `teardown()` call SHALL be a no-op

#### Scenario: Podman auto-detection
- **WHEN** Docker CLI is not found but Podman CLI is installed and `start()` is called
- **THEN** `podman compose` SHALL be used instead of `docker compose`

#### Scenario: No container runtime available
- **WHEN** neither Docker nor Podman CLI is found on PATH and `start()` is called
- **THEN** `RuntimeError` SHALL be raised with message "No container runtime found. Install docker or podman."
- **AND** any lease acquired before detection SHALL be released

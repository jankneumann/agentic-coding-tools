# Delta Spec: Docker Lifecycle — Container Auto-Start

## ADDED Requirements

### Requirement: Container Runtime Detection

The docker manager SHALL detect available container runtimes.

- Detection SHALL check for `docker` first, then `podman`
- A runtime SHALL be considered available only when both `which <runtime>` succeeds AND `<runtime> info` returns exit code 0
- The `docker.container_runtime` profile field SHALL support `"auto"`, `"docker"`, and `"podman"`
- When set to `"auto"`, the first available runtime SHALL be used

#### Scenario: Docker detected
- **WHEN** `docker` is on PATH and `docker info` succeeds
- **THEN** `detect_runtime()` SHALL return `"docker"`

#### Scenario: Only Podman available
- **WHEN** `docker` is not on PATH but `podman` is available
- **THEN** `detect_runtime()` SHALL return `"podman"`

#### Scenario: No runtime available
- **WHEN** neither `docker` nor `podman` is available
- **THEN** `detect_runtime()` SHALL return `None`

### Requirement: Container Auto-Start

The docker manager SHALL start the ParadeDB container when `docker.auto_start` is `true` in the active profile.

- If the container is already running, no action SHALL be taken
- The compose file path SHALL come from `docker.compose_file` in the profile
- The container name SHALL come from `docker.container_name` in the profile
- Start SHALL use `<runtime> compose -f <file> up -d`
- Start SHALL have a timeout of 120 seconds

#### Scenario: Container auto-started
- **WHEN** `docker.auto_start` is `true` and the container is not running
- **THEN** `docker compose up -d` SHALL be executed
- **AND** the result SHALL include `{"started": true, "runtime": "docker"}`

#### Scenario: Container already running
- **WHEN** the container is already running
- **THEN** no compose command SHALL be executed
- **AND** the result SHALL include `{"already_running": true}`

#### Scenario: Docker disabled in profile
- **WHEN** `docker.enabled` is `false`
- **THEN** no runtime detection or start SHALL occur
- **AND** the result SHALL include `{"started": false, "error": "docker disabled in profile"}`

#### Scenario: Compose file missing
- **WHEN** the compose file path does not exist
- **THEN** the result SHALL include an error message identifying the missing file

### Requirement: Health Wait

The docker manager SHALL wait for the container to become healthy before returning success.

- Health checking SHALL poll the container health status at 2-second intervals
- The default timeout SHALL be 60 seconds
- The container health status SHALL be read via `<runtime> inspect --format '{{.State.Health.Status}}'`

#### Scenario: Container becomes healthy
- **WHEN** the container reports `healthy` status within the timeout
- **THEN** `wait_for_healthy()` SHALL return `True`

#### Scenario: Health check times out
- **WHEN** the container does not become healthy within 60 seconds
- **THEN** `wait_for_healthy()` SHALL return `False`

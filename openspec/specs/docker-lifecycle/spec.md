# docker-lifecycle Specification

## Purpose
TBD - created by archiving change add-coordinator-profiles. Update Purpose after archive.
## Requirements
### Requirement: Container Runtime Detection

The docker manager SHALL detect available container runtimes.

- Detection SHALL check for `docker` first; if `docker info` fails on macOS AND Colima is available AND `docker.colima.auto_start` is `true`, attempt Colima VM start; then fall back to `podman`
- A runtime SHALL be considered available only when both `which <runtime>` succeeds AND `<runtime> info` returns exit code 0
- The `docker.container_runtime` profile field SHALL support `"auto"`, `"docker"`, `"podman"`, and `"colima"`
- When set to `"auto"`, the first available runtime SHALL be used
- When `preferred` is `"colima"` on a non-macOS platform, detection SHALL log a warning and behave like `"auto"`
- `detect_runtime()` SHALL accept an optional `docker_config` dict parameter (default: `None`) for backward compatibility

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

### Requirement: Colima VM Detection

The docker manager SHALL detect Colima as an available Docker daemon provider on macOS.

- Detection SHALL check for `colima` on PATH via `which colima`
- Colima SHALL be considered available only when `which colima` succeeds
- Colima VM status SHALL be checked via `colima status` (exit code 0 = running)
- When `docker.container_runtime` is `"colima"`, the manager SHALL ensure the Colima VM is running before returning `"docker"` as the runtime

### Requirement: Colima VM Lifecycle Management

The docker manager SHALL manage the Colima VM lifecycle when Colima is the selected or auto-detected provider.

- `_ensure_colima_vm()` SHALL return `bool` — `True` if the VM is running after the call, `False` otherwise
- `_ensure_colima_vm()` SHALL be idempotent: if the VM is already running, it SHALL return `True` without side effects
- VM start SHALL use `colima start` with resource arguments from the profile's `docker.colima` block
- VM start SHALL have a timeout of 120 seconds
- VM start SHALL pass `--arch aarch64 --vm-type=vz --vz-rosetta` only when `docker.colima.apple_virt` is `true` AND `platform.machine()` is `"arm64"` or `"aarch64"`
- Default resources SHALL be: 2 CPU, 4 GiB memory, 30 GiB disk
- After VM start, the manager SHALL verify `docker info` succeeds before returning `True`

### Requirement: Colima Profile Configuration

The profile schema SHALL support a `docker.colima` configuration block.

- `docker.colima.cpu` — Number of CPUs to allocate (default: 2)
- `docker.colima.memory` — Memory in GiB (default: 4)
- `docker.colima.disk` — Disk in GiB (default: 30)
- `docker.colima.apple_virt` — Use Apple Virtualization framework with Rosetta on Apple Silicon (default: true)
- `docker.colima.auto_start` — Auto-start the VM when Docker daemon is unavailable (default: true)


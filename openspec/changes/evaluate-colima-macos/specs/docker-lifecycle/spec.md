# docker-lifecycle Specification (Delta for evaluate-colima-macos)

## New Requirements

### Requirement: Colima VM Detection

The docker manager SHALL detect Colima as an available Docker daemon provider on macOS.

- Detection SHALL check for `colima` on PATH via `which colima`
- Colima SHALL be considered available only when `which colima` succeeds
- Colima VM status SHALL be checked via `colima status` (exit code 0 = running)
- The `docker.container_runtime` profile field SHALL additionally support `"colima"`
- When set to `"colima"`, the manager SHALL ensure the Colima VM is running before returning `"docker"` as the runtime

#### Scenario: Colima VM already running
- **WHEN** `colima` is on PATH and `colima status` reports the VM is running
- **AND** `docker info` succeeds (Colima is providing the Docker socket)
- **THEN** `detect_runtime()` SHALL return `"docker"`

#### Scenario: Colima installed but VM stopped
- **WHEN** `colima` is on PATH but `colima status` reports the VM is not running
- **AND** `docker.container_runtime` is `"auto"` or `"colima"`
- **AND** the platform is macOS (`sys.platform == "darwin"`)
- **THEN** `_ensure_colima_vm()` SHALL attempt to start the VM
- **AND** if startup succeeds, `detect_runtime()` SHALL return `"docker"`

#### Scenario: Colima not installed
- **WHEN** `colima` is not on PATH
- **AND** `docker.container_runtime` is `"auto"`
- **THEN** detection SHALL proceed with standard Docker/Podman fallback (unchanged behavior)

#### Scenario: Colima explicitly selected but not installed
- **WHEN** `docker.container_runtime` is `"colima"` but `colima` is not on PATH
- **THEN** `detect_runtime()` SHALL return `None`
- **AND** the result SHALL include an error indicating Colima is not installed

#### Scenario: Non-macOS platform with Colima preference
- **WHEN** `docker.container_runtime` is `"colima"` and the platform is not macOS
- **THEN** `detect_runtime()` SHALL log a warning that Colima is macOS-only
- **AND** detection SHALL fall back to standard Docker/Podman detection

### Requirement: Colima VM Lifecycle Management

The docker manager SHALL manage the Colima VM lifecycle when Colima is the selected or auto-detected provider.

- VM start SHALL use `colima start` with resource arguments from the profile's `docker.colima` block
- VM start SHALL have a timeout of 120 seconds
- VM start SHALL pass `--arch aarch64 --vm-type=vz --vz-rosetta` on Apple Silicon when `docker.colima.apple_virt` is `true` (default)
- Resource arguments SHALL be: `--cpu <N> --memory <N> --disk <N>`
- Default resources SHALL be: 2 CPU, 4 GiB memory, 30 GiB disk
- After VM start, the manager SHALL verify `docker info` succeeds before returning

#### Scenario: Colima VM started successfully
- **WHEN** `_ensure_colima_vm()` is called and Colima is installed but not running
- **THEN** `colima start` SHALL be executed with profile-configured resources
- **AND** after startup, `docker info` SHALL be verified
- **AND** the result SHALL include `{"colima_started": true}`

#### Scenario: Colima VM startup fails
- **WHEN** `colima start` fails or times out
- **THEN** `_ensure_colima_vm()` SHALL return `False`
- **AND** detection SHALL fall back to Podman
- **AND** the error SHALL be logged at WARNING level

#### Scenario: Colima VM startup times out
- **WHEN** `colima start` does not complete within 120 seconds
- **THEN** `_ensure_colima_vm()` SHALL return `False`
- **AND** the error message SHALL indicate the timeout

### Requirement: Colima Profile Configuration

The profile schema SHALL support a `docker.colima` configuration block.

- `docker.colima.cpu` — Number of CPUs to allocate (default: 2)
- `docker.colima.memory` — Memory in GiB (default: 4)
- `docker.colima.disk` — Disk in GiB (default: 30)
- `docker.colima.apple_virt` — Use Apple Virtualization framework with Rosetta (default: true)
- `docker.colima.auto_start` — Auto-start the VM when Docker daemon is unavailable (default: true)

#### Scenario: Custom resource allocation
- **WHEN** `docker.colima.cpu` is set to 4 and `docker.colima.memory` is set to 8
- **THEN** `colima start` SHALL include `--cpu 4 --memory 8`

#### Scenario: Default resource allocation
- **WHEN** `docker.colima` block is absent or empty
- **THEN** `colima start` SHALL use `--cpu 2 --memory 4 --disk 30`

### Modified Requirements

### Requirement: Container Runtime Detection (Modified)

The docker manager SHALL detect available container runtimes.

- Detection SHALL check for `docker` first; if `docker info` fails on macOS AND Colima is available, attempt Colima VM start; then fall back to `podman`
- The `docker.container_runtime` profile field SHALL support `"auto"`, `"docker"`, `"podman"`, and `"colima"`
- All other existing detection requirements remain unchanged

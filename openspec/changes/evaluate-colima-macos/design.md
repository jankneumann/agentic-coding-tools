# Design: evaluate-colima-macos

## Design Decisions

### D1: Colima as a Docker daemon provider, not a CLI runtime

Colima's architecture exposes a standard Docker socket (`~/.colima/default/docker.sock` or `/var/run/docker.sock`). Once the VM is running, the standard `docker` CLI works identically to Docker Desktop. Therefore, Colima is treated as a **VM bootstrap layer** — the code starts the VM, then delegates to the existing `docker` runtime path.

**Rejected alternative**: Adding `"colima"` as a peer runtime alongside `"docker"` and `"podman"` that routes commands through `colima nerdctl`. This would duplicate Docker CLI compatibility that Colima already provides and introduce a third command path through all container operations.

### D2: macOS-only Colima activation

Colima is designed for macOS (and Linux, but Linux typically has Docker daemon natively). The VM auto-start logic SHALL only activate when `sys.platform == "darwin"`. On Linux/CI, the existing Docker/Podman detection path is unchanged.

**Rationale**: Avoids unnecessary Colima checks on Linux servers and CI runners where Docker is typically available directly. A warning is logged if a profile explicitly sets `"colima"` on a non-macOS platform.

### D3: Detection order with Colima integration

The modified detection sequence for `"auto"` mode:

```
1. Try `docker info` → if succeeds, return "docker" (covers Docker Desktop, already-running Colima, remote Docker)
2. If macOS AND `which colima` succeeds → try _ensure_colima_vm()
   a. If Colima starts and `docker info` now succeeds → return "docker"
   b. If Colima fails → log warning, continue
3. Try `podman` → if `which podman` and `podman info` succeed, return "podman"
4. Return None
```

**Key property**: Step 1 catches already-running Colima VMs without any Colima-specific code. The Colima integration only activates in step 2 when there's no Docker daemon available at all. This means Docker Desktop users see zero behavioral change.

### D4: Resource defaults

Default Colima VM resources: 2 CPU, 4 GiB memory, 30 GiB disk. These are conservative defaults suitable for running ParadeDB and optional OpenBao. Teams running heavier workloads can increase via `docker.colima.*` profile fields.

The `apple_virt: true` default enables the Apple Virtualization framework with Rosetta x86 emulation, which provides near-native performance for `amd64` container images on Apple Silicon. This is preferred over the older QEMU backend.

**Architecture detection**: The `--arch aarch64 --vm-type=vz --vz-rosetta` flags are only passed when `platform.machine()` returns `"arm64"` or `"aarch64"`. On Intel Macs (`x86_64`), these flags are silently skipped regardless of the `apple_virt` setting — the QEMU backend is used instead. This avoids requiring users to set different profile values per machine architecture.

### D5: _ensure_colima_vm() is idempotent

Calling `_ensure_colima_vm()` when the VM is already running is a no-op (checked via `colima status`). This prevents unnecessary VM restarts when `detect_runtime()` is called multiple times during a session.

## Data Flow

```
start_container(docker_config)
  │
  ├─ docker disabled? → return error
  │
  ├─ detect_runtime(preferred)
  │    │
  │    ├─ preferred == "colima"?
  │    │    ├─ macOS + colima installed? → _ensure_colima_vm(colima_config) → try docker
  │    │    ├─ macOS + colima NOT installed? → log warning → return None
  │    │    └─ not macOS? → log warning → behave like "auto" (try docker → try podman)
  │    │
  │    ├─ preferred == "auto"?
  │    │    ├─ try docker → success? → return "docker"
  │    │    ├─ macOS + colima installed? → _ensure_colima_vm() → try docker
  │    │    └─ try podman
  │    │
  │    └─ preferred == "docker" | "podman"? → existing behavior
  │
  ├─ is_container_running? → return already_running
  │
  └─ docker compose up -d → return started
```

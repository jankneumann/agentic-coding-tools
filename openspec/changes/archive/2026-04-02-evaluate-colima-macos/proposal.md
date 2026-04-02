# Change: evaluate-colima-macos

## Why

Docker Desktop requires a paid subscription for organizations above 250 employees or $10M revenue. Podman works as a fallback but has compose compatibility friction — `podman-compose` behaves differently from `docker compose` in networking and volume semantics, and rootless defaults can cause permission issues with certain containers (OpenBao, ZAP).

Colima provides a fully open-source (MIT) Docker-compatible runtime for macOS by running a Lima VM that exposes a standard Docker socket. Since it speaks the native Docker API, existing `docker` and `docker compose` commands work unchanged — but the VM lifecycle (start, stop, resource allocation) is a separate concern that currently requires manual intervention.

Adding managed Colima VM lifecycle support to `docker_manager.py` would let the coordinator auto-start a properly configured Colima VM when no Docker daemon is available on macOS, eliminating a common onboarding friction point while preserving full Docker/Podman compatibility.

## What Changes

- **Extend `docker_manager.py`** with Colima VM lifecycle management: detect if Colima is installed, auto-start the VM when no Docker daemon is available on macOS, configure resource limits
- **Extend `docker-lifecycle` spec** with new requirements for Colima VM detection, startup, and health verification
- **Add `"colima"` to `_ALLOWED_RUNTIMES`** in `docker_manager.py` so profiles can explicitly select Colima as the runtime preference
- **Extend profile schema** with `docker.colima` configuration block (CPU, memory, disk, VM type, Rosetta settings)
- **Update `base.yaml` and `local.yaml` profiles** with Colima defaults
- **Add onboarding documentation** with Colima setup instructions for macOS developers

## Approaches Considered

### Approach 1: Colima as auto-detected Docker provider (Recommended)

Add Colima VM lifecycle management that activates **only when `docker info` fails on macOS**. The detection order becomes: (1) check if Docker daemon is already running → use it, (2) check if Colima is installed → start Colima VM → use Docker socket it provides, (3) fall back to Podman. The `_ALLOWED_RUNTIMES` set adds `"colima"` for explicit profile selection, but `"auto"` mode just treats Colima as a way to get a Docker daemon running.

- **Pros**: Zero disruption for Docker Desktop users; Colima only activates when needed; preserves the existing `docker` CLI path so all compose files, inspect commands, and health checks work unchanged; explicit `"colima"` profile option for teams that standardize on it
- **Cons**: Adds macOS platform detection logic; Colima VM startup adds ~10-15s to first container launch; need to handle Colima installation check gracefully on Linux/CI
- **Effort**: M

### Approach 2: Colima as a first-class peer runtime

Add `"colima"` alongside `"docker"` and `"podman"` as a distinct runtime in the detection chain. All container commands route through `colima` CLI wrappers (e.g., `colima nerdctl` instead of `docker`).

- **Pros**: Full control over Colima-specific features (nerdctl, containerd)
- **Cons**: Duplicates Docker CLI compatibility that Colima already provides via its socket; introduces a third command path through all container operations; `colima nerdctl` has less ecosystem compatibility than `docker`; breaks the principle that Colima is a daemon provider, not a CLI replacement
- **Effort**: L

### Approach 3: Documentation-only with manual Colima setup

Add onboarding docs recommending Colima with install commands and configuration profiles. No code changes — rely on Colima providing a transparent Docker socket.

- **Pros**: Simplest; no code risk; works today
- **Cons**: Doesn't solve the onboarding friction of "I ran `make db-up` and got `Cannot connect to the Docker daemon`"; no managed resource allocation; every developer must manually configure Colima before first use
- **Effort**: S

### Recommended

**Approach 1** — Colima as auto-detected Docker provider. This aligns with the existing `detect_runtime()` architecture: Colima is not a runtime, it's a VM that provides the Docker runtime. The code change is localized to `docker_manager.py` with a new `_ensure_colima_vm()` helper that starts the VM when Docker isn't available on macOS. Explicit `"colima"` profile support allows teams to standardize without affecting the auto-detection path.

### Selected Approach

Approach 1 (Colima as auto-detected Docker provider) selected. Colima VM lifecycle management activates only on macOS when no Docker daemon is running. The `_ALLOWED_RUNTIMES` set adds `"colima"` for explicit profile selection, but `"auto"` mode treats Colima transparently as a Docker daemon provider.

## Impact

- **Affected specs**: `docker-lifecycle` (new requirements for Colima VM detection and lifecycle)
- **Files modified**:
  - `agent-coordinator/src/docker_manager.py` — Add Colima VM lifecycle functions, extend `_ALLOWED_RUNTIMES`
  - `agent-coordinator/profiles/base.yaml` — Add `docker.colima` configuration block
  - `agent-coordinator/profiles/local.yaml` — Set Colima defaults for local development
  - `agent-coordinator/tests/test_docker_manager.py` — Add Colima detection and lifecycle tests
  - `openspec/specs/docker-lifecycle/spec.md` — Add Colima requirements
  - `agent-coordinator/README.md` — Add Colima onboarding section
- **Files added**: None (all changes extend existing files)
- **Risk**: Low — Colima logic only activates on macOS when no Docker daemon is running; existing Docker Desktop and Podman paths are unchanged

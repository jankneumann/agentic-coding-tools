# Tasks: evaluate-colima-macos

## Phase 1: Colima VM Lifecycle Functions

- [ ] 1.1 Write tests for Colima detection and VM lifecycle in `test_docker_manager.py`
  **Spec scenarios**: docker-lifecycle.colima-vm-already-running, docker-lifecycle.colima-installed-but-stopped, docker-lifecycle.colima-not-installed, docker-lifecycle.colima-explicitly-selected-not-installed, docker-lifecycle.non-macos-with-colima-preference
  **Design decisions**: D1 (Colima as daemon provider, not CLI runtime), D2 (macOS-only activation), D5 (idempotent _ensure_colima_vm)
  **Dependencies**: None

- [ ] 1.2 Add `is_colima_installed()` function to `docker_manager.py` — check `which colima`
  **Spec scenarios**: docker-lifecycle.colima-not-installed, docker-lifecycle.colima-explicitly-selected-not-installed
  **Dependencies**: 1.1

- [ ] 1.3 Add `is_colima_running()` function to `docker_manager.py` — check `colima status`
  **Spec scenarios**: docker-lifecycle.colima-vm-already-running, docker-lifecycle.colima-installed-but-stopped
  **Design decisions**: D5 (idempotent)
  **Dependencies**: 1.1

- [ ] 1.4 Add `_ensure_colima_vm(colima_config)` function to `docker_manager.py` — start VM with resource args, verify `docker info` succeeds afterward
  **Spec scenarios**: docker-lifecycle.colima-vm-started-successfully, docker-lifecycle.colima-vm-startup-fails, docker-lifecycle.colima-vm-startup-times-out
  **Design decisions**: D1 (daemon provider), D4 (resource defaults), D5 (idempotent)
  **Dependencies**: 1.2, 1.3

## Phase 2: Runtime Detection Integration

- [ ] 2.1 Write tests for modified `detect_runtime()` with Colima auto-detection path
  **Spec scenarios**: docker-lifecycle.colima-installed-but-stopped (auto mode), docker-lifecycle.non-macos-with-colima-preference
  **Design decisions**: D3 (detection order)
  **Dependencies**: 1.1

- [ ] 2.2 Add `"colima"` to `_ALLOWED_RUNTIMES` set in `docker_manager.py`
  **Dependencies**: 2.1

- [ ] 2.3 Modify `detect_runtime()` to accept `docker_config` dict parameter (for Colima settings), integrate Colima auto-start on macOS when Docker daemon unavailable
  **Spec scenarios**: docker-lifecycle.container-runtime-detection-modified
  **Design decisions**: D2 (macOS-only), D3 (detection order)
  **Dependencies**: 1.4, 2.2

- [ ] 2.4 Update `start_container()` to pass `docker_config.get("colima", {})` to `detect_runtime()`
  **Dependencies**: 2.3

## Phase 3: Profile Configuration

- [ ] 3.1 Write tests for Colima profile configuration parsing and default values
  **Spec scenarios**: docker-lifecycle.custom-resource-allocation, docker-lifecycle.default-resource-allocation
  **Design decisions**: D4 (resource defaults)
  **Dependencies**: None

- [ ] 3.2 Add `docker.colima` block to `base.yaml` with defaults (cpu: 2, memory: 4, disk: 30, apple_virt: true, auto_start: true)
  **Spec scenarios**: docker-lifecycle.colima-profile-configuration
  **Dependencies**: 3.1

- [ ] 3.3 Add Colima-optimized settings to `local.yaml` — enable Colima auto-start for local dev
  **Dependencies**: 3.2

## Phase 4: Documentation

- [ ] 4.1 Update `openspec/specs/docker-lifecycle/spec.md` — merge delta requirements from this change
  **Dependencies**: 1.4, 2.3, 3.2

- [ ] 4.2 Add Colima onboarding section to `agent-coordinator/README.md` — install instructions, configuration options, troubleshooting
  **Dependencies**: 3.3

## Verification

- [ ] 5.1 Run existing `test_docker_manager.py` tests to confirm no regressions
  **Dependencies**: 2.4
- [ ] 5.2 Run `mypy --strict` on `docker_manager.py` to verify type safety
  **Dependencies**: 2.4
- [ ] 5.3 Run `ruff check` on modified files
  **Dependencies**: 2.4

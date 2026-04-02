# Tasks: evaluate-colima-macos

## Phase 1: Colima VM Lifecycle Functions

- [ ] 1.1 Write unit tests for `is_colima_installed()`, `is_colima_running()`, and `_ensure_colima_vm()` in `test_docker_manager.py`
  **Scope**: Tests for the three new helper functions ONLY — mock `shutil.which`, `subprocess.run`, `platform.machine()`. Cover: installed/not-installed, running/stopped, start success/failure/timeout, auto_start disabled, Apple Silicon vs Intel flag selection, idempotent no-op when already running.
  **Spec scenarios**: docker-lifecycle.colima-vm-already-running, docker-lifecycle.colima-installed-but-stopped, docker-lifecycle.colima-not-installed, docker-lifecycle.colima-installed-but-auto-start-disabled, docker-lifecycle.colima-vm-started-successfully, docker-lifecycle.colima-vm-startup-fails, docker-lifecycle.colima-vm-startup-times-out, docker-lifecycle.apple-silicon-mac, docker-lifecycle.intel-mac
  **Design decisions**: D1, D2, D4, D5, D6
  **Dependencies**: None

- [ ] 1.2 Add `is_colima_installed()` function to `docker_manager.py` — check `which colima`
  **Spec scenarios**: docker-lifecycle.colima-not-installed, docker-lifecycle.colima-explicitly-selected-not-installed
  **Dependencies**: 1.1

- [ ] 1.3 Add `is_colima_running()` function to `docker_manager.py` — check `colima status`
  **Spec scenarios**: docker-lifecycle.colima-vm-already-running, docker-lifecycle.colima-installed-but-stopped
  **Design decisions**: D6 (idempotent)
  **Dependencies**: 1.1

- [ ] 1.4 Add `_ensure_colima_vm(colima_config)` function to `docker_manager.py` — check auto_start setting, check if already running (no-op), start VM with resource args, detect Apple Silicon via `platform.machine()`, verify `docker info` afterward. Returns `bool`.
  **Spec scenarios**: docker-lifecycle.colima-vm-started-successfully, docker-lifecycle.colima-vm-already-running-idempotent, docker-lifecycle.colima-vm-startup-fails, docker-lifecycle.colima-vm-startup-times-out, docker-lifecycle.auto-start-disabled, docker-lifecycle.apple-silicon-mac, docker-lifecycle.intel-mac
  **Design decisions**: D1 (daemon provider), D4 (resource defaults), D6 (idempotent)
  **Dependencies**: 1.2, 1.3

## Phase 2: Runtime Detection Integration

- [ ] 2.1 Write integration tests for modified `detect_runtime()` with Colima path in `test_docker_manager.py`
  **Scope**: Tests for the modified `detect_runtime()` function — how it integrates Colima into the detection chain. Cover: auto mode with Colima fallback on macOS, explicit "colima" on macOS, explicit "colima" on non-macOS (falls back to auto behavior), explicit "colima" not installed (returns None). These tests mock `_ensure_colima_vm()` as a unit — the helper's internal behavior is tested in 1.1.
  **Spec scenarios**: docker-lifecycle.colima-installed-but-stopped (auto mode), docker-lifecycle.non-macos-with-colima-preference, docker-lifecycle.colima-explicitly-selected-not-installed
  **Design decisions**: D3 (detection order)
  **Dependencies**: 1.4

- [ ] 2.2 Add `"colima"` to `_ALLOWED_RUNTIMES` set in `docker_manager.py`
  **Dependencies**: 2.1

- [ ] 2.3 Modify `detect_runtime()` to accept optional `docker_config: dict | None = None` parameter (backward-compatible default), integrate Colima auto-start on macOS when Docker daemon unavailable
  **Spec scenarios**: docker-lifecycle.container-runtime-detection-modified
  **Design decisions**: D2 (macOS-only), D3 (detection order)
  **Note**: Existing callers pass only `preferred` — the new parameter has a default of `None` for backward compatibility. Existing tests continue to work unchanged.
  **Dependencies**: 1.4, 2.2

- [ ] 2.4 Update `start_container()` to pass `docker_config` to `detect_runtime()`, and include `"colima_started": true` in result dict when Colima VM was started
  **Approach**: Call `is_colima_running()` before `detect_runtime()`. If Colima wasn't running before but `detect_runtime()` returns `"docker"` on macOS, infer Colima was auto-started. No return type changes to `detect_runtime()` needed. (Design decision D5)
  **Dependencies**: 2.3

## Phase 3: Profile Configuration

- [ ] 3.1 Write tests for Colima profile configuration parsing and default values
  **Spec scenarios**: docker-lifecycle.custom-resource-allocation, docker-lifecycle.default-resource-allocation, docker-lifecycle.auto-start-disabled
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

## Dependency Graph

```
Phase 1:  1.1 ──┬── 1.2 ──┐
                │          ├── 1.4
                └── 1.3 ──┘
                     (1.2 and 1.3 are independent of each other)

Phase 2:  2.1 ── 2.2 ─┐
          1.4 ─────────┼── 2.3 ── 2.4
                       │
Phase 3:  3.1 ── 3.2 ── 3.3
          (Phase 3 is independent of Phase 1/2 — different files)

Phase 4:  1.4 + 2.3 + 3.2 → 4.1
          3.3 → 4.2

Phase 5:  2.4 → 5.1, 5.2, 5.3 (all independent of each other)
```

**Parallelizability**: Phase 1 (tasks 1.1→1.4) and Phase 3 (tasks 3.1→3.3) can run in parallel — they modify different files (`docker_manager.py` + `test_docker_manager.py` vs `base.yaml` + `local.yaml`). Max parallel width: 2 agents.

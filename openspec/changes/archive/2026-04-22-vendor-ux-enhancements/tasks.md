# Tasks: Vendor UX Enhancements

**Change ID**: `vendor-ux-enhancements`

## Phase 1: Adversarial Review Mode

- [x] 1.1 Write tests for adversarial prompt wrapping and review skill flag handling
  **Spec scenarios**: vendor-ux.1.2 (prompt prefix), vendor-ux.1.3 (schema compliance)
  **Design decisions**: D1 (prompt-only, no new dispatch_mode)
  **Dependencies**: None

- [x] 1.2 Add adversarial prompt prefix constant and `--adversarial` flag to `parallel-review-plan` and `parallel-review-implementation` SKILL.md files. When flag is set, wrap the review prompt with adversarial framing before calling `review_dispatcher.py` with `--mode review` (unchanged).
  **Spec scenarios**: vendor-ux.1.1-1.5 (all adversarial scenarios)
  **Design decisions**: D1, D2
  **Dependencies**: 1.1

## Phase 2: Micro-Task Quick Dispatch

- [x] 2.1 Write tests for quick-task vendor selection, dispatch, output handling, and complexity warning
  **Spec scenarios**: vendor-ux.2.3 (vendor selection), vendor-ux.2.5 (output), vendor-ux.2.6 (complexity warning), vendor-ux.2.7 (timeout)
  **Design decisions**: D3 (quick dispatch_mode), D4 (freeform output)
  **Dependencies**: None

- [x] 2.2 Add `quick` dispatch_mode to `agents.yaml` for all vendors (read-write args, no worktree isolation)
  **Spec scenarios**: vendor-ux.2.4 (dispatch mode)
  **Design decisions**: D3
  **Dependencies**: 2.1

- [x] 2.3 Create `/quick-task` skill (SKILL.md + scripts/quick_task.py): accept prompt + optional `--vendor`, dispatch via `ReviewOrchestrator.dispatch_and_wait(mode="quick")`, return raw stdout
  **Spec scenarios**: vendor-ux.2.1-2.7
  **Design decisions**: D3, D4
  **Dependencies**: 2.1, 2.2

## Phase 3: Vendor Health Check

- [x] 3.1 Write tests for vendor health checking (CLI presence, API key resolution, probe logic, table/JSON output)
  **Spec scenarios**: vendor-ux.3.2 (dimensions), vendor-ux.3.3 (output format), vendor-ux.3.7 (no inference)
  **Design decisions**: D5 (dual-use script), D6 (lightweight probes)
  **Dependencies**: None

- [x] 3.2 Create `vendor_health.py` with `check_all_vendors()`, `check_vendor()`, and `__main__` CLI (`--json` flag)
  **Spec scenarios**: vendor-ux.3.1-3.3, vendor-ux.3.7
  **Design decisions**: D5, D6
  **Dependencies**: 3.1

- [x] 3.3 Create `/vendor:status` skill wrapper (SKILL.md) and add `_check_vendor_health()` to `WatchdogService` with `vendor.unavailable` / `vendor.recovered` event emission
  **Spec scenarios**: vendor-ux.3.4-3.8
  **Design decisions**: D7 (coordinator_agent channel)
  **Dependencies**: 3.2

## Phase 4: Integration

- [x] 4.1 End-to-end tests for adversarial review consensus, quick-task dispatch, and vendor health CLI + watchdog events
  **Dependencies**: 1.2, 2.3, 3.3

- [x] 4.2 Update docs/lessons-learned.md with vendor UX patterns and codex-plugin-cc comparison notes
  **Dependencies**: 4.1

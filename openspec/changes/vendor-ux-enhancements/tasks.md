# Tasks: Vendor UX Enhancements

**Change ID**: `vendor-ux-enhancements`

## Phase 1: Adversarial Review Mode

- [ ] 1.1 Write tests for adversarial prompt construction and dispatch
  **Spec scenarios**: vendor-ux.1.2 (prompt prefix), vendor-ux.1.3 (schema compliance), vendor-ux.1.6 (mixed-mode)
  **Design decisions**: D1 (dispatch_mode not finding type), D2 (prompt in dispatcher)
  **Dependencies**: None

- [ ] 1.2 Add `adversarial` dispatch_mode to `agents.yaml` for all vendors
  **Spec scenarios**: vendor-ux.1.1 (dispatch mode registration)
  **Dependencies**: 1.1

- [ ] 1.3 Add adversarial prompt prefix and mode handling to `review_dispatcher.py`
  **Spec scenarios**: vendor-ux.1.2 (prompt construction), vendor-ux.1.4 (equal weight)
  **Design decisions**: D2 (prompt in dispatcher)
  **Dependencies**: 1.1, 1.2

- [ ] 1.4 Add `--adversarial` flag to `parallel-review-plan` and `parallel-review-implementation` skills
  **Spec scenarios**: vendor-ux.1.5 (skill integration)
  **Dependencies**: 1.3

- [ ] 1.5 Add `--adversarial-ratio` support to dispatch orchestration
  **Spec scenarios**: vendor-ux.1.6 (mixed-mode dispatch)
  **Dependencies**: 1.3

## Phase 2: Micro-Task Quick Dispatch

- [ ] 2.1 Write tests for quick-task vendor selection, dispatch, and output handling
  **Spec scenarios**: vendor-ux.2.3 (vendor selection), vendor-ux.2.5 (output format), vendor-ux.2.6 (complexity warning), vendor-ux.2.7 (timeout)
  **Design decisions**: D3 (quick dispatch_mode), D4 (freeform output)
  **Dependencies**: None

- [ ] 2.2 Add `quick` dispatch_mode to `agents.yaml` for all vendors
  **Spec scenarios**: vendor-ux.2.4 (dispatch mode)
  **Design decisions**: D3 (quick mode)
  **Dependencies**: 2.1

- [ ] 2.3 Create `/quick-task` skill (SKILL.md + scripts/quick_task.py)
  **Spec scenarios**: vendor-ux.2.1 (skill definition), vendor-ux.2.2 (no artifacts), vendor-ux.2.3 (vendor selection), vendor-ux.2.5 (output), vendor-ux.2.6 (complexity warning), vendor-ux.2.7 (timeout)
  **Design decisions**: D3, D4
  **Dependencies**: 2.1, 2.2

## Phase 3: Vendor Health Check

- [ ] 3.1 Write tests for vendor health checking (CLI presence, API key resolution, probe logic)
  **Spec scenarios**: vendor-ux.3.2 (health dimensions), vendor-ux.3.3 (output format), vendor-ux.3.7 (no inference probes)
  **Design decisions**: D5 (dual-use script), D6 (no inference)
  **Dependencies**: None

- [ ] 3.2 Create `vendor_health.py` script with `check_all_vendors()` and CLI interface
  **Spec scenarios**: vendor-ux.3.1 (CLI script), vendor-ux.3.2 (dimensions), vendor-ux.3.3 (output format), vendor-ux.3.7 (probe cost)
  **Design decisions**: D5 (standalone + importable), D6 (lightweight probes)
  **Dependencies**: 3.1

- [ ] 3.3 Create `/vendor:status` skill wrapper (SKILL.md)
  **Spec scenarios**: vendor-ux.3.4 (skill wrapper)
  **Dependencies**: 3.2

- [ ] 3.4 Write tests for watchdog vendor health integration
  **Spec scenarios**: vendor-ux.3.5 (watchdog method), vendor-ux.3.6 (event channel), vendor-ux.3.8 (configurable interval)
  **Design decisions**: D7 (coordinator_agent channel)
  **Dependencies**: 3.2

- [ ] 3.5 Add `_check_vendor_health()` to `WatchdogService` with event emission
  **Spec scenarios**: vendor-ux.3.5 (watchdog integration), vendor-ux.3.6 (event channel), vendor-ux.3.8 (interval)
  **Design decisions**: D7 (existing channel)
  **Dependencies**: 3.2, 3.4

## Phase 4: Integration

- [ ] 4.1 End-to-end test: adversarial review dispatch with consensus synthesis
  **Dependencies**: 1.3, 1.4, 1.5

- [ ] 4.2 End-to-end test: quick-task dispatch and result display
  **Dependencies**: 2.3

- [ ] 4.3 End-to-end test: vendor health check CLI + watchdog event emission
  **Dependencies**: 3.2, 3.5

- [ ] 4.4 Update docs/lessons-learned.md with vendor UX patterns
  **Dependencies**: 4.1, 4.2, 4.3

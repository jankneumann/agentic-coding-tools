# Tasks: wire-supervise-execution-through-the-dispatch-fn-seam

All tasks are XS, S, or M. None are L or XL. Test tasks precede the implementation they verify.

## 0. Freeze the dispatch boundary

- [x] 0.1 Write schema tests for supervised dispatch fixtures (S)
  **Spec scenarios**: roadmap-orchestration.3a (success exact-match evidence), roadmap-orchestration.3b (stale result), roadmap-orchestration.3c (parked result), roadmap-orchestration.4a-4e (attempt, claimed/acknowledged/entered, and quarantine invariants), supervise.3c (bounded sanitized context), skill-workflow.1a-1b (bounded result)
  **Contracts**: `contracts/schemas/bounded-dispatch-context.schema.json`, `contracts/schemas/supervised-dispatch-request.schema.json`, `contracts/schemas/supervised-dispatch-result.schema.json`, `contracts/schemas/delegated-dispatch-attempt.schema.json`
  **Design decisions**: D2, D6, D7
  **Dependencies**: None
  **Files**: `skills/tests/supervise/test_execution_contract.py`, `skills/tests/supervise/fixtures/execution/contracts/**`

- [x] 0.2 Freeze dispatch schemas (S)
  **Dependencies**: 0.1
  **Files**: `openspec/changes/wire-supervise-execution-through-the-dispatch-fn-seam/contracts/**`

- [x] 0.3 Write delegated-attempt checkpoint tests (S)
  **Spec scenarios**: roadmap-orchestration.4a (persist prepared batch), roadmap-orchestration.4b (resume unresolved attempt)
  **Contracts**: `openspec/schemas/checkpoint.schema.json`, `contracts/schemas/delegated-dispatch-attempt.schema.json`
  **Design decisions**: D4, D6
  **Dependencies**: 0.2
  **Files**: `skills/tests/roadmap-runtime/test_delegated_checkpoint.py`

- [x] 0.4 Extend the checkpoint attempt ledger (M)
  **Dependencies**: 0.3
  **Files**: `skills/roadmap-runtime/scripts/models.py`, `skills/roadmap-runtime/scripts/checkpoint.py`, `openspec/schemas/checkpoint.schema.json`, `skills/roadmap-runtime/install_assets/openspec/schemas/checkpoint.schema.json`

- [x] Checkpoint: run schema plus checkpoint tests; review the cumulative diff; verify backward-compatible loading

## 1. Select safe execution batches

- [x] 1.1 Write the batch-selection scope-boundary test matrix (S)
  **Spec scenarios**: roadmap-orchestration.2a (fan out disjoint items), roadmap-orchestration.2b (serialize indeterminate items), roadmap-orchestration.2c (serialize ambiguous globs and integration writes)
  **Contracts**: `contracts/schemas/supervised-dispatch-request.schema.json`
  **Design decisions**: D3
  **Dependencies**: 0.2
  **Files**: `skills/tests/roadmap-runtime/test_dispatch_scheduler.py`, `skills/tests/roadmap-runtime/fixtures/dispatch-scopes/**`

- [x] 1.2 Implement the neutral dispatch scheduler (M)
  **Dependencies**: 0.4, 1.1
  **Files**: `skills/roadmap-runtime/scripts/dispatch_scheduler.py`

- [x] Checkpoint: run contract plus batch-selection tests; review the cumulative diff; verify package scope

## 2. Delegate item lifecycles through the callback

- [x] 2.1 Write delegated-lifecycle characterization tests (M)
  **Spec scenarios**: roadmap-orchestration.1a (delegated generation), roadmap-orchestration.1b (non-dispatched invalid ID), roadmap-orchestration.3a (apply exact-match result), roadmap-orchestration.3b (reject mismatch), roadmap-orchestration.3c (park pending gate)
  **Contracts**: `contracts/schemas/supervised-dispatch-request.schema.json`, `contracts/schemas/supervised-dispatch-result.schema.json`
  **Design decisions**: D1, D2, D6
  **Dependencies**: 0.2
  **Files**: `skills/tests/autopilot-roadmap/test_supervised_dispatch.py`, `skills/tests/autopilot-roadmap/test_orchestrator.py`

- [x] 2.2 Extend the roadmap orchestrator with opt-in delegated batches (M)
  **Dependencies**: 1.2, 2.1
  **Files**: `skills/autopilot-roadmap/scripts/orchestrator.py`, `skills/autopilot-roadmap/SKILL.md`

- [x] Checkpoint: run roadmap-orchestration tests; review the cumulative diff; verify legacy behavior

## 3. Build the leased host adapter

- [x] 3.1 Write host-adapter lifecycle tests (M)
  **Spec scenarios**: roadmap-orchestration.4a (persist prepared), roadmap-orchestration.4b (resume unresolved), roadmap-orchestration.4c (lease crash-window reconciliation), roadmap-orchestration.4d (authorized parked continuation), roadmap-orchestration.4e (unknown-liveness quarantine), roadmap-orchestration.3a (exact isolation evidence), roadmap-orchestration.3b (reject mismatches), supervise.2b (preflight isolation failure), supervise.2c (parked result), supervise.3c (reject unsafe context)
  **Contracts**: `contracts/schemas/supervised-dispatch-request.schema.json`, `contracts/schemas/supervised-dispatch-result.schema.json`, `contracts/schemas/delegated-dispatch-attempt.schema.json`
  **Design decisions**: D4, D5, D6, D8
  **Dependencies**: 0.4, 1.2, 2.2
  **Files**: `skills/tests/supervise/test_execution.py`, `skills/tests/supervise/fixtures/execution/lifecycle/**`

- [ ] 3.2 Implement the host prepare/launch/heartbeat/resume/apply adapter (M)
  **Dependencies**: 3.1
  **Files**: `skills/supervise/scripts/execution.py`

- [ ] Checkpoint: run launch-window, ack/go, marker collision, stale-takeover, quarantine, parked-resume, exact-evidence, and context-sanitizer tests

## 4. Wire the supervisor host protocol

- [ ] 4.1 Write supervisor host workflow tests (S)
  **Spec scenarios**: supervise.1a (approved execution), supervise.1b (unapproved refusal), supervise.2a (parallel isolation), supervise.2b (isolation failure), supervise.2c (park pending gate), supervise.3a (router pass-through), supervise.3b (router fallback), skill-workflow.1a (outcome boundary), skill-workflow.1b (failure boundary)
  **Contracts**: `contracts/schemas/supervised-dispatch-request.schema.json`, `contracts/schemas/supervised-dispatch-result.schema.json`
  **Design decisions**: D4, D5, D7
  **Dependencies**: 3.2
  **Files**: `skills/tests/supervise/test_workflow_contract.py`

- [ ] 4.2 Document the `/supervise execute` background callback protocol (M)
  **Dependencies**: 4.1
  **Files**: `skills/supervise/SKILL.md`

- [ ] Checkpoint: run supervise tests; inspect host-assisted invariants; verify source-only skill scope

## 5. Prove the end-to-end boundary

- [ ] 5.1 Write the parent-session supervised-dispatch integration test (M)
  **Spec scenarios**: roadmap-orchestration.2a (concurrent batch), roadmap-orchestration.2b (serialized overlap), supervise.2a (distinct worktrees), skill-workflow.1a (no transcript field), skill-workflow.1c (inspect captured parent session and durable outputs)
  **Contracts**: `contracts/schemas/supervised-dispatch-request.schema.json`, `contracts/schemas/supervised-dispatch-result.schema.json`
  **Design decisions**: D3, D4, D5, D6, D7
  **Dependencies**: 3.2, 4.2
  **Files**: `skills/tests/autopilot-roadmap/test_supervised_dispatch_e2e.py`, `skills/tests/autopilot-roadmap/fixtures/supervised-dispatch/**`

- [ ] 5.2 Synchronize runtime skill mirrors; run the full feature gates (S)
  **Dependencies**: 5.1
  **Files**: `.agents/skills/autopilot-roadmap/**`, `.agents/skills/supervise/**`, `.agents/skills/roadmap-runtime/**`, `.claude/skills/autopilot-roadmap/**`, `.claude/skills/supervise/**`, `.claude/skills/roadmap-runtime/**`

- [ ] Checkpoint: run both skill suites; run strict OpenSpec, package, scope, runtime-mirror checks

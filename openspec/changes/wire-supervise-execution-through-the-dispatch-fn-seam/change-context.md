# Change Context: wire-supervise-execution-through-the-dispatch-fn-seam

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| roadmap-orchestration.1 | `specs/roadmap-orchestration/spec.md` | Delegated Autopilot Item Lifecycle | --- | D1, D2 | `skills/autopilot-roadmap/scripts/orchestrator.py`; `skills/autopilot-roadmap/SKILL.md` | `skills/tests/autopilot-roadmap/test_supervised_dispatch.py`; `skills/tests/autopilot-roadmap/test_orchestrator.py` | pass 3b5a1fb0 (370-test validation suite) |
| roadmap-orchestration.2 | `specs/roadmap-orchestration/spec.md` | Scope-Safe Ready Batches | --- | D3 | `skills/roadmap-runtime/scripts/dispatch_scheduler.py`; `skills/autopilot-roadmap/scripts/orchestrator.py` | `skills/tests/roadmap-runtime/test_dispatch_scheduler.py`; `skills/tests/autopilot-roadmap/test_supervised_dispatch_e2e.py` | fail 3b5a1fb0 (deferred overlapping peer later carries proven_disjoint) |
| roadmap-orchestration.3 | `specs/roadmap-orchestration/spec.md` | Outcome-Only Resume Contract | --- | D2, D6, D7, D8 | `skills/autopilot-roadmap/scripts/orchestrator.py`; `skills/supervise/scripts/execution.py` | `skills/tests/autopilot-roadmap/test_supervised_dispatch.py`; `skills/tests/supervise/test_execution.py` | pass 3b5a1fb0 (370-test validation suite) |
| roadmap-orchestration.4 | `specs/roadmap-orchestration/spec.md` | Durable Delegated Attempt Ledger | --- | D4, D6, D8 | `skills/roadmap-runtime/scripts/models.py`; `skills/roadmap-runtime/scripts/checkpoint.py`; `openspec/schemas/checkpoint.schema.json`; `skills/supervise/scripts/execution.py` | `skills/tests/roadmap-runtime/test_delegated_checkpoint.py`; `skills/tests/supervise/test_execution.py` | pass 3b5a1fb0 (370-test validation suite) |
| supervise.1 | `specs/supervise/spec.md` | Approved Roadmap Execution | --- | D1, D4 | `skills/supervise/SKILL.md`; `skills/supervise/scripts/execution.py` | `skills/tests/supervise/test_workflow_contract.py` | pass 3b5a1fb0 (370-test validation suite) |
| supervise.2 | `specs/supervise/spec.md` | Background Worktree Isolation | --- | D4, D5, D7, D8 | `skills/supervise/scripts/execution.py`; `skills/roadmap-runtime/scripts/dispatch_scheduler.py` | `skills/tests/supervise/test_execution.py`; `skills/tests/autopilot-roadmap/test_supervised_dispatch_e2e.py` | pass 3b5a1fb0 (370-test validation suite) |
| supervise.3 | `specs/supervise/spec.md` | Router-Neutral Supervisor Dispatch | --- | D2, D6 | `skills/supervise/SKILL.md`; `skills/supervise/scripts/execution.py`; `skills/autopilot-roadmap/scripts/orchestrator.py` | `skills/tests/supervise/test_execution.py`; `skills/tests/supervise/test_workflow_contract.py` | pass 3b5a1fb0 (370-test validation suite) |
| skill-workflow.1 | `specs/skill-workflow/spec.md` | Supervised Background Dispatch Boundary | --- | D4, D6, D7 | `openspec/changes/wire-supervise-execution-through-the-dispatch-fn-seam/contracts/schemas/supervised-dispatch-request.schema.json`; `openspec/changes/wire-supervise-execution-through-the-dispatch-fn-seam/contracts/schemas/delegated-dispatch-attempt.schema.json`; `skills/supervise/SKILL.md`; `skills/supervise/scripts/execution.py` | `skills/tests/supervise/test_execution_contract.py`; `skills/tests/autopilot-roadmap/test_supervised_dispatch_e2e.py` | pass 3b5a1fb0 (370-test validation suite) |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Keep Autopilot as the sole per-change phase owner. | Separate opt-in `prepare_delegated_batch` / `apply_delegated_batch` entry points reuse the callback normalization seam. | Avoids competing phase machines while preserving unchanged legacy `execute_roadmap()` behavior. |
| D2 | Preserve the established callback seam and router context. | Additive typed context and strict supervised result contracts. | Maintains the One-Version Rule and router neutrality. |
| D3 | Admit concurrency only with affirmative scope evidence. | Deterministic tri-state scope classifier and maximal safe batch selection. | Fails closed for missing, boundless, or ambiguous scope. |
| D4 | Make suspension and launch ownership durable. | Two-stage prepare/apply API with generation-specific acknowledgement/go barrier. | Closes launch crash windows without provider calls in deterministic code. |
| D5 | Prevent children from sharing supervisor state. | Verify exact managed worktree path and branch before dispatch. | Makes write isolation an enforced precondition. |
| D6 | Make outcomes bounded, correlated, and idempotent. | Strict dispatch-attempt ledger, durable application journal, and canonical committed loop-state evidence. | Supports safe resume without retaining transcripts or replaying callbacks. |
| D7 | Exclude transcripts structurally. | Closed request/result schemas, bounded context sanitizer, and sentinel scans. | Prevents unbounded provider-specific content from entering parent state. |
| D8 | Preserve waiting as a non-failure state. | Parked continuation reuses attempt identity under a new lease generation; uncertainty quarantines. | Separates approval waiting from failures and unsafe takeover. |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|
| C3-SCHED-1 | wp-scheduler | correctness | high | fixed | Reject schema-invalid scope-shaped work packages before concurrency classification. |
| C3-ORCH-1 | wp-orchestrator | correctness | high | fixed | Validate exact batch identity and membership without an active-change schema dependency; preserve router-owned context and reject boolean versions. |
| C3-HOST-1 | wp-host-adapter | resilience | high | fixed | Enforce generation-specific claim/ack/go ownership, exact realpath evidence, bounded context, and positive-death-only takeover. |
| C3-SUP-1 | wp-supervise | compatibility | high | fixed | Reconciled supervisor versus deterministic state ownership and documented outcome-only successful handoff requirements. |
| C3-INT-1 | wp-integration | behavioral_failure | high | fixed | Populate real child-only transcripts with unique sentinels and prove exclusion from parent events, temp results, checkpoint context, supervisor records, handoffs, and durable files. |
| RI-1 | whole branch | resilience | critical | fixed | Hardened linked-worktree marker ownership, checkpoint locking/atomic persistence, crash recovery, continuation takeover, canonical evidence, scheduler semantics, and per-item failure isolation; see `impl-findings.md`. |

## Coverage Summary

- **Requirements traced**: 8/8
- **Tests mapped**: 8 requirements have at least one planned test
- **Evidence collected**: 7/8 requirements have pass evidence at validated commit `3b5a1fb0`; 370 focused validation tests passed
- **Gaps identified**: roadmap-orchestration.2 fails because the second request affected by overlap later carries `proven_disjoint` instead of `serial_indeterminate`
- **Deferred items**: ---

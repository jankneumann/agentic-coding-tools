# Change Context: wire-supervise-execution-through-the-dispatch-fn-seam

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| roadmap-orchestration.1 | `specs/roadmap-orchestration/spec.md` | Delegated Autopilot Item Lifecycle | --- | D1, D2 | --- | `skills/tests/autopilot-roadmap/test_supervised_dispatch.py`; `skills/tests/autopilot-roadmap/test_orchestrator.py` | --- |
| roadmap-orchestration.2 | `specs/roadmap-orchestration/spec.md` | Scope-Safe Ready Batches | --- | D3 | --- | `skills/tests/roadmap-runtime/test_dispatch_scheduler.py`; `skills/tests/autopilot-roadmap/test_supervised_dispatch_e2e.py` | --- |
| roadmap-orchestration.3 | `specs/roadmap-orchestration/spec.md` | Outcome-Only Resume Contract | --- | D2, D6, D7, D8 | --- | `skills/tests/autopilot-roadmap/test_supervised_dispatch.py`; `skills/tests/supervise/test_execution.py` | --- |
| roadmap-orchestration.4 | `specs/roadmap-orchestration/spec.md` | Durable Delegated Attempt Ledger | --- | D4, D6, D8 | --- | `skills/tests/roadmap-runtime/test_delegated_checkpoint.py`; `skills/tests/supervise/test_execution.py` | --- |
| supervise.1 | `specs/supervise/spec.md` | Approved Roadmap Execution | --- | D1, D4 | --- | `skills/tests/supervise/test_workflow_contract.py` | --- |
| supervise.2 | `specs/supervise/spec.md` | Background Worktree Isolation | --- | D4, D5, D7, D8 | --- | `skills/tests/supervise/test_execution.py`; `skills/tests/autopilot-roadmap/test_supervised_dispatch_e2e.py` | --- |
| supervise.3 | `specs/supervise/spec.md` | Router-Neutral Supervisor Dispatch | --- | D2, D6 | --- | `skills/tests/supervise/test_execution.py`; `skills/tests/supervise/test_workflow_contract.py` | --- |
| skill-workflow.1 | `specs/skill-workflow/spec.md` | Supervised Background Dispatch Boundary | --- | D4, D6, D7 | --- | `skills/tests/supervise/test_execution_contract.py`; `skills/tests/autopilot-roadmap/test_supervised_dispatch_e2e.py` | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Keep Autopilot as the sole per-change phase owner. | Opt-in delegated item lifecycle in the roadmap orchestrator. | Avoids competing phase machines while preserving legacy execution. |
| D2 | Preserve the established callback seam and router context. | Additive typed context and strict supervised result contracts. | Maintains the One-Version Rule and router neutrality. |
| D3 | Admit concurrency only with affirmative scope evidence. | Deterministic tri-state scope classifier and maximal safe batch selection. | Fails closed for missing, boundless, or ambiguous scope. |
| D4 | Make suspension and launch ownership durable. | Two-stage prepare/apply API with generation-specific acknowledgement/go barrier. | Closes launch crash windows without provider calls in deterministic code. |
| D5 | Prevent children from sharing supervisor state. | Verify exact managed worktree path and branch before dispatch. | Makes write isolation an enforced precondition. |
| D6 | Make outcomes bounded, correlated, and idempotent. | Additive dispatch-attempt ledger and exact-evidence result application. | Supports safe resume without retaining transcripts. |
| D7 | Exclude transcripts structurally. | Closed request/result schemas, bounded context sanitizer, and sentinel scans. | Prevents unbounded provider-specific content from entering parent state. |
| D8 | Preserve waiting as a non-failure state. | Parked continuation reuses attempt identity under a new lease generation; uncertainty quarantines. | Separates approval waiting from failures and unsafe takeover. |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

## Coverage Summary

- **Requirements traced**: 8/8
- **Tests mapped**: 8 requirements have at least one planned test
- **Evidence collected**: 0/8 requirements have pass/fail evidence
- **Gaps identified**: Implementation and validation evidence pending
- **Deferred items**: ---

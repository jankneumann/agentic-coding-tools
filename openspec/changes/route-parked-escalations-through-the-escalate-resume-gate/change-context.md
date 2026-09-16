# Change Context: route-parked-escalations-through-the-escalate-resume-gate

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|-------------|-------------|--------------|-----------------|---------------|---------|----------|
| supervise.1 | specs/supervise/spec.md | Immediate Policy-Pause Escalation Has One Authoritative Commit | contracts/README.md; openspec/schemas/gate-decision.schema.json; openspec/schemas/checkpoint.schema.json | D1, D2, D3 | skills/roadmap-runtime/scripts/checkpoint.py; skills/supervise/scripts/execution.py; skills/supervise/scripts/gate_router.py | skills/tests/roadmap-runtime/test_checkpoint_replan.py; skills/tests/supervise/test_execution.py; skills/tests/supervise/test_gate_router.py | pass f8e2193f |
| supervise.2 | specs/supervise/spec.md | Escalate Resume Correlation Is Generation-Safe and Sanitized | contracts/README.md; openspec/schemas/gate-decision.schema.json | D3, D4, D5 | skills/supervise/scripts/cycle_state.py; skills/supervise/scripts/execution.py; skills/supervise/scripts/gate_router.py; skills/supervise/SKILL.md | skills/tests/supervise/test_cycle_state.py; skills/tests/supervise/test_execution.py; skills/tests/supervise/test_gate_router.py; skills/tests/supervise/test_prose_free_gates.py | pass f8e2193f |
| supervise.3 | specs/supervise/spec.md | Supervise Gate Routing uses generation-aware resume authorization | contracts/README.md; openspec/schemas/gate-decision.schema.json | D3, D4 | skills/supervise/scripts/cycle_state.py; skills/supervise/scripts/gate_router.py | skills/tests/supervise/test_cycle_state.py; skills/tests/supervise/test_gate_router.py | pass f8e2193f |
| roadmap-orchestration.1 | specs/roadmap-orchestration/spec.md | Delegated Batch Apply Admits the Current Unapplied Cohort | contracts/README.md; openspec/schemas/checkpoint.schema.json | D2, D6 | skills/autopilot-roadmap/scripts/orchestrator.py; skills/roadmap-runtime/scripts/checkpoint.py; skills/roadmap-runtime/scripts/models.py | skills/tests/autopilot-roadmap/test_supervised_dispatch.py; skills/tests/roadmap-runtime/test_delegated_checkpoint.py | pass f8e2193f |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Route only after complete batch application. | route_parked_escalations checks terminal effects_applied journals before evaluation or resume. | Prevents partial application from creating a second authority path or replaying callbacks. |
| D2 | Use one shared checkpoint transaction as the authority boundary. | Roadmap runtime checkpoint transactions serialize state and gate decisions in one atomic payload. | Prevents stale snapshot overwrite and split-brain decision sidecars. |
| D3 | Lock by subject and fresh-check before committing. | Automatic and manual routing share generation-scoped locking, current-state validation, and atomic decision-plus-resume. | Makes races deterministic while keeping approval I/O outside the workspace transaction. |
| D4 | Correlate escalation identity to lease generation while retaining legacy safety. | Decision lookup, answer selection, approval refs, and mirror retirement bind to the parked generation. | Rejects stale approval references without duplicating matching legacy decisions. |
| D5 | Sanitize policy-pause context at the shared seam. | Automatic and manual paths emit the same six allowlisted fields and fixed retry reason. | Prevents child text and raw approval content from entering durable authority artifacts. |
| D6 | Derive required apply membership from current journal state. | Delegated apply admits exactly current attempts not yet at effects_applied. | Allows resumed members to complete without historical peers while preserving at-most-once effects. |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|
| implementation-review | wp-authority-recovery | correctness and resilience | high | fixed | Generation selection, current-attempt correlation, legacy reuse, and fixed context were repaired in 1208e0f5, 86e837be, and 0a7b7fa3. |
| validation-1 | wp-authority-recovery | spec/evidence drift | critical | fixed | Tasks, API/architecture context impact, and the canonical package result were reconciled by f8e2193f. |
| validation-1-import-isolation | wp-authority-recovery | behavioral failure | high | fixed | Coherent flat-module restoration and a regression guard close the order-dependent suite failure. |

## Coverage Summary

- **Requirements traced**: 4/4
- **Scenarios verified**: 14/14 through the mapped behavioral suites
- **Tests mapped**: 4/4 requirements have behavioral tests
- **Evidence collected**: 4/4 requirements have passing evidence at validated commit f8e2193f; the complete skills suite passed with 6,310 tests and 6 skips
- **Contract traceability gate**: pass; the change-scoped gate exited 0
- **Gaps identified**: none
- **Deferred items**: none

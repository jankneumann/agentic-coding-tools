# Change Context: route-parked-escalations-through-the-escalate-resume-gate

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|-------------|-------------|--------------|-----------------|---------------|---------|----------|
| supervise.1 | specs/supervise/spec.md | Immediate Policy-Pause Escalation Has One Authoritative Commit | contracts/README.md; openspec/schemas/gate-decision.schema.json; openspec/schemas/checkpoint.schema.json | D1, D2, D3 | skills/roadmap-runtime/scripts/checkpoint.py; skills/supervise/scripts/execution.py; skills/supervise/scripts/gate_router.py | skills/tests/supervise/test_execution.py; skills/tests/supervise/test_gate_router.py; skills/tests/roadmap-runtime/test_checkpoint_replan.py | pass 3e1293d9 |
| supervise.2 | specs/supervise/spec.md | Escalate Resume Correlation Is Generation-Safe and Sanitized | contracts/README.md; openspec/schemas/gate-decision.schema.json | D3, D4, D5 | skills/supervise/scripts/cycle_state.py; skills/supervise/scripts/execution.py; skills/supervise/scripts/gate_router.py; skills/supervise/SKILL.md | skills/tests/supervise/test_execution.py; skills/tests/supervise/test_gate_router.py | pass 3e1293d9 |
| supervise.3 | specs/supervise/spec.md | Supervise Gate Routing uses generation-aware resume authorization | contracts/README.md; openspec/schemas/gate-decision.schema.json | D3, D4 | skills/supervise/scripts/cycle_state.py; skills/supervise/scripts/gate_router.py | skills/tests/supervise/test_cycle_state.py; skills/tests/supervise/test_gate_router.py | pass 3e1293d9 |
| roadmap-orchestration.1 | specs/roadmap-orchestration/spec.md | Delegated Batch Apply Admits the Current Unapplied Cohort | contracts/README.md; openspec/schemas/checkpoint.schema.json | D2, D6 | skills/autopilot-roadmap/scripts/orchestrator.py; skills/roadmap-runtime/scripts/checkpoint.py; skills/roadmap-runtime/scripts/models.py | skills/tests/autopilot-roadmap/test_supervised_dispatch.py; skills/tests/roadmap-runtime/test_delegated_checkpoint.py | pass 3e1293d9 |

## Scenario Evidence

| Scenario | Behavioral evidence |
|---|---|
| Complete batch routes exactly once | `test_route_parked_escalations_returns_exact_proceed_resolution_once`; `test_route_parked_escalations_returns_exact_blocked_resolution_once`; `test_route_parked_escalations_retry_reports_durable_already_routed_state` |
| Partial batch cannot route | `test_route_parked_escalations_rejects_partial_batch_before_gate_evaluation` |
| Approval wait preserves concurrent authority | `TestCheckpointGateDecisionLedger::test_gate_decision_append_preserves_a_concurrent_checkpoint_transition`; `TestCheckpointTransaction::test_transaction_reloads_current_state_and_commits_one_payload` |
| Stale and concurrent routing are safe | `test_stale_atomic_escalation_candidate_does_not_append_a_decision`; `test_automatic_and_manual_resolution_race_commits_one_proceed`; `test_concurrent_blocked_subjects_preserve_both_mirror_entries` |
| Legacy and later generations remain distinct | `test_escalate_resume_answer_binds_legacy_block_to_current_parked_generation`; `test_escalate_resume_legacy_block_does_not_authorize_a_later_repark` |
| Manual and automatic context are identical | `TestResolveParked::test_policy_pause_uses_the_fixed_sanitized_retry_reason`; `test_escalate_resume_manual_answer_uses_the_fixed_policy_pause_context` |
| Answer selects a generation safely | `test_escalate_resume_answer_selects_the_newest_current_parked_attempt`; `test_escalate_resume_answer_refuses_an_older_parked_attempt_generation` |
| Authoritative decision repairs a failed mirror projection | `test_rehydrate_restores_blocked_escalation_after_mirror_projection_failure` |
| Proceed clears the prior generation journal atomically | `test_atomic_escalation_resume_publishes_decision_and_generation_together`; route proceed/retry tests above |
| Resume rejects a generation-blind stale reference | `test_escalate_resume_approval_ref_rejects_a_prior_generation` |
| Initial batch remains exact | `test_apply_binds_out_of_order_results_and_dispatches_once_with_router_context`; `test_apply_rejects_missing_current_result_before_callback` |
| Resumed member applies without historical peer | `test_apply_accepts_resumed_current_generation_with_applied_peer_omitted` |
| Historical and stale results fail closed | `test_apply_rejects_historical_result_for_effects_applied_peer_before_callback`; `test_apply_rejects_inexact_multiple_resumed_cohort_before_callback` |
| Multiple resumed members form the exact current cohort | `test_apply_requires_all_resumed_members_regardless_of_submission_order`; `test_apply_rejects_inexact_multiple_resumed_cohort_before_callback` |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Route only after complete batch application. | The route guard admits effects-applied members and durable already-routed policy-pause continuations only. | Preserves retry visibility without restoring the cleared generation-G journal. |
| D2 | Use one shared checkpoint transaction as the authority boundary. | Roadmap runtime checkpoint transactions serialize state and gate decisions in one atomic payload. | Prevents stale snapshot overwrite and split-brain decision sidecars. |
| D3 | Lock by subject and fresh-check before committing. | Automatic/manual routing share generation locks; mirror read-merge-write has its own process-safe projection lock. | Makes authority and derived projection races deterministic without holding workspace locks across approval I/O. |
| D4 | Correlate escalation identity to lease generation while retaining legacy safety. | Decision lookup, answer selection, approval refs, bounded output, and mirror retirement bind to the parked generation. | Rejects stale references while preserving legacy reuse. |
| D5 | Sanitize policy-pause context and output. | Requests use six allowlisted fields; route returns only exact bounded resolution keys. | Prevents child or approval payload leakage. |
| D6 | Derive required apply membership from current journal state. | Delegated apply admits exactly current attempts not yet at effects_applied. | Supports one or multiple resumed members without replaying historical peers. |

## Review Findings Summary

| Finding | Disposition | Resolution |
|---|---|---|
| Bounded route return contract and unreachable retry state | fixed | Exact proceed, blocked, and already-routed objects are pinned; retry resolves its decided generation from the durable approval reference. |
| Behavioral evidence and scenario traceability | fixed | All 14 retained scenarios now map to named behavioral tests; focused package suites pass 620 tests. |
| Ledger-to-mirror rehydrate reconciliation | fixed | Injected projection failure leaves checkpoint authority durable and rehydrate restores the normalized pending gate. |
| Architecture freshness wording | advisory qualified | The scoped artifact is preserved and digested, but its zero findings are not treated as coverage of skills/ because the canonical graph predates the branch and excludes that root. |

## Coverage Summary

- **Requirements traced**: 4/4
- **Scenarios verified**: 14/14 with named behavioral tests above
- **Focused package tests**: 620 passed
- **Full skills suite**: 6,319 passed, 6 skipped, 2 warnings
- **Validated implementation commit**: `3e1293d97a2db43314d6072c4d7fdb7329637223`
- **Gaps identified**: none in the retained delta scenarios
- **Deferred items**: architecture file-size findings remain advisory technical debt

# Change Context: harden-substantive-review-gates

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| review-convergence-safety.1 | specs/review-convergence-safety/spec.md | Reject placeholder-only terminal output | --- | D1 | `skills/parallel-infrastructure/scripts/review_dispatcher.py` | `test_nonempty_placeholder_is_unsuccessful`, `test_placeholder_wrapper_is_unsuccessful_after_grace_period`, `test_poll_placeholder_is_unsuccessful`, `test_dispatch_placeholder_is_unsuccessful` | --- |
| review-convergence-safety.2 | specs/review-convergence-safety/spec.md | Preserve concrete reviews | --- | D1 | `skills/parallel-infrastructure/scripts/review_dispatcher.py` | `test_substantive_finding_with_placeholder_context_succeeds` | --- |
| review-convergence-safety.3 | specs/review-convergence-safety/spec.md | Escalate unconfirmed high-impact judgment | --- | D2 | `skills/parallel-infrastructure/scripts/review_ledger.py`, `skills/autopilot/scripts/convergence_loop.py` | `test_unconfirmed_high_impact_judgment_requires_adjudication` | --- |
| review-convergence-safety.4 | specs/review-convergence-safety/spec.md | Preserve medium advisory behavior | --- | D2 | `skills/parallel-infrastructure/scripts/review_ledger.py`, `skills/autopilot/scripts/convergence_loop.py` | `test_unconfirmed_medium_judgment_does_not_enter_fix_callback` | --- |
| review-convergence-safety.5 | specs/review-convergence-safety/spec.md | Preserve completed result across interruption | contracts/README.md | D3, D4 | `skills/parallel-infrastructure/scripts/checkpoint_findings.py`, `skills/autopilot/scripts/convergence_loop.py` | `test_completed_vendor_is_recoverable_when_panel_is_interrupted` | --- |
| review-convergence-safety.6 | specs/review-convergence-safety/spec.md | Do not emit async submissions as terminal | contracts/README.md | D3 | `skills/parallel-infrastructure/scripts/review_dispatcher.py` | `test_result_callback_waits_for_async_poll` | --- |
| review-convergence-safety.7 | specs/review-convergence-safety/spec.md | Preserve ordered return with prompt callbacks | contracts/README.md | D3 | `skills/parallel-infrastructure/scripts/review_dispatcher.py` | `test_result_callback_fires_in_completion_order`, `test_async_poll_starts_before_slow_sync_finishes` | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Stop a demonstrated false-quorum response | `_is_placeholder_only_response` | Narrow, backward-compatible ingestion guard |
| D2 | Prevent high-risk uncertainty from becoming success or an automatic edit | `adjudication_items` and `adjudication_required` exit | Uses existing escalation surface |
| D3 | Close the post-return loss window | `result_callback` and `_checkpoint_result` | Optional callback preserves callers |
| D4 | Make every partial checkpoint recoverable | `_write_review_checkpoint` and atomic text writes | Existing manifest reader remains compatible |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

## Coverage Summary

- **Requirements traced**: 7/7
- **Tests mapped**: 7 requirements have at least one test
- **Evidence collected**: 0/7 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: ---

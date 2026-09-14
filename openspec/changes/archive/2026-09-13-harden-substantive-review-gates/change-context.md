# Change Context: harden-substantive-review-gates

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| review-convergence-safety.1 | specs/review-convergence-safety/spec.md | Reject placeholder-only terminal output | --- | D1 | `skills/parallel-infrastructure/scripts/review_dispatcher.py` | `test_nonempty_placeholder_is_unsuccessful`, `test_placeholder_wrapper_is_unsuccessful_after_grace_period`, `test_poll_placeholder_is_unsuccessful`, `test_dispatch_placeholder_is_unsuccessful`, `test_placeholder_does_not_trigger_schema_repair`, `test_poll_rejects_clean_findings_when_submission_runtime_is_fast` | pass 68a6c89e |
| review-convergence-safety.2 | specs/review-convergence-safety/spec.md | Preserve concrete reviews | --- | D1 | `skills/parallel-infrastructure/scripts/review_dispatcher.py` | `test_substantive_finding_with_placeholder_context_succeeds`, `test_real_finding_starting_with_review_pending_succeeds`, `test_poll_accepts_clean_findings_when_remote_runtime_is_unknown` | pass 68a6c89e |
| review-convergence-safety.3 | specs/review-convergence-safety/spec.md | Escalate unconfirmed high-impact judgment | --- | D2 | `skills/parallel-infrastructure/scripts/review_ledger.py`, `skills/autopilot/scripts/convergence_loop.py` | `test_unconfirmed_high_impact_judgment_requires_adjudication` | pass 68a6c89e |
| review-convergence-safety.4 | specs/review-convergence-safety/spec.md | Preserve medium advisory behavior | --- | D2 | `skills/parallel-infrastructure/scripts/review_ledger.py`, `skills/autopilot/scripts/convergence_loop.py` | `test_unconfirmed_medium_judgment_does_not_enter_fix_callback` | pass 68a6c89e |
| review-convergence-safety.5 | specs/review-convergence-safety/spec.md | Preserve completed result across interruption | contracts/README.md | D3, D4 | `skills/parallel-infrastructure/scripts/checkpoint_findings.py`, `skills/autopilot/scripts/convergence_loop.py` | `test_completed_vendor_is_recoverable_when_panel_is_interrupted` | pass 68a6c89e |
| review-convergence-safety.6 | specs/review-convergence-safety/spec.md | Do not emit async submissions as terminal | contracts/README.md | D3 | `skills/parallel-infrastructure/scripts/review_dispatcher.py` | `test_result_callback_waits_for_async_poll` | pass 68a6c89e |
| review-convergence-safety.7 | specs/review-convergence-safety/spec.md | Preserve ordered return with prompt callbacks | contracts/README.md | D3 | `skills/parallel-infrastructure/scripts/review_dispatcher.py` | `test_result_callback_fires_in_completion_order`, `test_async_poll_starts_before_slow_sync_finishes`, `test_async_poll_starts_without_waiting_for_slow_submit` | pass 68a6c89e |

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

| R1-async-checkpoint | whole branch | resilience | critical | fix | Polls begin before slow synchronous work completes and every terminal result checkpoints immediately. |
| R1-placeholder-paths | dispatcher | correctness | critical | fix | CLI, async polling, and SDK ingestion reject placeholder-only terminal responses without schema repair. |
| R2-clean-async | dispatcher | correctness | critical | fix | Unknown remote runtime no longer reuses poll-loop elapsed time to reject legitimate clean results. |
| R2-placeholder-evidence | dispatcher | observability | medium | fix | Rejected SDK placeholder payloads persist as raw review evidence. |
| R3-fast-empty | dispatcher | resilience | medium | fix | Production dispatch passes a submission-start timestamp, preserving the fast-empty guard while direct recovery polls remain runtime-neutral. |
| R3-sdk-raw | dispatcher | observability | low | fix | SDK parse failure no longer invents a literal `null` raw payload; placeholder checks use the persisted serialization. |
## Coverage Summary

- **Requirements traced**: 7/7
- **Tests mapped**: 7 requirements have at least one test
- **Evidence collected**: 7/7 requirements have passing evidence at `68a6c89e`
- **Gaps identified**: ---
- **Deferred items**: callback-exception cancellation and async model metadata are advisory follow-ups outside the demonstrated recovery failure.

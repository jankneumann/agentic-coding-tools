# Change Context: ledger-driven-review-convergence

<!-- 3-phase incremental artifact:
     Phase 1 (pre-implementation): Req ID, Spec Source, Description, Contract Ref, Design Decision,
       Test(s) planned. Files Changed = "---". Evidence = "---".
     Phase 2 (implementation): Files Changed populated. Tests pass (GREEN).
     Phase 3 (validation): Evidence filled with "pass <SHA>", "fail <SHA>", or "deferred <reason>". -->

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| skill-workflow.1 | specs/skill-workflow/spec.md — Gate-Time Review Ledger | Persist findings to `.review-ledger/ledger.json` with stable ids; merge on fingerprint or match_score | --- | D1, D8 | `skills/parallel-infrastructure/scripts/review_ledger.py`, `skills/autopilot/scripts/convergence_loop.py` | `test_review_ledger_schema.py`, `test_review_ledger.py` (same id, created on first round) | --- |
| skill-workflow.2 | specs/skill-workflow/spec.md — Compact Before New Hunt | Compact against HEAD: retire gone files / missing tokens; reopen addressed if tokens remain | --- | D2 | `skills/parallel-infrastructure/scripts/review_ledger.py`, `skills/autopilot/scripts/convergence_loop.py` | `test_review_ledger.py` (retired, reopens) | --- |
| skill-workflow.3 | specs/skill-workflow/spec.md — Delta Review After Round One | Round N>1 prompts include open items + last-fix diff; forbid reopening retired/parked | --- | D5 | `skills/autopilot/scripts/convergence_loop.py` | `test_convergence_loop.py` (round 2 prompt) | --- |
| skill-workflow.4 | specs/skill-workflow/spec.md — Parked Disagreement Does Not Abort | Park disagreements; continue agreed blocking; never `reason=disagreement` | --- | D4 | `skills/autopilot/scripts/convergence_loop.py` | `test_convergence_loop.py` (continues, leftovers) | --- |
| skill-workflow.5 | specs/skill-workflow/spec.md — Scoped Fix Cluster | fix_callback gets current blocking items and cited paths only; reject out-of-scope edits | --- | D7 | `skills/parallel-infrastructure/scripts/review_ledger.py`, `skills/autopilot/scripts/convergence_loop.py` | `test_convergence_loop.py` (scoped, rejected) | --- |
| skill-workflow.6 | specs/skill-workflow/spec.md — Review Convergence Loop | Compact + ledger merge; block only deterministic or confirmed high/critical open items; unconfirmed medium never blocks; PLAN_FIX is fix_callback | --- | D3, D6 | `skills/autopilot/scripts/convergence_loop.py`, `skills/autopilot/scripts/autopilot.py` | `test_convergence_loop.py`, `test_convergence_spiral_fixture.py` | --- |
| skill-workflow.7 | specs/skill-workflow/spec.md — Finding Trend Tracking and Stall Detection | Stall when post-compact blocking is not strictly decreasing; window of 2 | --- | D6 | `skills/autopilot/scripts/convergence_loop.py` | `test_convergence_loop.py` (decreasing, stalled) | --- |
| skill-workflow.8 | specs/skill-workflow/spec.md — Disagreement Classification | Disposition disagreement is consensus `disagreement` and ledger `parked` | --- | D4 | `skills/autopilot/scripts/convergence_loop.py`, `skills/parallel-infrastructure/scripts/review_ledger.py` | `test_convergence_loop.py` (parked) | --- |
| skill-workflow.9 | specs/skill-workflow/spec.md — Disagreement Findings Escalate | Park for humans; mid-loop does not abort | --- | D4 | `skills/autopilot/scripts/convergence_loop.py` | `test_convergence_loop.py` (parked leftovers) | --- |
| skill-workflow.10 | specs/skill-workflow/spec.md — State Machine Phases | PLAN_FIX/IMPL_FIX are phase_history sub-steps; no outer cold re-review bounce | --- | D6 | `skills/autopilot/scripts/autopilot.py`, `skills/autopilot/SKILL.md` | `test_autopilot.py` (one engine, resume) | --- |
| skill-workflow.11 | specs/skill-workflow/spec.md — Fix Dispatch | PLAN_FIX inline on cited paths; IMPL_FIX targeted to lead vendor ∩ write_allow ∩ file_path | --- | D7 | `skills/autopilot/scripts/autopilot.py`, `skills/autopilot/scripts/convergence_loop.py`, `skills/autopilot/SKILL.md` | `test_convergence_loop.py` (scoped) | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Local-first ledger next to the change | `review_ledger.py` load/save/merge at `.review-ledger/ledger.json` | Gate-time review must work with coordinator down |
| D2 | Compact is heuristic first | `compact()` retires missing files/tokens; reopens addressed if tokens remain | No extra LLM call in v1; ambient can replace later |
| D3 | Blocking set after compact | `is_blocking_item` / `blocking_items` after compact+merge | Aligns loop with integration-gate "unconfirmed warn only" |
| D4 | Disagreement parks, loop continues | `park_item` + `reviews/parked-disagreements.json`; no `reason=disagreement` | Agreed blocking work should not abort |
| D5 | Delta prompt for round N>1 | `build_review_prompt` attaches open items + last-fix diff | Stops cold re-review of the whole artifact |
| D6 | One engine — PLAN_FIX is fix_callback | `_phase_review` records PLAN_FIX/IMPL_FIX sub-steps; maps leftover non-convergence to `max_iter` | Nested PLAN_REVIEW↔PLAN_FIX was a second spiral |
| D7 | Scoped fix cluster | `scoped_fix_payload` + `check_fix_scope` | Unscoped fixes create new surfaces the next hunt attacks |
| D8 | Ledger is additive when missing | `load_or_create` warns and writes an empty ledger | Phase-1-only checkouts still run converge() |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

## Coverage Summary

- **Requirements traced**: 11/11
- **Tests mapped**: 11 requirements have at least one test
- **Evidence collected**: 0/11 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: ---

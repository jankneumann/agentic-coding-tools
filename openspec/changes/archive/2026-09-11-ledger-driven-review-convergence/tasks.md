# Tasks: ledger-driven-review-convergence

## 1. Contracts

- [x] 1.1 Write tests for ledger document validation
  **Spec scenarios**: skill-workflow Gate-Time Review Ledger (created on first round)
  **Contracts**: `contracts/review-ledger.schema.json`, `contracts/parked-disagreements.schema.json`
  **Design decisions**: D1
  **Dependencies**: None
  **Files**: `skills/tests/parallel-infrastructure/test_review_ledger_schema.py`

- [x] 1.2 Add gate-time ledger schemas
  **Dependencies**: 1.1
  **Files**: `openspec/changes/ledger-driven-review-convergence/contracts/**`

- [x] Checkpoint: run contract tests, review diff, verify scope

## 2. Ledger library

- [x] 2.1 Write tests for stable ids, fingerprint merge, compact heuristic, blocking set
  **Spec scenarios**: skill-workflow Gate-Time Review Ledger (same defect keeps id, created on first round); Compact Before New Hunt (retired, reopens); Review Convergence Loop (unconfirmed medium does not block)
  **Contracts**: `contracts/review-ledger.schema.json`
  **Design decisions**: D1, D2, D3
  **Dependencies**: 1.2
  **Files**: `skills/tests/parallel-infrastructure/test_review_ledger.py`

- [x] 2.2 Implement `review_ledger.py` (load, merge, compact, blocking set)
  **Dependencies**: 2.1
  **Files**: `skills/parallel-infrastructure/scripts/review_ledger.py`

- [x] Checkpoint: run ledger tests, review diff, verify scope

## 3. Convergence loop

- [x] 3.1 Write tests for delta prompts, parked disagreement, stall on non-decreasing blocking, scoped fix cluster
  **Spec scenarios**: skill-workflow Delta Review After Round One; Parked Disagreement Does Not Abort (continues, leftovers); Finding Trend Tracking (decreasing, stalled); Scoped Fix Cluster (scoped, rejected); Disagreement Classification; Disagreement Findings Escalate
  **Design decisions**: D4, D5, D7
  **Dependencies**: 2.2
  **Files**: `skills/tests/autopilot/test_convergence_loop.py`

- [x] 3.2 Wire ledger compact, delta prompts, blocking set, parked disagreement into `converge()`
  **Dependencies**: 3.1
  **Files**: `skills/autopilot/scripts/convergence_loop.py`

- [x] 3.3 Scope `fix_callback` payloads to cited paths
  **Dependencies**: 3.2
  **Files**: `skills/autopilot/scripts/convergence_loop.py`, `skills/autopilot/scripts/autopilot.py`

- [x] Checkpoint: run converge tests, review diff, verify scope

## 4. Autopilot one-engine

- [x] 4.1 Write tests that PLAN_REVIEW does not outer-bounce into a cold re-review
  **Spec scenarios**: skill-workflow State Machine Phases (one engine, resume)
  **Design decisions**: D6
  **Dependencies**: 3.3
  **Files**: `skills/autopilot/scripts/tests/test_autopilot.py`

- [x] 4.2 Record PLAN_FIX/IMPL_FIX as phase_history sub-steps inside `converge()`
  **Dependencies**: 4.1
  **Files**: `skills/autopilot/scripts/autopilot.py`, `skills/autopilot/SKILL.md`

- [x] Checkpoint: run autopilot tests, review diff, verify scope

## 5. Integration

- [x] 5.1 Add a seeded spiral fixture (round-1 extra medium unconfirmed, round-2 must not grow blocking)
  **Spec scenarios**: skill-workflow Review Convergence Loop (unconfirmed medium does not block); Finding Trend Tracking
  **Design decisions**: D3, D5
  **Dependencies**: 4.2
  **Files**: `skills/tests/autopilot/test_convergence_spiral_fixture.py`

- [x] 5.2 Validate the change with `openspec validate --strict` then the autopilot unit suite then the parallel-infrastructure unit suite
  **Dependencies**: 5.1
  **Files**: none

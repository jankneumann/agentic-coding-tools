# Tasks: harden-review-dispatch-parse-and-timeouts

## 1. Contracts

- [ ] 1.1 Write tests for coercion alias table loading
  **Spec scenarios**: skill-workflow Schema-Derived Review Prompt (helper/schema parity); Finding Coercion Before Validation (alias, completeness/testability, severity fill, unknown enum)
  **Contracts**: `contracts/finding-coercion.schema.json`, `contracts/dispatch-timeout-budget.schema.json`, `contracts/vendor-raw-output.schema.json`
  **Design decisions**: D1, D2, D4, D6
  **Dependencies**: None
  **Files**: `skills/tests/parallel-infrastructure/test_finding_coercion.py`

- [ ] 1.2 Add dispatch robustness contract schemas
  **Dependencies**: 1.1
  **Files**: `openspec/changes/harden-review-dispatch-parse-and-timeouts/contracts/**`

- [ ] Checkpoint: run contract schema tests, review diff, verify scope

## 2. Prompt helper and coercion

- [ ] 2.1 Write tests for `prompt_contract()` matching the canonical schema required fields
  **Spec scenarios**: skill-workflow Schema-Derived Review Prompt (converge prompt, skill helper)
  **Contracts**: `openspec/schemas/review-findings.schema.json`
  **Design decisions**: D1, D8
  **Dependencies**: 1.2
  **Files**: `skills/tests/parallel-infrastructure/test_review_findings_schema.py`

- [ ] 2.2 Implement `prompt_contract()` with `coerce_findings_payload()` in `review_findings_schema.py`
  **Dependencies**: 2.1
  **Files**: `skills/parallel-infrastructure/scripts/review_findings_schema.py`

- [ ] 2.3 Wire all review prompt callers to `prompt_contract()`
  **Dependencies**: 2.2
  **Files**: `skills/autopilot/scripts/convergence_loop.py`, `skills/parallel-review-plan/SKILL.md`, `skills/parallel-review-implementation/SKILL.md`, `skills/merge-pull-requests/scripts/vendor_review.py`

- [ ] Checkpoint: run schema helper tests, review diff, verify scope

## 3. Dispatcher repair, timeout, sidecars, ingest

- [ ] 3.1 Write dispatcher robustness tests
  **Spec scenarios**: skill-workflow Schema Repair Retry (repaired, unbounded); Raw Vendor Output Sidecar (failed, successful); Per-Vendor Dispatch Timeout Budget (converge passes timeout, Claude budget, CLI override); Judgment Ingest for Model Reviewers (CLI judgment, no self-promote); Empty Or Blinded Review Is Not Success (fast empty, timeout not quorum_lost); Vendor Timeout Enforcement; Vendor Failure Resilience
  **Contracts**: `contracts/dispatch-timeout-budget.schema.json`, `contracts/vendor-raw-output.schema.json`
  **Design decisions**: D3, D4, D5, D6, D7
  **Dependencies**: 2.2
  **Files**: `skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py`, `skills/tests/autopilot/test_convergence_loop.py`

- [ ] 3.2 Implement coerce-then-validate plus one repair retry
  **Dependencies**: 3.1
  **Files**: `skills/parallel-infrastructure/scripts/review_dispatcher.py`

- [ ] 3.3 Implement raw stdout sidecars
  **Dependencies**: 3.1
  **Files**: `skills/parallel-infrastructure/scripts/review_dispatcher.py`, `skills/parallel-infrastructure/scripts/checkpoint_findings.py`

- [ ] 3.4 Implement per-vendor timeout budget through `converge()`
  **Dependencies**: 3.1
  **Files**: `skills/parallel-infrastructure/scripts/review_dispatcher.py`, `skills/autopilot/scripts/convergence_loop.py`

- [ ] 3.5 Implement judgment ingest for model reviewers
  **Dependencies**: 3.2
  **Files**: `skills/parallel-infrastructure/scripts/review_dispatcher.py`

- [ ] 3.6 Reject fast-empty findings as unsuccessful
  **Dependencies**: 3.5
  **Files**: `skills/parallel-infrastructure/scripts/review_dispatcher.py`

- [ ] Checkpoint: run dispatcher and converge tests, review diff, verify scope

## 4. Integration

- [ ] 4.1 Add a fixture replay of archived invalid-JSON timeout blobs through the new path
  **Spec scenarios**: skill-workflow Empty Or Blinded Review Is Not Success (timeout not quorum_lost); Finding Coercion Before Validation
  **Design decisions**: D2, D3, D7
  **Dependencies**: 3.6
  **Files**: `skills/tests/parallel-infrastructure/test_review_dispatch_replay.py`

- [ ] 4.2 Validate the change with `openspec validate --strict` then the parallel-infrastructure unit suite then the autopilot unit suite
  **Dependencies**: 4.1
  **Files**: none

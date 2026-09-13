# Tasks: Harden substantive review gates

## Phase 1: Dispatcher guardrails

- [ ] 1.1 Write historical placeholder ingestion tests [S]
  **Spec scenarios**: review-convergence-safety.1 (Historical placeholder response), review-convergence-safety.2 (Placeholder does not invalidate a substantive review)
  **Design decisions**: D1
  **Dependencies**: None
- [ ] 1.2 Implement placeholder-only classification [S]
  **Dependencies**: 1.1
- [ ] 1.3 Write terminal-result callback tests [S]
  **Spec scenarios**: review-convergence-safety.6 (Async submission is not terminal), review-convergence-safety.7 (Callback preserves return order)
  **Contracts**: contracts/README.md
  **Design decisions**: D3
  **Dependencies**: None
- [ ] 1.4 Implement terminal-result callback dispatch [S]
  **Dependencies**: 1.3
- [ ] 1.5 Checkpoint: run dispatcher tests, review diff, verify scope

## Phase 2: Convergence guardrails

- [ ] 2.1 Write high-impact adjudication tests [S]
  **Spec scenarios**: review-convergence-safety.3 (Unconfirmed high judgment), review-convergence-safety.4 (Medium judgment remains advisory)
  **Design decisions**: D2
  **Dependencies**: None
- [ ] 2.2 Implement high-impact adjudication routing [S]
  **Dependencies**: 2.1
- [ ] 2.3 Write interrupted-panel checkpoint test [S]
  **Spec scenarios**: review-convergence-safety.5 (Supervisor interruption after one completion)
  **Contracts**: contracts/README.md
  **Design decisions**: D3, D4
  **Dependencies**: 1.4
- [ ] 2.4 Implement incremental convergence checkpointing [M]
  **Dependencies**: 2.3
- [ ] 2.5 Checkpoint: run convergence tests, review diff, verify scope

## Phase 3: Validation

- [ ] 3.1 Update requirement traceability evidence [XS]
  **Dependencies**: 1.5, 2.5
- [ ] 3.2 Run strict OpenSpec validation [XS]
  **Dependencies**: 3.1
- [ ] 3.3 Run repository quality gates [S]
  **Dependencies**: 3.2

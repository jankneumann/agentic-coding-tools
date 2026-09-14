# Tasks — Route parked escalations through the escalate-resume gate

## 1. Specify the recovered authority boundary

- [ ] 1.1 (M) Write deterministic checkpoint transaction tests: blocked approval wait preserves concurrent unrelated transition/apply state, stale target candidates make no authority or mirror mutation, and two blocked subjects retain both mirror entries.
  **Spec scenarios**: supervise.1, supervise.2
  **Design decisions**: D2, D3
  **Dependencies**: None

- [ ] 1.2 (M) Write checkpoint serialization tests proving a visible checkpoint includes its gate-decision ledger atomically and legacy generationless records reuse/retire safely.
  **Spec scenarios**: supervise.3
  **Design decisions**: D2, D4
  **Dependencies**: None

- [ ] 1.3 (M) Write resumed-batch lifecycle tests for current-journal membership: one and multiple resumed members, missing current member, historical peer, stale generation, and terminal-persisted recovery.
  **Spec scenarios**: roadmap-orchestration.1, roadmap-orchestration.2
  **Design decisions**: D6
  **Dependencies**: None

- [ ] Checkpoint: run focused RED suites, review test fixtures and intended file scope.

## 2. Implement the shared authority path

- [ ] 2.1 (M) Add the shared per-workspace checkpoint transaction and fold gate-decision serialization into its single atomic payload.
  **Dependencies**: 1.1, 1.2

- [ ] 2.2 (M) Migrate execution and delegated-orchestrator checkpoint mutations to the shared transaction seam without holding it across callbacks or network I/O.
  **Dependencies**: 2.1

- [ ] 2.3 (M) Implement generation-subject locked routing with fresh recheck, atomic decision-plus-proceed resume, post-commit derived mirror reconciliation, and stale-candidate no-op behavior.
  **Dependencies**: 1.1, 1.2, 2.1, 2.2

- [ ] Checkpoint: run focused transaction/router tests, review cumulative diff, and verify no stale snapshot writer remains.

## 3. Implement recovered lifecycle semantics

- [ ] 3.1 (M) Derive delegated apply's exact required result set from current journal state and reject missing or historical results before callbacks.
  **Dependencies**: 1.3, 2.2

- [ ] 3.2 (M) Integrate post-complete-batch policy-pause routing, exact allowlisted policy-pause context, legacy generation selection, approval-ref matching, and bounded route results.
  **Dependencies**: 2.3, 3.1

- [ ] 3.3 (S) Update schema, supervise protocol documentation, and executable documentation guards for complete-apply ordering, route-only retry, mirror authority, and generation semantics.
  **Dependencies**: 3.2

- [ ] Checkpoint: run supervise and delegated lifecycle suites, review scope, and update completed task markers.

## 4. Validate and review

- [ ] 4.1 (M) Run focused roadmap-runtime, supervise, and autopilot-roadmap regression suites; then run the full skills suite.
  **Dependencies**: 3.1, 3.2, 3.3

- [ ] 4.2 (S) Run Ruff, strict change/repository OpenSpec validation, work-package/DAG validation, and context-drift validation.
  **Dependencies**: 4.1

- [ ] 4.3 (M) Run vendor-diverse implementation review, address confirmed findings, and record dispositions before opening the PR.
  **Dependencies**: 4.2

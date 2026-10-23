# Tasks: Reject vacuous worker results in the package executor

> Change ID: `reject-vacuous-worker-results-in-the-package-executor`
> Roadmap item: `ri-04` (`verification-enforcement-discipline`)

## Status

- [x] Planning
- [ ] Implementation
- [ ] Testing
- [ ] Review
- [ ] Done

## 1. Result contract and checker (wp-contract)

- [x] 1.1 Write failing tests in `skills/validate-packages/scripts/tests/test_validate_work_result.py` for empty and `not_run` steps (S)
  - `validate_verification_consistency` on `steps: []` reports an error naming the empty step list, with both `passed: true` and `passed: false`; `validate_result` returns `valid == false`.
  - A step with `method: not_run, passed: true` produces an error naming the step.
  **Spec scenarios**: parallel-infrastructure.empty-steps-validation-error, parallel-infrastructure.not-run-step-cannot-pass
  **Design decisions**: D1
  **Dependencies**: None
- [x] 1.2 Write failing tests for the `commit_resolves` check (S)
  - Fixture: a temporary `git init` repo with one commit.
  - Its HEAD SHA passes. A well-formed absent SHA fails, and the error names the commit and the path. A non-repository directory fails.
  - A non-hex commit such as `--help` fails without `git` being invoked (monkeypatch `subprocess.run` to assert it is not called).
  - Without `worktree_path` the check is `skipped: true` and `valid` is unchanged.
  - CLI `--worktree <path>` on an absent commit exits 1 and prints `commit_resolves`.
  **Spec scenarios**: parallel-infrastructure.absent-commit-fails, parallel-infrastructure.present-commit-passes, parallel-infrastructure.commit-check-skipped-recorded, parallel-infrastructure.cli-worktree-flag
  **Design decisions**: D2
  **Dependencies**: None
- [x] 1.3 Write failing tests for `derive_outcome`, `effective_outcome` and outcome consistency (S)
  - Derivation table: failed → BLOCKED; completed with passing non-empty steps and a passing scope check → PASS; a failing step, empty steps or `scope_check.passed == false` → ISSUES.
  - `outcome: PASS` contradicted by a failing step, a failed scope check or `status: failed` is an error. `status: failed` with `outcome: ISSUES` is an error. `outcome: ISSUES` over passing evidence is valid, and its effective outcome is ISSUES.
  **Spec scenarios**: parallel-infrastructure.pass-contradicted-rejected, parallel-infrastructure.downgrade-allowed, parallel-infrastructure.legacy-result-validates
  **Design decisions**: D3
  **Dependencies**: None
- [x] 1.4 Add optional `outcome` and `method` to both copies of `work-queue-result.schema.json`, keeping `schema_version` at 1 and the copies byte-identical (XS)
  **Dependencies**: 1.3
- [x] 1.5 Implement the empty-step and `not_run` errors in `validate_verification_consistency` (XS)
  **Dependencies**: 1.1
- [x] 1.6 Implement `validate_commit_resolves` and `validate_result(..., *, worktree_path=None)`, and add the CLI `--worktree` flag (S)
  **Dependencies**: 1.2
- [x] 1.7 Implement `derive_outcome`, `effective_outcome` and `validate_outcome_consistency`, and wire them into `validate_result` (S)
  **Dependencies**: 1.3, 1.4
- [x] Checkpoint: run `skills/validate-packages/scripts/tests`, review the diff, verify the scope

## 2. Emitter and acceptance (wp-acceptance)

- [x] 2.1 Write failing tests in `skills/parallel-infrastructure/scripts/tests/test_package_executor.py` (S)
  - `build_result` with zero steps gives `verification.passed == false` and an outcome that is not PASS.
  - `build_result` emits PASS, BLOCKED or ISSUES according to its inputs.
  - An explicit `outcome=` is emitted as given.
  - `build_failure_result`'s step has `method: not_run` and the result has `outcome: BLOCKED`.
  **Spec scenarios**: parallel-infrastructure.empty-steps-not-passed, parallel-infrastructure.build-result-emits-outcome
  **Design decisions**: D1, D3
  **Dependencies**: 1.7
- [x] 2.2 Write failing tests in `test_result_validator.py` for `accept_package_result` and `PackageAcceptance` (S)
  - A PASS result whose commit resolves in a temporary repo is accepted.
  - A failed result, an ISSUES result, a BLOCKED result, an invalid result and `worktree_path=None` are each refused, and each refusal has a reason naming the condition that failed.
  - The acceptance is frozen.
  - `override_for` with a blank reason or approver raises `ValueError`. A valid override returns `accepted=True` and carries `{reason, approver}`.
  **Spec scenarios**: parallel-infrastructure.accept-pass, parallel-infrastructure.skipped-commit-check-refused, parallel-infrastructure.override-blank-rejected
  **Design decisions**: D4, D6
  **Dependencies**: 1.6, 1.7
- [x] 2.3 Fix `build_result` (non-empty and all passed; derived or explicit `outcome`) and `build_failure_result` (`method: not_run`) (XS)
  **Dependencies**: 2.1
- [x] 2.4 Implement `PackageAcceptance` (with the `override_for` constructor) in the new dependency-free `package_acceptance.py`, re-export it from `result_validator`, and implement `accept_package_result`, and thread `worktree_path` through `validate_package_result` (S)
  **Dependencies**: 2.2
- [x] Checkpoint: run the parallel-infrastructure and validate-packages suites, review the diff, verify the scope

## 3. Decision points (wp-gates)

- [x] 3.1 Write failing tests in `test_dag_scheduler.py` (S)
  - Migrate the existing `mark_completed(pid)` calls to pass an accepted `PackageAcceptance`.
  - A refused acceptance returns `False`, sets `failed` with an error listing the reasons, and leaves dependants unready.
  - An acceptance for another package, and a non-acceptance value, are refused.
  - An override completes the package, and `get_status_summary` reports the reason and approver.
  **Spec scenarios**: parallel-infrastructure.failed-result-not-completed, parallel-infrastructure.mismatched-acceptance-refused, parallel-infrastructure.override-recorded
  **Design decisions**: D4, D6
  **Dependencies**: 2.4
- [x] 3.2 Write failing tests in `test_integration_orchestrator.py` (S)
  - Migrate `_make_result` to one passing step, and record results with an accepted acceptance.
  - A failed or BLOCKED result with its refused acceptance gives `blocked_not_passing`, and `not_passing` names the package.
  - `acceptance=None` gives `blocked_not_passing` with a reason naming the missing verdict.
  - Accepted results with clean reviews give `pass`.
  - An override is listed under `overrides`.
  - The execution summary reports each package's outcome and acceptance.
  **Spec scenarios**: parallel-infrastructure.gate-blocks-failed-result, parallel-infrastructure.gate-blocks-missing-acceptance, parallel-infrastructure.gate-passes-accepted, parallel-infrastructure.override-recorded, parallel-infrastructure.summary-reports-acceptance
  **Design decisions**: D5, D6
  **Dependencies**: 2.4
- [x] 3.3 Implement `mark_completed(package_id, acceptance)` and `PackageStatus.override`, and report it in `get_status_summary` (S)
  **Dependencies**: 3.1
- [x] 3.4 Implement `record_package_result(..., acceptance=None)`, `IntegrationGateStatus.BLOCKED_NOT_PASSING`, the gate ordering, `not_passing`, `overrides` and the summary fields (S)
  **Dependencies**: 3.2
- [x] Checkpoint: run the suites, review the diff, verify the scope

## 4. End-to-end pins and docs (wp-integration)

- [ ] 4.1 Add `skills/tests/parallel-infrastructure/test_vacuous_results.py` (S)
  - The outputs of `build_result` (passing, failing and zero-step) and of `build_failure_result` validate against `openspec/schemas/work-queue-result.schema.json`.
  - A legacy result validates.
  - The two schema copies are byte-identical.
  - End-to-end flows:
    - zero steps → refused → not completed, and the gate is blocked;
    - an absent commit → refused;
    - a valid PASS → completed, and the gate passes.
  **Spec scenarios**: parallel-infrastructure.emitters-validate, parallel-infrastructure.legacy-result-validates, parallel-infrastructure.schema-copies-identical, parallel-infrastructure.empty-steps-not-passed, parallel-infrastructure.absent-commit-fails
  **Design decisions**: D7
  **Dependencies**: 3.3, 3.4
- [ ] 4.2 Update the docs (XS)
  - `skills/parallel-infrastructure/SKILL.md`: acceptance, outcome, method and override.
  - The `skills/validate-feature/SKILL.md` evidence line, changed without changing the line count.
  - The `docs/parallel-agentic-development.md` C4 row: add `BLOCKED_NOT_PASSING`.
  **Dependencies**: 3.4
- [ ] Checkpoint: run the full affected suites and `openspec validate --strict`

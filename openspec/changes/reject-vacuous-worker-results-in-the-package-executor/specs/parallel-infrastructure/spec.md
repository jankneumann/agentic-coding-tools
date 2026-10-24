## ADDED Requirements

### Requirement: Empty Verification Cannot Pass

`PackageExecutor.build_result` SHALL set `verification.passed` to `true` only when
`verification_steps` is non-empty and every step has `passed: true`; an empty step
list SHALL produce `verification.passed == false`.
`validate_work_result.validate_verification_consistency` SHALL report an error for a
result whose `verification.steps` is empty, whatever its `verification.passed` value.
It SHALL also report an error naming the step for any step with `passed: true` that
has `method: not_run`, or an integer `exit_code` other than 0, or evidence with
neither `artifacts` nor `metrics` entries. A step with `passed: false` SHALL NOT be
reported by these step rules.

<!-- Scenario ID: parallel-infrastructure.empty-steps-not-passed -->
#### Scenario: build_result with zero steps does not pass

- **WHEN** `build_result` is called with `status="completed"` and `verification_steps=[]`
- **THEN** the returned result has `verification.passed == false`
- **AND** its `outcome` is not `PASS`

<!-- Scenario ID: parallel-infrastructure.empty-steps-validation-error -->
#### Scenario: validate_work_result reports zero steps as an error

- **WHEN** `validate_result` is given a result with `verification.steps == []`
- **THEN** `checks.verification_consistency.passed` is `false` and its errors name the empty step list
- **AND** `valid` is `false`
- **AND** the same holds when the result claims `verification.passed == true`

<!-- Scenario ID: parallel-infrastructure.not-run-step-cannot-pass -->
#### Scenario: A not_run step claiming a pass is rejected

- **WHEN** a result contains a step with `method: not_run` and `passed: true`
- **THEN** `checks.verification_consistency` reports an error naming that step

<!-- Scenario ID: parallel-infrastructure.nonzero-exit-cannot-pass -->
#### Scenario: A step with a non-zero exit code claiming a pass is rejected

- **WHEN** a result contains a step with `exit_code: 1` and `passed: true`
- **THEN** `checks.verification_consistency` reports an error naming that step and its exit code
- **AND** `valid` is `false`
- **AND** the same step with `passed: false` is not reported

<!-- Scenario ID: parallel-infrastructure.empty-evidence-cannot-pass -->
#### Scenario: A passing step with no evidence is rejected

- **WHEN** a result contains a step with `passed: true` and `evidence: {"artifacts": [], "metrics": {}}`, whatever its `kind`
- **THEN** `checks.verification_consistency` reports an error naming that step's missing evidence
- **AND** a single artifact or a single metric is enough evidence to clear the error

### Requirement: Reported Head Commit Is the Package's Own Commit

`validate_work_result.validate_result` SHALL accept an optional `worktree_path`. When
it is supplied, a `commit_resolves` check SHALL run `git` with `worktree_path` as the
working directory and with inherited repository-location variables such as `GIT_DIR`
removed from its environment. It SHALL pass only when all of these hold:
`git rev-parse --verify --quiet <git.head.commit>^{commit}` exits 0; the commit is
reachable from the package branch (`git merge-base --is-ancestor`), where the package
branch is `refs/heads/<git.head.branch>` when the result reports a branch and the
worktree's `HEAD` otherwise; and the commit is not the commit that `git.base.ref`
resolves to. It SHALL fail with an error naming the commit and the worktree when any
of these does not hold, when the base ref or the package branch does not resolve, or
when `worktree_path` is not a git working tree.
When `worktree_path` is not supplied, the `commit_resolves` check SHALL be recorded
with `skipped: true` and SHALL NOT change `valid`. The CLI SHALL accept
`--worktree PATH` and pass it as `worktree_path`.

<!-- Scenario ID: parallel-infrastructure.absent-commit-fails -->
#### Scenario: A commit absent from the worktree fails validation

- **WHEN** `validate_result` is given a result whose `git.head.commit` does not exist in the repository at `worktree_path`
- **THEN** `checks.commit_resolves.passed` is `false` and its error names the commit
- **AND** `valid` is `false`
- **AND** the same holds when `worktree_path` is a directory that is not a git working tree, and the error names the path

<!-- Scenario ID: parallel-infrastructure.present-commit-passes -->
#### Scenario: A commit present in the worktree passes the check

- **WHEN** `git.head.commit` is the HEAD commit of the package branch checked out at `worktree_path`, one commit ahead of `git.base.ref`
- **THEN** `checks.commit_resolves.passed` is `true`

<!-- Scenario ID: parallel-infrastructure.unreachable-commit-fails -->
#### Scenario: A commit not reachable from the package branch fails validation

- **WHEN** `git.head.commit` exists in the repository at `worktree_path` but only on another branch, or only as a dangling commit
- **THEN** `checks.commit_resolves.passed` is `false` and its error says the commit is not reachable from the package branch
- **AND** `valid` is `false`
- **AND** the same holds when the result reports no `git.head.branch` and the commit is not reachable from the worktree's `HEAD`

<!-- Scenario ID: parallel-infrastructure.head-equals-base-fails -->
#### Scenario: A head commit equal to the base commit fails validation

- **WHEN** `git.head.commit` is the commit that `git.base.ref` resolves to, so the package made no commit
- **THEN** `checks.commit_resolves.passed` is `false` and its error says the package made no commit
- **AND** `valid` is `false`
- **AND** a `git.base.ref` or `git.head.branch` that does not resolve also fails the check

<!-- Scenario ID: parallel-infrastructure.commit-check-skipped-recorded -->
#### Scenario: No worktree path records a skipped check

- **WHEN** `validate_result` is called without `worktree_path`
- **THEN** `checks.commit_resolves` has `skipped: true`
- **AND** the check does not by itself make `valid` false

<!-- Scenario ID: parallel-infrastructure.cli-worktree-flag -->
#### Scenario: The CLI exits non-zero for an absent commit

- **WHEN** `validate_work_result.py <result.json> --worktree <path>` runs on a result naming an absent commit
- **THEN** the process exits 1 and the output names the `commit_resolves` failure

### Requirement: Explicit Result Outcome and Step Method

The work-queue result schema SHALL define an optional top-level `outcome` with values
`PASS`, `ISSUES` and `BLOCKED`, and an optional per-step `method` with values
`executed`, `ci`, `inspected` and `not_run`. A result's effective outcome SHALL be its
`outcome` when present, and otherwise SHALL be derived as: `BLOCKED` when `status` is
`failed`; `PASS` when `status` is `completed`, `verification.steps` is non-empty,
`verification.passed` is `true`, every step has `passed: true` and `scope_check.passed`
is not `false`; `ISSUES`
otherwise. `build_result` SHALL always emit `outcome`: when no `outcome` argument is
supplied it SHALL be the derived value, and a supplied value SHALL be emitted
unchanged so that validation judges it. `build_failure_result` SHALL emit its synthetic step with `method: not_run`.
Validation SHALL report an error when `outcome` is `PASS` but the derivation from the
evidence is not `PASS`, and when `status` is `failed` and `outcome` is present and not
`BLOCKED`. An `outcome` of `ISSUES` or `BLOCKED` over passing evidence SHALL be valid.

<!-- Scenario ID: parallel-infrastructure.build-result-emits-outcome -->
#### Scenario: build_result emits the derived outcome

- **WHEN** `build_result` is called with `status="completed"`, in-scope files and one passing step
- **THEN** the result has `outcome == "PASS"`
- **AND** when called with `status="failed"` the result has `outcome == "BLOCKED"`
- **AND** when called with a failing step the result has `outcome == "ISSUES"`

<!-- Scenario ID: parallel-infrastructure.pass-contradicted-rejected -->
#### Scenario: A PASS outcome contradicted by evidence is rejected

- **WHEN** a result has `outcome: PASS` and a failing step, or a failed scope check, or `status: failed`
- **THEN** validation reports an outcome-consistency error and `valid` is `false`
- **AND** the same holds for a result with `status: failed` and `outcome: ISSUES`

<!-- Scenario ID: parallel-infrastructure.downgrade-allowed -->
#### Scenario: A worker may downgrade its own outcome

- **WHEN** a result has `outcome: ISSUES` and all evidence passes
- **THEN** validation reports no outcome-consistency error
- **AND** the effective outcome is `ISSUES`

### Requirement: Package Acceptance Only From a Validated PASS

`result_validator.accept_package_result(result_data, package_def,
expected_contracts_revision, expected_plan_revision, worktree_path)` SHALL return a
frozen `PackageAcceptance` carrying `package_id`, `accepted`, the effective `outcome`
and a sequence of `reasons`. It SHALL be accepted only when full Phase C1 validation is
valid, the `commit_resolves` check ran (was not skipped) and passed, the effective
outcome is `PASS`, and the result's `package_id`, when present, equals the package
definition's; otherwise `reasons` SHALL name every failed condition.
`DAGScheduler.mark_completed(package_id, acceptance)` SHALL mark the package
`completed` only when `acceptance` is a `PackageAcceptance` for the same package with
`accepted == true`, and SHALL return `true` in that case. Otherwise it SHALL mark the
package `failed` with an error listing the reasons, and SHALL return `false`, so
packages depending on it do not become ready.

<!-- Scenario ID: parallel-infrastructure.accept-pass -->
#### Scenario: A validated PASS result is accepted and completes the package

- **WHEN** a schema-valid result with one passing step and a commit that resolves in the given worktree is passed to `accept_package_result`
- **THEN** the acceptance is accepted with outcome `PASS`
- **AND** `mark_completed` with it returns `true` and the package's dependants become ready

<!-- Scenario ID: parallel-infrastructure.failed-result-not-completed -->
#### Scenario: A failed or BLOCKED result does not complete the package

- **WHEN** the package's result has `status: failed` or `outcome: BLOCKED`, and its acceptance is passed to `mark_completed`
- **THEN** `mark_completed` returns `false`
- **AND** the package state is `failed`, not `completed`
- **AND** its dependants are not returned by `get_ready_packages`

<!-- Scenario ID: parallel-infrastructure.skipped-commit-check-refused -->
#### Scenario: Acceptance refuses an unchecked commit

- **WHEN** `accept_package_result` is called with `worktree_path=None`
- **THEN** the acceptance is not accepted and its reasons name the unchecked commit

<!-- Scenario ID: parallel-infrastructure.mismatched-acceptance-refused -->
#### Scenario: An acceptance for a different package is refused

- **WHEN** `mark_completed("wp-a", acceptance)` is called with an accepted acceptance for `wp-b`, or with a value that is not a `PackageAcceptance`
- **THEN** it returns `false` and `wp-a` is not completed

### Requirement: Integration Gate Blocks Non-Passing Results

`IntegrationOrchestrator.record_package_result(package_id, result, acceptance=None)`
SHALL store the acceptance verdict with the result. `check_integration_gate` SHALL
return status `blocked_incomplete` when any implementation package has no result, and
otherwise SHALL return status `blocked_not_passing` when any implementation package's
result has no acceptance verdict, a verdict that is not accepted, or an accepted
verdict without an override whose `result_digest` is not `digest_result` of the
recorded result, naming those packages and their reasons under `not_passing`, before
any review-findings check runs. `accept_package_result` SHALL set `result_digest` to
`digest_result` of the result it judged.
The execution summary SHALL report each package's effective outcome and acceptance.

<!-- Scenario ID: parallel-infrastructure.gate-blocks-failed-result -->
#### Scenario: The gate blocks a package whose only result is failed or BLOCKED

- **WHEN** every implementation package has a recorded result and review, and one package's only result is `status: failed` or `outcome: BLOCKED` with its non-accepted acceptance
- **THEN** `check_integration_gate` returns status `blocked_not_passing`
- **AND** `not_passing` names that package

<!-- Scenario ID: parallel-infrastructure.gate-blocks-missing-acceptance -->
#### Scenario: A result recorded without an acceptance verdict blocks the gate

- **WHEN** a result is recorded with `acceptance=None`
- **THEN** `check_integration_gate` returns `blocked_not_passing` with a reason naming the missing verdict

<!-- Scenario ID: parallel-infrastructure.gate-blocks-acceptance-for-another-result -->
#### Scenario: An acceptance issued for a different result blocks the gate

- **WHEN** a failed result is recorded with an accepted verdict that was made for a different, passing result of the same package
- **THEN** `check_integration_gate` returns `blocked_not_passing` with the reason "acceptance was not issued for the recorded result"
- **AND** the same holds for an accepted verdict that carries no `result_digest`

<!-- Scenario ID: parallel-infrastructure.summary-reports-acceptance -->
#### Scenario: The execution summary reports outcome and acceptance

- **WHEN** `generate_execution_summary` runs after one accepted and one refused result are recorded
- **THEN** each package's entry carries its effective outcome and whether it was accepted

<!-- Scenario ID: parallel-infrastructure.gate-passes-accepted -->
#### Scenario: Accepted results with clean reviews pass the gate

- **WHEN** every implementation package has an accepted result and a review with no blocking findings
- **THEN** `check_integration_gate` returns status `pass`

### Requirement: Recorded Acceptance Override

`PackageAcceptance.override_for(package_id, reason, approver)` SHALL return an accepted
acceptance whose `override` records the reason and approver, and SHALL raise
`ValueError` when either is blank. Constructing a `PackageAcceptance` with
`accepted == true` SHALL raise `ValueError` unless its `outcome` is `PASS` or it
carries an override with a non-blank reason and approver. The integration gate
response SHALL list every
overridden package under `overrides`, and `DAGScheduler.get_status_summary` SHALL
report the override on each package completed through one.

<!-- Scenario ID: parallel-infrastructure.override-recorded -->
#### Scenario: An override completes the package and is visible

- **WHEN** `mark_completed` is called with `PackageAcceptance.override_for("wp-a", "flaky CI, rerun green", "operator")`
- **THEN** it returns `true`
- **AND** the status summary for `wp-a` carries the reason and approver
- **AND** a gate that passes with that acceptance lists `wp-a` under `overrides`

<!-- Scenario ID: parallel-infrastructure.override-blank-rejected -->
#### Scenario: A blank override reason or approver is rejected

- **WHEN** `PackageAcceptance.override` is called with a blank reason or approver
- **THEN** it raises `ValueError`

<!-- Scenario ID: parallel-infrastructure.silent-accept-impossible -->
#### Scenario: An accepted verdict cannot be built without PASS or an override

- **WHEN** `PackageAcceptance("wp-a", True, None)` or `PackageAcceptance("wp-a", True, "ISSUES")` is constructed directly
- **THEN** it raises `ValueError`
- **AND** so does a directly passed override with a blank reason or a missing approver

### Requirement: Existing Work-Queue Result Emitters Remain Valid

The `outcome` and `method` schema fields SHALL be optional, `schema_version` SHALL
remain `1`, and the schema under `openspec/schemas/` and its installed copy under
`skills/parallel-infrastructure/install_assets/openspec/schemas/` SHALL be
byte-identical. Results produced by `build_result` and `build_failure_result`, and a
result that carries neither new field, SHALL validate against the schema.

<!-- Scenario ID: parallel-infrastructure.emitters-validate -->
#### Scenario: Every emitter's output validates against the schema

- **WHEN** the outputs of `build_result` (passing and failing) and `build_failure_result` are validated against `work-queue-result.schema.json`
- **THEN** each has no schema errors

<!-- Scenario ID: parallel-infrastructure.legacy-result-validates -->
#### Scenario: A legacy result without the new fields still validates

- **WHEN** a result with one passing step and no `outcome` or `method` fields is validated
- **THEN** it has no schema errors and its effective outcome is `PASS`

<!-- Scenario ID: parallel-infrastructure.schema-copies-identical -->
#### Scenario: Both schema copies are identical

- **WHEN** the two copies of `work-queue-result.schema.json` are compared
- **THEN** their bytes are equal

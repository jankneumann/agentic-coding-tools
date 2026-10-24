# Reject vacuous worker results in the package executor

> Parent roadmap: `verification-enforcement-discipline` (Phase 1: Absence is not a pass)
> Roadmap item: `ri-04`
> Change ID: `reject-vacuous-worker-results-in-the-package-executor`
> Effort: L · Priority: 1 · Depends on: none

## Why

A work-package result can currently claim success with no evidence, and the
orchestrator will believe it:

- `skills/parallel-infrastructure/scripts/package_executor.py:189` computes
  `verification.passed = all(step.passed for step in steps)`, which is `True` for an
  empty list. A worker that ran nothing reports a pass.
- `skills/validate-packages/scripts/validate_work_result.py`
  `validate_verification_consistency` returns early with no errors when `steps` is
  empty, so the one consistency check never fires on the vacuous case.
- Nothing checks that the worker's self-reported `git.head.commit` exists. A result
  can name a commit that was never made.
- `integration_orchestrator.record_package_result` stores any result, and
  `check_integration_gate` treats "a result is present" as "the package completed",
  so a `status: failed` result unblocks the gate exactly as a passing one does.
- `dag_scheduler.mark_completed(package_id)` takes no evidence at all, so dependants
  become ready on the caller's word.

The roadmap's governing sentence is *the absence of evidence is not a pass*. Today
the package executor's contract cannot tell "verified" from "claimed".

## What Changes

1. **Empty verification cannot pass.** `build_result` computes
   `passed = bool(steps) and all(step passed)`. `validate_verification_consistency`
   reports zero steps as an error whatever `passed` says. It also rejects a passing
   step that carries a non-zero `exit_code`, or that has no evidence at all (no
   artifacts and no metrics).
2. **The head commit must be the package's own commit.** `validate_result` gains
   an optional `worktree_path`. When it is given, a `commit_resolves` check runs in
   that worktree and fails unless all three of these hold:
   - `git.head.commit` resolves to a commit (`git rev-parse --verify --quiet
     <commit>^{commit}`);
   - it is reachable from the package branch (`git merge-base --is-ancestor`). The
     package branch is `refs/heads/<git.head.branch>` when the result reports one,
     and the worktree's `HEAD` otherwise;
   - it is not the commit that `git.base.ref` resolves to. A worker that made no
     commit has not passed.

   A base ref or branch that does not resolve fails the check. The CLI gains
   `--worktree PATH`. When no path is given the check is recorded as `skipped`. It
   is never silently passed.
3. **Explicit outcome and per-step method.** The result schema gains an optional
   top-level `outcome` (`PASS` / `ISSUES` / `BLOCKED`) and an optional per-step
   `method` (`executed` / `ci` / `inspected` / `not_run`). `build_result` always
   emits a derived `outcome`. `build_failure_result` marks its synthetic step
   `method: not_run`. Validation rejects any `outcome` or `method` that the evidence
   contradicts.
4. **Acceptance only from a validated PASS.** A new
   `result_validator.accept_package_result(...)` returns a frozen
   `PackageAcceptance`. It is accepted only when all three of these hold:
   - full Phase C1 validation is valid;
   - the commit check actually ran and passed;
   - the effective outcome is `PASS`.

   `dag_scheduler.mark_completed(package_id, acceptance)` marks a package completed
   only from an accepted `PackageAcceptance` for that package. Otherwise it marks
   the package `failed` with the reasons and returns `False`, so dependants stay
   blocked.
5. **The integration gate blocks non-passing results.**
   `record_package_result(package_id, result, acceptance=None)` stores the verdict.
   `check_integration_gate` returns a new `blocked_not_passing` status for any
   implementation package whose recorded result is present but not accepted.
   Results that are `failed`, `BLOCKED` or `ISSUES`, or that have no acceptance
   verdict, all count. So does a validated verdict whose `result_digest` is not the
   digest of the recorded result, since that verdict was made for another result.
   A missing result keeps returning `blocked_incomplete`.
6. **A recorded override, never a silent one.** `PackageAcceptance.override_for(...)`
   requires a non-blank reason and approver. It produces an accepted verdict that
   carries the override, and the gate response and the scheduler status summary
   surface it. Constructing `PackageAcceptance` directly with `accepted=True` and
   neither outcome `PASS` nor an override raises `ValueError`.
7. **Existing emitters keep validating.** Both new schema fields are optional,
   `schema_version` stays `1`, and the installed schema copy is kept byte-identical.
   A test validates the outputs of `build_result` and `build_failure_result`, plus
   a legacy result without the new fields, against the schema.

## Assumptions (stated in place of discovery questions)

This change was planned by a supervised autopilot worker that may not ask
discovery questions. Each conservative choice is recorded here so a reviewer can
overturn it:

- **A1. Capability:** the requirements belong to the existing
  `parallel-infrastructure` capability, which already owns "Integration Gate Uses
  Consensus". No new capability or skill is added.
- **A2. Method vocabulary:** `executed` means the worker ran the command in the
  package worktree. `ci` means it read a CI run's result. `inspected` means
  reading only, with no execution. `not_run` means the step was not performed. The
  only rule enforced on it is that `not_run` cannot pass. Finer semantics are out
  of scope.
- **A3. ISSUES is not a pass.** Only `PASS` is accepted. `ISSUES` (work done,
  evidence not clean) and `BLOCKED` (could not complete) both block dependants and
  the gate, as the roadmap states for "present but not passing".
- **A4. A worker may downgrade, never upgrade.** A worker may report
  `ISSUES`/`BLOCKED` when the evidence would allow `PASS`, because that is the
  conservative direction. It may not report `PASS` when the evidence does not
  support it. `status: failed` requires `BLOCKED` when `outcome` is present.
- **A5. The commit check needs an explicit path.** `git.head.worktree` is a name,
  not a path, so the caller passes the package worktree path. Library callers that
  pass none get a recorded `skipped` check and an unchanged `valid`, which keeps
  existing callers working. `accept_package_result`, the decision point, refuses a
  skipped check, so the fail-closed property holds where completion is decided.
- **A6. Breaking internal signatures is acceptable.** `mark_completed` gains a
  required `acceptance` argument. Its only callers are tests and skill prose, and
  they are migrated in this change. `record_package_result` keeps a compatible
  signature (`acceptance=None`), but a missing verdict now blocks the gate.

## Impact

- **Code:**
  - `skills/parallel-infrastructure/scripts/` — `package_executor.py`, `result_validator.py`, `dag_scheduler.py`, `integration_orchestrator.py`
  - `skills/validate-packages/scripts/validate_work_result.py`
- **Schema:** `openspec/schemas/work-queue-result.schema.json` and its installed copy under `skills/parallel-infrastructure/install_assets/`. Both changes are additive and optional.
- **Docs:**
  - `skills/parallel-infrastructure/SKILL.md`
  - the `skills/validate-feature/SKILL.md` evidence checklist (one line, line-neutral)
  - the `docs/parallel-agentic-development.md` C4 table row
- **Tests:**
  - the existing co-located suites under `skills/parallel-infrastructure/scripts/tests/` and `skills/validate-packages/scripts/tests/` (fixtures with `steps: []` are migrated)
  - a new `skills/tests/parallel-infrastructure/test_vacuous_results.py` that pins the roadmap acceptance outcomes end to end

## Non-Goals

- Changing how workers run verification steps, or which steps a package declares.
- Checking that `files_modified` matches the commit's diff. The commit check
  binds the head commit to the package branch and rejects head == base. It does
  not compare the diff with the reported file list. (An earlier draft also left
  branch reachability and head == base out of scope. After review, the user chose
  the strict reading: the commit must be reachable from the package branch and
  must not be the base commit.)
- Any change to the review-findings or consensus path of the integration gate.
- Coordinator or work-queue server changes. The coordinator stores the result
  payload opaquely.

## Approaches Considered

- **A — Tighten the existing executor, validator and gates (selected).** This is
  the smallest change that makes the vacuous pass unrepresentable at every
  decision point. It reuses `validate_work_result` and `result_validator`, and it
  follows the roadmap constraint to prefer tightening over new skills.
- **B — Make `outcome` and `method` required and bump `schema_version` to 2.**
  This is stronger, but every emitter and stored result would have to migrate at
  once. The roadmap constraint allows it only if all emitters migrate in the same
  change, and stored historical results could not. Rejected.
- **C — Enforce only in `dag_scheduler`.** This leaves the integration gate and the
  CLI validator still accepting vacuous results, so a caller that skips the
  scheduler bypasses it. Rejected.

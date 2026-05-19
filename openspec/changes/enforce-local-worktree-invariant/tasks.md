# Tasks

All work runs in managed worktrees in local CLI execution. Test tasks precede
the implementation tasks they verify.

## Phase 1 - Policy Helper

- [x] 1.1 Write tests for checkout mutation policy classification (S)
  - **Spec scenarios**: `worktree.local-shared-checkout-requires-worktree`, `worktree.local-managed-worktree-allows-mutation`, `worktree.cloud-or-harness-isolation-allows-in-place-mutation`, `worktree.sync-point-allowance-is-explicit`
  - **Design decisions**: D1, D3
  - **Dependencies**: None
  - Add tests under `skills/shared/tests/` covering shared checkout block, managed worktree allow, isolated harness allow, sync-point allow, and user-facing messages.

- [x] 1.2 Implement `skills/shared/checkout_policy.py` (M)
  - **Spec scenarios**: Same as 1.1
  - **Dependencies**: 1.1
  - Add the `CheckoutPolicy` dataclass, `classify_checkout()`, `require_mutation_allowed()`, and CLI entrypoint. Reuse `EnvironmentProfile.detect()` rather than duplicating cloud/local detection.

- [x] 1.3 Write tests for CLI exit behavior (S)
  - **Spec scenarios**: `worktree.local-shared-checkout-requires-worktree`, `worktree.local-managed-worktree-allows-mutation`
  - **Design decisions**: D2
  - **Dependencies**: 1.2
  - Verify `require-mutation --json` returns structured success in a managed worktree and exits non-zero with a clear message from the shared checkout.

- [x] 1.4 Add shared checkout policy CLI wiring (S)
  - **Spec scenarios**: Same as 1.3
  - **Dependencies**: 1.3
  - Make the module invokable through `skills/.venv/bin/python skills/shared/checkout_policy.py require-mutation`.

- [x] Checkpoint: run shared tests, review diff, verify scope

## Phase 2 - Skill Contracts

- [x] 2.1 Write skill invariant tests for mutating worktree requirements (M)
  - **Spec scenarios**: `skill-workflow.local-cli-mutations-require-worktree-isolation`, `skill-workflow.quick-tasks-are-read-only-unless-isolated`, `skill-workflow.autopilot-write-capable-phases-use-worktree-isolation`
  - **Design decisions**: D4, D5, D6
  - **Dependencies**: 1.4
  - Add or extend tests under `skills/tests/` to verify high-risk mutating skills mention worktree setup or checkout policy guard and do not advertise read-write shared-checkout execution.

- [x] 2.2 Update planning skill instructions for exploration flows (M)
  - **Spec scenarios**: `skill-workflow.artifact-producing-exploration-uses-worktrees`, `skill-workflow.plan-refinement-completes`
  - **Dependencies**: 2.1
  - Update canonical `skills/explore-feature/SKILL.md`, `skills/iterate-on-plan/SKILL.md`, `skills/plan-roadmap/SKILL.md`, and `skills/autopilot-roadmap/SKILL.md` to enter or verify worktrees before artifact writes.

- [x] 2.3 Update autopilot phase isolation metadata (M)
  - **Spec scenarios**: `skill-workflow.autopilot-write-capable-phases-use-worktree-isolation`
  - **Dependencies**: 2.1
  - Update `skills/autopilot/SKILL.md`, `skills/autopilot/scripts/phase_agent.py`, and the autopilot dispatch tests so write-capable phases report worktree isolation.

- [x] Checkpoint: run affected skill invariant tests, review diff, verify scope

## Phase 3 - Docs and Remaining Mutating Skills

- [ ] 3.1 Update operator documentation for the local CLI invariant (S)
  - **Spec scenarios**: `skill-workflow.main-receives-work-through-pr-sync-points`
  - **Dependencies**: 1.4
  - Update `AGENTS.md`, `docs/cloud-vs-local-execution.md`, and relevant lessons/decision docs. Remove the `/iterate-on-plan` commits-to-local-main language.

- [x] 3.2 Update quick-task plus artifact generator instructions (M)
  - **Spec scenarios**: `skill-workflow.quick-tasks-are-read-only-unless-isolated`, `skill-workflow.local-cli-mutations-require-worktree-isolation`
  - **Dependencies**: 2.1
  - Update `skills/quick-task/SKILL.md`, `skills/validate-feature/SKILL.md`, `skills/refresh-architecture/SKILL.md`, `skills/changelog-version/SKILL.md`, and `skills/archive-roadmap/SKILL.md` where they write artifacts.

- [ ] 3.3 Sync canonical skills to runtime copies (S)
  - **Spec scenarios**: `skill-workflow.local-cli-mutations-require-worktree-isolation`
  - **Dependencies**: 2.2, 2.3, 3.2
  - Run `bash skills/install.sh --mode rsync --deps none --python-tools none` so `.agents/skills/` and `.claude/skills/` reflect canonical skill changes.

- [ ] Checkpoint: run skill tests, OpenSpec validation, review diff, verify scope

## Phase 4 - Integration

- [ ] 4.1 Run focused verification (S)
  - **Spec scenarios**: all scenarios in this change
  - **Dependencies**: 1.4, 2.3, 3.3
  - Run `skills/.venv/bin/python -m pytest skills/shared/tests skills/tests/autopilot skills/tests/explore-feature skills/tests/iterate-on-plan skills/tests/quick-task` where directories exist.

- [ ] 4.2 Run full OpenSpec validation (S)
  - **Spec scenarios**: all scenarios in this change
  - **Dependencies**: 4.1
  - Run `openspec validate enforce-local-worktree-invariant --strict`.

- [ ] 4.3 Prepare PR summary (S)
  - **Spec scenarios**: `skill-workflow.main-receives-work-through-pr-sync-points`
  - **Dependencies**: 4.2
  - Summarize `CHANGES MADE`, `DIDN'T TOUCH`, and `CONCERNS` for the PR.

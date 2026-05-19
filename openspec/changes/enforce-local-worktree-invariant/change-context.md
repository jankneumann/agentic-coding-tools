# Change Context: enforce-local-worktree-invariant

<!-- 3-phase incremental artifact:
     Phase 1 (pre-implementation): Req ID, Spec Source, Description, Contract Ref, Design Decision,
       Test(s) planned. Files Changed = "---". Evidence = "---".
     Phase 2 (implementation): Files Changed populated. Tests pass (GREEN).
     Phase 3 (validation): Evidence filled with "pass <SHA>", "fail <SHA>", or "deferred <reason>". -->

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| worktree.1 | specs/worktree/spec.md / Checkout Policy Helper SHALL Reuse Environment Detection | Checkout policy helper reuses EnvironmentProfile and classifies isolated harness, local shared checkout, managed worktree, and sync-point cases. | --- | D1, D2, D3 | skills/shared/checkout_policy.py; skills/shared/tests/test_checkout_policy.py | skills/shared/tests/test_checkout_policy.py | --- |
| skill-workflow.1 | specs/skill-workflow/spec.md / Local CLI Mutations Require Worktree Isolation | Mutating local CLI skill phases run in managed worktrees unless isolated externally or explicitly sync-pointed. | --- | D1, D4 | skills/explore-feature/SKILL.md; skills/iterate-on-plan/SKILL.md; skills/plan-roadmap/SKILL.md; skills/autopilot-roadmap/SKILL.md; skills/validate-feature/SKILL.md; skills/refresh-architecture/SKILL.md; skills/changelog-version/SKILL.md; skills/archive-roadmap/SKILL.md; skills/tests/* | skills/tests/explore-feature/test_skill_md.py; skills/tests/iterate-on-plan/test_skill_md.py; skills/tests/quick-task/test_skill_md.py; skills/tests/autopilot/test_build_phase_dispatch_kwargs.py | --- |
| skill-workflow.2 | specs/skill-workflow/spec.md / Shared Checkout Mutation Policy Guard | Shared runtime exposes a reusable guard that blocks local shared-checkout mutation and allows managed worktrees, isolated harnesses, and explicit sync-points. | --- | D1, D2, D3 | skills/shared/checkout_policy.py; skills/shared/tests/test_checkout_policy.py | skills/shared/tests/test_checkout_policy.py | --- |
| skill-workflow.3 | specs/skill-workflow/spec.md / Artifact-Producing Exploration Uses Worktrees | explore-feature distinguishes read-only chat output from artifact-producing workflows that require worktree isolation. | --- | D4, D6 | skills/explore-feature/SKILL.md; skills/tests/explore-feature/test_skill_md.py | skills/tests/explore-feature/test_skill_md.py | --- |
| skill-workflow.4 | specs/skill-workflow/spec.md / Autopilot Write-Capable Phases Use Worktree Isolation | Autopilot dispatch metadata isolates every write-capable phase, including planning, implementation, validation, and fix phases. | --- | D5 | skills/autopilot/SKILL.md; skills/autopilot/scripts/phase_agent.py; skills/tests/autopilot/test_build_phase_dispatch_kwargs.py | skills/tests/autopilot/test_build_phase_dispatch_kwargs.py | --- |
| skill-workflow.5 | specs/skill-workflow/spec.md / Quick Tasks Are Read-Only Unless Isolated | quick-task is read-only from shared checkout unless it first enters a managed worktree for write mode. | --- | D4 | skills/quick-task/SKILL.md; skills/tests/quick-task/test_skill_md.py | skills/tests/quick-task/test_skill_md.py | --- |
| skill-workflow.6 | specs/skill-workflow/spec.md / Main Receives Work Through PR Sync Points | Completed local CLI work reaches main only through PR review and explicit sync-point operations with clean-tree and active-agent guards. | --- | D3 | --- | docs and skill invariant tests planned | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | A single helper makes the invariant executable and reusable. | `skills/shared/checkout_policy.py` | Avoids duplicating path and environment logic in each skill. |
| D2 | SKILL.md and shell callers need a stable guard surface. | `skills/shared/checkout_policy.py require-mutation` CLI | Mirrors existing script-path CLIs such as `skills/shared/active_agents.py`. |
| D3 | Sync-point skills still need shared checkout access, but only explicitly. | `--sync-point` policy reason plus existing sync-point guards | Keeps main mutation narrow without blocking merge/update workflows. |
| D4 | Worktree creation remains owned by `worktree.py`. | Skills call `worktree.py setup`; policy verifies the resulting context. | Preserves branch override and registry behavior in one place. |
| D5 | Autopilot has multiple write-capable phases. | Planned update to `_WORKTREE_PHASES` and SKILL.md phase text. | Prevents planning, review cache, validation evidence, or fix phases from writing to shared checkout. |
| D6 | Exploration has read-only and artifact-producing modes. | Planned `explore-feature` mode split. | Keeps cheap read-only discovery ergonomic while protecting generated artifacts. |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

## Coverage Summary

- **Requirements traced**: 7/7
- **Tests mapped**: 6 requirements have at least one implemented test; 1 requirement has planned tests
- **Evidence collected**: 0/7 requirements have pass/fail evidence
- **Gaps identified**: Operator docs remain planned after skill wiring.
- **Deferred items**: ---

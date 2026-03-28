# Tasks: unify-skill-tiers

## Task 1: Add deprecated skill cleanup to install.sh
- [ ] Add `DEPRECATED_SKILLS` array with all linear-* and parallel-* skill names being consolidated
- [ ] Add cleanup loop that removes deprecated skills from agent config dirs before installation
- [ ] Only remove directories containing `SKILL.md` (safety check for user-managed content)
- [ ] Print cleanup actions to stdout

**Files**: `skills/install.sh`

## Task 2: Consolidate plan-feature
- [ ] Merge contract generation steps (4a-4d) from parallel-plan-feature into plan-feature
- [ ] Merge work-packages generation (step 5) from parallel-plan-feature
- [ ] Merge work-packages validation (step 6) from parallel-plan-feature
- [ ] Add tier annotations to steps (`[coordinated only]`, `[local-parallel+]`, `[all tiers]`)
- [ ] Add parallel-plan-feature triggers to unified skill
- [ ] Skip coordinator-dependent steps (resource claim registration) when tier != coordinated

**Files**: `skills/plan-feature/SKILL.md`

## Task 3: Consolidate implement-feature
- [ ] Add local-parallel DAG execution path using Agent tool when work-packages.yaml exists
- [ ] Add per-package worktree setup for local-parallel tier
- [ ] Add context slicing for agent dispatch (from parallel-implement-feature)
- [ ] Merge Phase C review + integration steps for local-parallel tier
- [ ] Add change-context finalization (Phase 2 completion) from parallel-implement-feature
- [ ] Add parallel-implement-feature triggers to unified skill
- [ ] Preserve existing sequential path as the sequential tier

**Files**: `skills/implement-feature/SKILL.md`

## Task 4: Consolidate explore-feature
- [ ] Merge resource claim analysis (step 2) from parallel-explore-feature as coordinator-gated
- [ ] Merge parallel feasibility assessment (step 3) from parallel-explore-feature
- [ ] Update candidate ranking to include feasibility when coordinator is available
- [ ] Add parallel-explore-feature triggers to unified skill
- [ ] Update recommended next action to always reference `/plan-feature` (not `parallel-plan-feature`)

**Files**: `skills/explore-feature/SKILL.md`

## Task 5: Consolidate validate-feature
- [ ] Add evidence completeness checking from parallel-validate-feature as work-packages-gated section
- [ ] Add change-context evidence population (Phase 3) from parallel-validate-feature
- [ ] Keep existing full validation (deployment, security, behavioral) as the base path
- [ ] Add parallel-validate-feature triggers to unified skill

**Files**: `skills/validate-feature/SKILL.md`

## Task 6: Consolidate cleanup-feature
- [ ] Merge merge-queue integration steps from parallel-cleanup-feature as coordinator-gated
- [ ] Merge cross-feature rebase coordination as coordinator-gated
- [ ] Merge feature registry deregistration as coordinator-gated
- [ ] Merge dependent feature notification as coordinator-gated
- [ ] Add parallel-cleanup-feature triggers to unified skill

**Files**: `skills/cleanup-feature/SKILL.md`

## Task 7: Update iterate skills
- [ ] Add `linear-iterate-on-plan` triggers to iterate-on-plan
- [ ] Add `linear-iterate-on-implementation` triggers to iterate-on-implementation
- [ ] Update skill name field to remove `linear-` prefix if present

**Files**: `skills/iterate-on-plan/SKILL.md`, `skills/iterate-on-implementation/SKILL.md`

## Task 8: Remove deprecated skill directories
- [ ] Remove `skills/linear-plan-feature/`
- [ ] Remove `skills/linear-implement-feature/`
- [ ] Remove `skills/linear-explore-feature/`
- [ ] Remove `skills/linear-validate-feature/`
- [ ] Remove `skills/linear-cleanup-feature/`
- [ ] Remove `skills/linear-iterate-on-plan/`
- [ ] Remove `skills/linear-iterate-on-implementation/`
- [ ] Remove `skills/parallel-plan-feature/`
- [ ] Remove `skills/parallel-implement-feature/`
- [ ] Remove `skills/parallel-explore-feature/`
- [ ] Remove `skills/parallel-validate-feature/`
- [ ] Remove `skills/parallel-cleanup-feature/`
- [ ] Keep `skills/parallel-review-plan/` and `skills/parallel-review-implementation/`

**Files**: Multiple directories

## Task 9: Update CLAUDE.md workflow documentation
- [ ] Remove the linear/parallel workflow distinction
- [ ] Document unified workflow with tier annotations
- [ ] Update skill references to use canonical names only
- [ ] Document that `parallel-review-*` skills are retained as implementation utilities

**Files**: `CLAUDE.md`

## Task 10: Update docs references
- [ ] Update `docs/two-level-parallel-agentic-development.md` section 2.14 to document unified skill family
- [ ] Update cross-references in `docs/skills-workflow.md` if it exists

**Files**: `docs/two-level-parallel-agentic-development.md`, `docs/skills-workflow.md`

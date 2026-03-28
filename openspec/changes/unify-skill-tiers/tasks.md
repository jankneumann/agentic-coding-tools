# Tasks: unify-skill-tiers

## Task 1: Add deprecated skill cleanup to install.sh
- [ ] Add `DEPRECATED_SKILLS` array with all linear-* and parallel-* skill names being consolidated
- [ ] Add cleanup loop that removes deprecated skills from agent config dirs before installation
- [ ] Only remove directories containing `SKILL.md` (safety check for user-managed content)
- [ ] Print cleanup actions to stdout

**Files**: `skills/install.sh`

## Task 2: Create parallel-infrastructure skill and relocate scripts
- [ ] Create `skills/parallel-infrastructure/SKILL.md` (non-user-invocable infrastructure skill)
- [ ] Move scripts from `skills/parallel-implement-feature/scripts/` to `skills/parallel-infrastructure/scripts/`:
  - `dag_scheduler.py`, `scope_checker.py`, `package_executor.py`
  - `review_dispatcher.py`, `consensus_synthesizer.py`, `integration_orchestrator.py`
  - `result_validator.py`, `circuit_breaker.py`, `escalation_handler.py`
  - `__init__.py`, `__main__.py`, `tests/`
- [ ] Move `check_coordinator.py` to `skills/coordination-bridge/scripts/` (single canonical copy)

**Files**: `skills/parallel-infrastructure/`, `skills/coordination-bridge/scripts/`

## Task 3: Update downstream script imports
- [ ] Update `skills/auto-dev-loop/scripts/convergence_loop.py` sys.path to reference `parallel-infrastructure/scripts/`
- [ ] Update `skills/auto-dev-loop/SKILL.md` to replace `/parallel-*` and `/linear-*` invocations with unified names
- [ ] Update `skills/fix-scrub/scripts/vendor_dispatch.py` sys.path to reference `parallel-infrastructure/scripts/`
- [ ] Update `skills/merge-pull-requests/scripts/vendor_review.py` sys.path to reference `parallel-infrastructure/scripts/`
- [ ] Update all SKILL.md references to `check_coordinator.py` to use `coordination-bridge/scripts/check_coordinator.py`

**Files**: `skills/auto-dev-loop/`, `skills/fix-scrub/`, `skills/merge-pull-requests/`

## Task 4: Consolidate plan-feature
- [ ] Merge contract generation steps (4a-4d) from parallel-plan-feature into plan-feature
- [ ] Merge work-packages generation (step 5) from parallel-plan-feature
- [ ] Merge work-packages validation (step 6) from parallel-plan-feature
- [ ] Add tier detection logic at Step 0 with tier notification
- [ ] Add tier annotations to steps (`[coordinated only]`, `[local-parallel+]`, `[all tiers]`)
- [ ] Add parallel-plan-feature triggers to unified skill (with tier override behavior)
- [ ] Skip coordinator-dependent steps (resource claim registration) when tier != coordinated

**Files**: `skills/plan-feature/SKILL.md`

## Task 5: Consolidate implement-feature
- [ ] Add tier detection logic at Step 0 (check work-packages.yaml, task count)
- [ ] Add local-parallel DAG execution path using Agent tool when work-packages.yaml exists
- [ ] Use single feature worktree for local-parallel (not per-package)
- [ ] Add context slicing for agent dispatch (from parallel-implement-feature)
- [ ] Add prompt-based scope enforcement for dispatched agents
- [ ] Merge Phase C review + integration steps for coordinated tier
- [ ] Add change-context finalization (Phase 2 completion) from parallel-implement-feature
- [ ] Add parallel-implement-feature triggers to unified skill
- [ ] Preserve existing sequential path as the sequential tier
- [ ] Update script references to use `parallel-infrastructure/scripts/`

**Files**: `skills/implement-feature/SKILL.md`

## Task 6: Consolidate explore-feature
- [ ] Merge resource claim analysis (step 2) from parallel-explore-feature as coordinator-gated
- [ ] Merge parallel feasibility assessment (step 3) from parallel-explore-feature
- [ ] Update candidate ranking to include feasibility when coordinator is available
- [ ] Add parallel-explore-feature triggers to unified skill
- [ ] Update recommended next action to always reference `/plan-feature` (not `/parallel-plan-feature`)

**Files**: `skills/explore-feature/SKILL.md`

## Task 7: Consolidate validate-feature
- [ ] Add evidence completeness checking from parallel-validate-feature as work-packages-gated section
- [ ] Add change-context evidence population (Phase 3) from parallel-validate-feature
- [ ] Keep existing full validation (deployment, security, behavioral) as the base path
- [ ] Add parallel-validate-feature triggers to unified skill

**Files**: `skills/validate-feature/SKILL.md`

## Task 8: Consolidate cleanup-feature
- [ ] Merge merge-queue integration steps from parallel-cleanup-feature as coordinator-gated
- [ ] Merge cross-feature rebase coordination as coordinator-gated
- [ ] Merge feature registry deregistration as coordinator-gated
- [ ] Merge dependent feature notification as coordinator-gated
- [ ] Add parallel-cleanup-feature triggers to unified skill

**Files**: `skills/cleanup-feature/SKILL.md`

## Task 9: Update iterate skills
- [ ] Add `linear-iterate-on-plan` triggers to iterate-on-plan
- [ ] Add `linear-iterate-on-implementation` triggers to iterate-on-implementation
- [ ] Update skill name field to remove `linear-` prefix if present

**Files**: `skills/iterate-on-plan/SKILL.md`, `skills/iterate-on-implementation/SKILL.md`

## Task 10: Remove deprecated skill directories
- [ ] Remove `skills/linear-plan-feature/`
- [ ] Remove `skills/linear-implement-feature/`
- [ ] Remove `skills/linear-explore-feature/`
- [ ] Remove `skills/linear-validate-feature/`
- [ ] Remove `skills/linear-cleanup-feature/`
- [ ] Remove `skills/linear-iterate-on-plan/`
- [ ] Remove `skills/linear-iterate-on-implementation/`
- [ ] Remove `skills/parallel-plan-feature/` (scripts already relocated in Task 2)
- [ ] Remove `skills/parallel-implement-feature/` (scripts already relocated in Task 2)
- [ ] Remove `skills/parallel-explore-feature/`
- [ ] Remove `skills/parallel-validate-feature/`
- [ ] Remove `skills/parallel-cleanup-feature/`
- [ ] Keep `skills/parallel-review-plan/` and `skills/parallel-review-implementation/`

**Files**: Multiple directories

## Task 11: Update CLAUDE.md workflow documentation
- [ ] Remove the linear/parallel workflow distinction
- [ ] Document unified workflow with tier annotations
- [ ] Update skill references to use canonical names only
- [ ] Document that `parallel-review-*` skills are retained as implementation utilities
- [ ] Document `parallel-infrastructure` and `coordination-bridge` as infrastructure skills

**Files**: `CLAUDE.md`

## Task 12: Update docs references
- [ ] Update `docs/two-level-parallel-agentic-development.md` section 2.14 to document unified skill family
- [ ] Update `docs/skills-workflow.md` to reflect unified skills
- [ ] Update `docs/script-skill-dependencies.md` with new script locations
- [ ] Update `docs/lessons-learned.md` if it references linear/parallel skill names
- [ ] Update `openspec/specs/skill-workflow/spec.md` to reflect unified model

**Files**: `docs/two-level-parallel-agentic-development.md`, `docs/skills-workflow.md`, `docs/script-skill-dependencies.md`, `docs/lessons-learned.md`, `openspec/specs/skill-workflow/spec.md`

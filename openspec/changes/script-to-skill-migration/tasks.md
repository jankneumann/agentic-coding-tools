# Tasks: script-to-skill-migration

## T1: Create Infrastructure Skills (P0)

### T1.1: Create `skills/worktree/` infrastructure skill
- [ ] Create `skills/worktree/SKILL.md` with API documentation for `worktree.py` and `merge_worktrees.py`
- [ ] Create `skills/worktree/scripts/` directory
- [ ] Copy `scripts/worktree.py` → `skills/worktree/scripts/worktree.py`
- [ ] Copy `scripts/merge_worktrees.py` → `skills/worktree/scripts/merge_worktrees.py`
- [ ] Verify scripts run from the skill directory

### T1.2: Create `skills/coordination-bridge/` infrastructure skill
- [ ] Create `skills/coordination-bridge/SKILL.md` with API documentation
- [ ] Create `skills/coordination-bridge/scripts/` directory
- [ ] Copy `scripts/coordination_bridge.py` → `skills/coordination-bridge/scripts/coordination_bridge.py`
- [ ] Verify script runs from the skill directory

### T1.3: Create `skills/validate-packages/` infrastructure skill
- [ ] Create `skills/validate-packages/SKILL.md` with API documentation
- [ ] Create `skills/validate-packages/scripts/` directory
- [ ] Copy `scripts/validate_work_packages.py` → `skills/validate-packages/scripts/validate_work_packages.py`
- [ ] Copy `scripts/parallel_zones.py` → `skills/validate-packages/scripts/parallel_zones.py`
- [ ] Copy `scripts/validate_work_result.py` → `skills/validate-packages/scripts/validate_work_result.py`
- [ ] Copy `scripts/architecture_schema.json` if referenced by validators

### T1.4: Create `skills/validate-flows/` infrastructure skill
- [ ] Create `skills/validate-flows/SKILL.md` with API documentation
- [ ] Create `skills/validate-flows/scripts/` directory
- [ ] Copy `scripts/validate_flows.py` → `skills/validate-flows/scripts/validate_flows.py`

## T2: Update SKILL.md Path References (P0)

### T2.1: Update worktree path references (21 skills)
- [ ] linear-plan-feature/SKILL.md — `scripts/worktree.py` → `<skill-base-dir>/../worktree/scripts/worktree.py`
- [ ] linear-implement-feature/SKILL.md
- [ ] linear-iterate-on-implementation/SKILL.md
- [ ] linear-validate-feature/SKILL.md
- [ ] linear-cleanup-feature/SKILL.md
- [ ] parallel-plan-feature/SKILL.md
- [ ] parallel-implement-feature/SKILL.md
- [ ] parallel-cleanup-feature/SKILL.md
- [ ] parallel-validate-feature/SKILL.md
- [ ] fix-scrub/SKILL.md
- [ ] openspec-beads-worktree/SKILL.md
- [ ] plan-feature/SKILL.md (alias)
- [ ] implement-feature/SKILL.md (alias)
- [ ] iterate-on-implementation/SKILL.md (alias)
- [ ] validate-feature/SKILL.md (alias)
- [ ] cleanup-feature/SKILL.md (alias)
- [ ] iterate-on-plan/SKILL.md (alias)
- [ ] linear-iterate-on-plan/SKILL.md
- [ ] explore-feature/SKILL.md (alias, if referenced)
- [ ] parallel-explore-feature/SKILL.md (if referenced)
- [ ] merge-pull-requests/SKILL.md (if referenced)

### T2.2: Update coordination_bridge path references (12 skills)
- [ ] linear-plan-feature/SKILL.md — `scripts/coordination_bridge.py` → `<skill-base-dir>/../coordination-bridge/scripts/coordination_bridge.py`
- [ ] linear-implement-feature/SKILL.md
- [ ] linear-iterate-on-implementation/SKILL.md
- [ ] linear-validate-feature/SKILL.md
- [ ] linear-cleanup-feature/SKILL.md
- [ ] fix-scrub/SKILL.md
- [ ] plan-feature/SKILL.md (alias)
- [ ] implement-feature/SKILL.md (alias)
- [ ] iterate-on-implementation/SKILL.md (alias)
- [ ] validate-feature/SKILL.md (alias)
- [ ] cleanup-feature/SKILL.md (alias)
- [ ] iterate-on-plan/SKILL.md (alias)

### T2.3: Update validation script path references (4 skills)
- [ ] parallel-plan-feature/SKILL.md — `scripts/validate_work_packages.py` → sibling-relative
- [ ] parallel-plan-feature/SKILL.md — `scripts/parallel_zones.py` → sibling-relative
- [ ] parallel-implement-feature/SKILL.md — same updates
- [ ] parallel-validate-feature/SKILL.md — `scripts/validate_work_result.py` → sibling-relative

### T2.4: Update validate_flows path references (2 skills)
- [ ] linear-implement-feature/SKILL.md — `scripts/validate_flows.py` → sibling-relative
- [ ] linear-validate-feature/SKILL.md — same update

## T3: Update Python sys.path Imports (P1)

### T3.1: Update parallel-implement-feature/scripts/dag_scheduler.py
- [ ] Change `_SCRIPTS_DIR` from `parent.parent.parent.parent / "scripts"` to `parent.parent.parent / "validate-packages" / "scripts"`
- [ ] Verify imports still resolve

### T3.2: Update parallel-implement-feature/scripts/scope_checker.py
- [ ] Change `_SCRIPTS_DIR` import path to sibling-relative
- [ ] Verify imports still resolve

## T4: Update install.sh (P1)

### T4.1: Add script source sync step
- [ ] Add pre-sync step that copies source scripts into infrastructure skill directories
- [ ] Define mapping of infra skill → source scripts
- [ ] Ensure rsync preserves existing skill-local scripts (don't delete non-mapped files)
- [ ] Test sync works with `--mode rsync`, `--mode symlink`, `--mode copy`

## T5: Update refresh-architecture Skill (P2)

### T5.1: Bundle refresh_architecture.sh
- [ ] Copy `scripts/refresh_architecture.sh` into `skills/refresh-architecture/scripts/`
- [ ] Update `skills/refresh-architecture/SKILL.md` to use local path
- [ ] Also bundle any other scripts referenced by refresh_architecture.sh

## T6: Documentation and Validation (P1)

### T6.1: Documentation
- [ ] Add `docs/script-skill-dependencies.md` (already created in this plan)
- [ ] Update `CLAUDE.md` with infrastructure skill conventions
- [ ] Update `docs/skills-workflow.md` with infrastructure skill section

### T6.2: Validation
- [ ] Run `openspec validate script-to-skill-migration --strict`
- [ ] Run `install.sh` and verify infrastructure skills are synced
- [ ] Verify a skill can invoke `worktree.py` from synced location
- [ ] Run existing `scripts/tests/` to confirm no regression
- [ ] Run skill tests (bug-scrub, fix-scrub) to confirm no breakage

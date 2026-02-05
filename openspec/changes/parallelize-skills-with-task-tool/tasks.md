# Tasks: Parallelize Skills with Task Tool

## Task Groups

### 1. Update implement-feature with Parallel Quality Checks
**Dependencies**: None (can start immediately)
**Files**: `skills/implement-feature/SKILL.md`

- [x] 1.1 Update Step 6 (Quality Checks) to use parallel Task(Bash) calls
- [x] 1.2 Add result aggregation logic after parallel checks complete
- [x] 1.3 Update documentation to explain parallel execution pattern

### 2. Update iterate-on-implementation with Parallel Quality Checks
**Dependencies**: None (can run parallel with Task 1)
**Files**: `skills/iterate-on-implementation/SKILL.md`

- [x] 2.1 Update Step 7 (Run Quality Checks) to use parallel Task(Bash) calls
- [x] 2.2 Add result aggregation logic after parallel checks complete
- [x] 2.3 Update documentation to explain parallel execution pattern

### 3. Update plan-feature with Parallel Context Exploration
**Dependencies**: None (can run parallel with Tasks 1-2)
**Files**: `skills/plan-feature/SKILL.md`

- [x] 3.1 Update Step 2 (Review Existing Context) to use parallel Task(Explore) agents
- [x] 3.2 Add context synthesis logic after exploration completes
- [x] 3.3 Update documentation to explain parallel exploration pattern

### 4. Update iterate-on-plan with Parallel Analysis
**Dependencies**: None (can run parallel with Tasks 1-3)
**Files**: `skills/iterate-on-plan/SKILL.md`

- [x] 4.1 Update Step 5 (Review and Analyze) to optionally use parallel Task(Explore) agents for different finding types
- [x] 4.2 Add analysis synthesis logic
- [x] 4.3 Update documentation to explain parallel analysis pattern

### 5. Rewrite parallel-implement to Use Native Task()
**Dependencies**: None (can run parallel with Tasks 1-4)
**Files**: `skills/parallel-implement/SKILL.md`

- [x] 5.1 Remove worktree creation/cleanup steps (Steps 4, 7)
- [x] 5.2 Replace external `claude -p` spawning with Task(general-purpose) calls (Step 5)
- [x] 5.3 Replace `git merge` branch integration with orchestrator-managed commits (Step 6)
- [x] 5.4 Update monitoring to use TaskOutput instead of log file tailing (Step 8)
- [x] 5.5 Keep Beads integration optional but simplify (no worktree-per-bead)
- [x] 5.6 Update agent prompt templates for Task() context
- [x] 5.7 Update troubleshooting section for new patterns

### 6. Update skill-workflow Spec
**Dependencies**: Tasks 1-5 (after implementation patterns are finalized)
**Files**: `openspec/specs/skill-workflow/spec.md`

- [x] 6.1 Add requirement for parallel quality check execution in iterate-on-implementation
- [x] 6.2 Add scenarios for parallel execution success and failure aggregation

### 7. Documentation and Lessons Learned
**Dependencies**: Tasks 1-6
**Files**: `CLAUDE.md`

- [x] 7.1 Add lesson learned about Task() parallelization patterns
- [x] 7.2 Document when worktrees are vs aren't needed

## Parallelization Summary

| Task | Can Parallelize With |
|------|---------------------|
| 1 (implement-feature) | 2, 3, 4, 5 |
| 2 (iterate-on-implementation) | 1, 3, 4, 5 |
| 3 (plan-feature) | 1, 2, 4, 5 |
| 4 (iterate-on-plan) | 1, 2, 3, 5 |
| 5 (parallel-implement) | 1, 2, 3, 4 |
| 6 (spec update) | None - depends on 1-5 |
| 7 (docs) | None - depends on 1-6 |

**Maximum parallel width**: 5 (Tasks 1-5 can all run concurrently)

# Tasks: Parallelize Skills with Task Tool

## Task Groups

### 1. Update implement-feature with Parallel Patterns
**Dependencies**: None (can start immediately)
**Files**: `skills/implement-feature/SKILL.md`

- [x] 1.1 Update Step 6 (Quality Checks) to use parallel Task(Bash) calls
- [x] 1.2 Add result aggregation logic after parallel checks complete
- [x] 1.3 Add parallel task implementation pattern to Step 3 (for independent tasks)
- [x] 1.4 Document file scope isolation and when to parallelize

### 2. Update iterate-on-implementation with Parallel Patterns
**Dependencies**: None (can run parallel with Task 1)
**Files**: `skills/iterate-on-implementation/SKILL.md`

- [x] 2.1 Update Step 7 (Run Quality Checks) to use parallel Task(Bash) calls
- [x] 2.2 Add result aggregation logic after parallel checks complete
- [x] 2.3 Add parallel fix implementation pattern to Step 6 (for independent findings)

### 3. Update plan-feature with Parallel Context Exploration
**Dependencies**: None (can run parallel with Tasks 1-2)
**Files**: `skills/plan-feature/SKILL.md`

- [x] 3.1 Update Step 2 (Review Existing Context) to use parallel Task(Explore) agents
- [x] 3.2 Add context synthesis logic after exploration completes

### 4. Update iterate-on-plan with Parallel Analysis
**Dependencies**: None (can run parallel with Tasks 1-3)
**Files**: `skills/iterate-on-plan/SKILL.md`

- [x] 4.1 Update Step 5 (Review and Analyze) to optionally use parallel Task(Explore) agents
- [x] 4.2 Add analysis synthesis logic

### 5. Remove parallel-implement Skill
**Dependencies**: Tasks 1-2 (pattern must be merged first)
**Files**: `skills/parallel-implement/` (delete)

- [x] 5.1 Remove skills/parallel-implement directory
- [x] 5.2 Verify pattern is captured in implement-feature and iterate-on-implementation

### 6. Update skill-workflow Spec
**Dependencies**: Tasks 1-5 (after implementation patterns are finalized)
**Files**: `openspec/specs/skill-workflow/spec.md`

- [x] 6.1 Add requirement for parallel quality check execution
- [x] 6.2 Add requirement for parallel task implementation pattern
- [x] 6.3 Add scenarios for parallel execution success and failure aggregation

### 7. Documentation and Lessons Learned
**Dependencies**: Tasks 1-6
**Files**: `CLAUDE.md`

- [x] 7.1 Add lesson learned about Task() parallelization patterns
- [x] 7.2 Document when worktrees are vs aren't needed
- [x] 7.3 Document file scope isolation strategy

## Parallelization Summary

| Task | Can Parallelize With |
|------|---------------------|
| 1 (implement-feature) | 2, 3, 4 |
| 2 (iterate-on-implementation) | 1, 3, 4 |
| 3 (plan-feature) | 1, 2, 4 |
| 4 (iterate-on-plan) | 1, 2, 3 |
| 5 (remove parallel-implement) | None - depends on 1-2 |
| 6 (spec update) | None - depends on 1-5 |
| 7 (docs) | None - depends on 1-6 |

**Maximum parallel width**: 4 (Tasks 1-4 can all run concurrently)

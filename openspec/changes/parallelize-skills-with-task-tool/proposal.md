# Proposal: Parallelize Skills with Task Tool

## Change ID
`parallelize-skills-with-task-tool`

## Why

The current skill implementations have two parallelization patterns with different tradeoffs:

1. **Sequential execution** (plan-feature, implement-feature, iterate-*): All steps run serially even when independent operations could run concurrently (e.g., quality checks: pytest, mypy, ruff, openspec validate).

2. **External CLI spawning** (parallel-implement): Uses `claude -p` with git worktrees and `&` for background processes. This works but requires:
   - Git worktree setup/teardown per agent
   - Branch-per-agent management
   - Manual log file handling
   - No agent resumption on failure
   - Complex merge choreography

Claude Code now provides a native `Task()` tool that enables in-process subagent spawning with:
- `run_in_background=true` for concurrent execution
- `TaskOutput` for result collection
- `resume` parameter for error recovery
- Coordinated working directory (no worktrees needed for logically isolated tasks)

## What Changes

Update four skills and remove one:

| Skill | Change |
|-------|--------|
| plan-feature | Add parallel Explore agents for context gathering |
| implement-feature | Add parallel quality checks + parallel task implementation pattern |
| iterate-on-plan | Add optional parallel analysis agents |
| iterate-on-implementation | Add parallel quality checks + parallel fix implementation |
| parallel-implement | **REMOVED** - pattern merged into implement-feature |

### Key Architectural Change: Worktrees No Longer Needed

The old pattern required git worktrees because:
- External `claude -p` processes shared filesystem with no coordination
- Two agents editing the same file = race condition

The new pattern doesn't need worktrees because:
- Task() agents are coordinated by the parent orchestrator
- Independent tasks target different files/modules (enforced by prompt scoping)
- Tasks with file overlap must run sequentially (already a workflow rule)
- The orchestrator integrates results, not git merge

### Why Remove parallel-implement?

The parallel-implement skill was valuable because the worktree + external CLI pattern was complex. Now that Task() makes parallelization simple:
- The orchestration pattern fits naturally in implement-feature's "Implement Tasks" step
- Having a separate skill adds unnecessary complexity
- Users can parallelize ad-hoc when tasks.md has independent tasks

## Impact

### Affected Specs
- `skill-workflow` - Add requirements for parallel execution patterns

### Removed Skills
- `parallel-implement` - Pattern merged into implement-feature and iterate-on-implementation

## Non-Goals

- **Not changing the workflow structure**: The 4-skill workflow remains the same
- **Not supporting concurrent edits to same file**: Tasks with shared scope must remain sequential

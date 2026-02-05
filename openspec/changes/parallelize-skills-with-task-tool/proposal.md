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

Update five skills to leverage Task() for parallelization:

| Skill | Current Pattern | New Pattern |
|-------|-----------------|-------------|
| plan-feature | Sequential context review | Parallel Explore agents for context gathering |
| implement-feature | Sequential quality checks | Parallel background quality checks |
| parallel-implement | External CLI + worktrees | Native Task() subagents |
| iterate-on-plan | Sequential analysis | Parallel analysis agents by finding type |
| iterate-on-implementation | Sequential quality checks | Parallel background quality checks |

### Key Architectural Change: Worktrees No Longer Needed

The old pattern required git worktrees because:
- External `claude -p` processes shared filesystem with no coordination
- Two agents editing the same file = race condition

The new pattern doesn't need worktrees because:
- Task() agents are coordinated by the parent orchestrator
- Independent tasks target different files/modules (enforced by prompt scoping)
- Tasks with file overlap must run sequentially (already a workflow rule)
- The orchestrator integrates results, not git merge

## Impact

### Affected Specs
- `skill-workflow` - Add requirements for parallel execution patterns

### New Capabilities
None - this is an enhancement to existing skills.

## Non-Goals

- **Not changing the workflow structure**: The 4-skill workflow remains the same
- **Not adding new skills**: Only updating existing skills
- **Not supporting concurrent edits to same file**: Tasks with shared scope must remain sequential
- **Not removing Beads integration**: parallel-implement can still use Beads for task tracking (optional)

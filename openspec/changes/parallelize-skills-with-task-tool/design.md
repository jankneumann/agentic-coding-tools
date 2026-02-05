# Design: Parallelize Skills with Task Tool

## Problem Statement

Current skills execute steps sequentially even when operations are independent. The parallel-implement skill uses external CLI spawning which requires complex worktree management.

## Decision: Native Task() Over External CLI

### Option A: Keep External CLI Pattern (Rejected)
- Pros: Already working, battle-tested
- Cons: Complex worktree/branch management, no error recovery, manual logging

### Option B: Native Task() Subagents (Selected)
- Pros: Simpler coordination, built-in resumption, no worktree overhead
- Cons: Newer pattern, agents share filesystem

**Rationale**: Task() provides the same parallelization benefits with dramatically simpler orchestration. The filesystem sharing concern is mitigated by scoping agents to non-overlapping files (which the workflow already requires).

## Architecture

### Parallelization Patterns by Skill Type

#### Pattern 1: Parallel Quality Checks (implement-feature, iterate-on-implementation)

```
Orchestrator
    │
    ├── Task(Bash): pytest          ─┐
    ├── Task(Bash): mypy            ─┼── run_in_background=true
    ├── Task(Bash): ruff            ─┤
    └── Task(Bash): openspec validate─┘
    │
    └── TaskOutput × 4 → aggregate results
```

All checks run concurrently. Orchestrator waits for all to complete, then reports aggregate pass/fail.

#### Pattern 2: Parallel Context Exploration (plan-feature, iterate-on-plan)

```
Orchestrator
    │
    ├── Task(Explore): "Find related specs"      ─┐
    ├── Task(Explore): "Analyze existing code"   ─┼── run_in_background=true
    └── Task(Explore): "Review in-progress work" ─┘
    │
    └── TaskOutput × 3 → synthesize context
```

Exploration is read-only, safe to parallelize unconditionally.

#### Pattern 3: Parallel Task Implementation (parallel-implement)

```
Orchestrator
    │
    ├── Identify independent tasks from tasks.md
    ├── Create Beads (optional, for tracking)
    │
    ├── Task(general-purpose): "Implement task 1" ─┐
    ├── Task(general-purpose): "Implement task 2" ─┼── run_in_background=true
    └── Task(general-purpose): "Implement task 3" ─┘
    │
    └── TaskOutput × N → verify, commit
```

Each agent is scoped to specific files/modules. No worktrees needed.

## File Isolation Strategy

### Why Worktrees Were Used
External `claude -p` processes are uncoordinated. Two agents editing `src/auth.py` simultaneously would corrupt the file.

### Why Worktrees Are No Longer Needed
1. **Logical scoping**: Agent prompts explicitly list which files/modules are in scope
2. **Dependency enforcement**: Tasks with file overlap must be sequential (existing rule)
3. **Orchestrator control**: Parent coordinates when agents run and what they touch
4. **Result integration**: Orchestrator reviews agent work before committing

### When Worktrees Would Still Be Needed
Only if you wanted concurrent edits to the same file, which the workflow prohibits.

## Subagent Types and Their Uses

| Subagent Type | Use Case | run_in_background |
|---------------|----------|-------------------|
| `Bash` | Quality checks (pytest, mypy, ruff) | Yes |
| `Explore` | Context gathering, codebase analysis | Yes |
| `general-purpose` | Task implementation, complex multi-step work | Yes |
| `Plan` | Design analysis (rarely parallelized) | No |

## Error Handling

### Agent Failure Recovery
```
1. TaskOutput returns error
2. Check if recoverable (test failure vs crash)
3. If recoverable: resume agent with `resume=<agent_id>`
4. If not: report failure, stop iteration
```

### Partial Success Handling
When running multiple quality checks:
- Collect all results before failing
- Report all failures together (not fail-fast)
- User sees complete picture

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Agents modify same file | Enforce file scope in prompts; validate task independence |
| Background agent hangs | Use timeout parameter; monitor via TaskOutput |
| Result aggregation complexity | Define clear success/failure criteria per pattern |
| Beads integration break | Keep Beads optional; Task() agents can still call `bd close` |

## Testing Strategy

1. **Unit**: Mock Task() calls, verify correct parallelization patterns
2. **Integration**: Run skills with small OpenSpec proposals, verify parallel execution
3. **Manual**: Compare execution time sequential vs parallel for quality checks

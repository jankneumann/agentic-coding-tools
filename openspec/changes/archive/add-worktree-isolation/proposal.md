# Proposal: Add Per-Feature Worktree Isolation

## Change ID
`add-worktree-isolation`

## Why

When working on multiple features in different terminal windows, branch checkouts conflict because all CLI sessions share the same repo directory. Currently users must manually create git worktrees and restart Claude in new directories for each feature.

This friction discourages parallel feature development and creates context-switching overhead.

## What Changes

| Skill | Change |
|-------|--------|
| implement-feature | Create worktree automatically at start |
| cleanup-feature | Remove worktree after archive |
| iterate-on-implementation | Detect worktree context for OpenSpec file access |

### Key Design Decisions

**Worktree path convention**: `../<repo-name>.worktrees/<change-id>/`

Example directory structure:
```
/Users/user/Coding/
├── agentic-coding-tools/                    # Main repo (stays on main)
└── agentic-coding-tools.worktrees/          # Worktree parent
    ├── add-user-auth/                       # Feature A worktree
    └── improve-performance/                 # Feature B worktree
```

**Always automatic**: Worktree creation happens on every `/implement-feature` invocation. No flag needed.

**OpenSpec files stay in main repo**: Worktrees only contain implementation code. OpenSpec proposals/specs remain in the main repo and are accessed via path resolution.

## Impact

### Affected Specs
- `skill-workflow` - Add requirements for worktree isolation

### User Workflow

```bash
# Terminal 1: Start feature A
/implement-feature add-user-auth
# → Creates worktree, changes working directory
# → "Worktree created at ../agentic-coding-tools.worktrees/add-user-auth/"

# Terminal 2: Start feature B (from main repo)
/implement-feature improve-performance
# → Creates separate worktree, no conflict with Terminal 1

# When done with feature A:
/cleanup-feature add-user-auth
# → Merges PR, archives OpenSpec, removes worktree
```

## Non-Goals

- **Not task-level isolation**: One worktree per feature, not per task
- **Not cross-machine coordination**: Relies on local git operations only
- **Not replacing Task()**: Task() remains the pattern for intra-session parallelization

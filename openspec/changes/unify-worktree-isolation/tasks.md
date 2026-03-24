# Tasks: Unify Worktree Isolation for Parallel Agents

## Task Dependency Graph

```
wp-agent-profiles ──┬── wp-skill-update
                    │
wp-merge-protocol ──┘
                    └── wp-integration
```

## Tasks

### T1: Agent Profile Isolation Config (`wp-agent-profiles`)

- [ ] T1.1: Add `isolation` field to agent profile schema in `agents.yaml`
- [ ] T1.2: Update `agents_config.py` to parse the new `isolation` field
- [ ] T1.3: Add helper function `get_agent_isolation(agent_type)` returning isolation mode or None
- [ ] T1.4: Write unit tests for isolation config parsing

### T2: Integration Merge Protocol (`wp-merge-protocol`)

- [ ] T2.1: Create `scripts/merge_worktrees.py` — merges per-package branches into feature branch
- [ ] T2.2: Implement `--no-ff` merge with conflict detection and reporting
- [ ] T2.3: Implement scope violation detection on merge conflict (map conflict files to packages)
- [ ] T2.4: Add `--dry-run` mode for preflight merge feasibility check
- [ ] T2.5: Write unit tests for merge protocol (mock git operations)

### T3: Skill Prompt Updates (`wp-skill-update`)

All skill sources are in `skills/`, NOT `.claude/skills/`.

**Planning skills (launcher invariant)**:
- [ ] T3.1: Update `skills/parallel-plan-feature/SKILL.md` — add worktree setup as first step, commit artifacts to feature branch, pin worktree for reuse
- [ ] T3.2: Update `skills/linear-plan-feature/SKILL.md` — same pattern as T3.1

**Implementation skills (worktree-per-package)**:
- [ ] T3.3: Update `skills/parallel-implement-feature/SKILL.md` Phase A:
  - Add launcher invariant (shared checkout is read-only)
  - Root packages get own worktrees (sequential, merged before parallel dispatch)
  - Parallel packages get worktrees branched from updated feature branch
- [ ] T3.4: Update Phase B with worktree verification and cd-into-worktree instructions
- [ ] T3.5: Update Phase C with integration merge protocol using `merge_worktrees.py`
- [ ] T3.6: Add teardown/cleanup step for worktrees after integration
- [ ] T3.7: Update `skills/parallel-implement-feature/scripts/` helper dispatch functions
- [ ] T3.8: `skills/linear-implement-feature/SKILL.md` — already uses worktrees, no change needed (verify only)

**Cleanup skills (launcher invariant)**:
- [ ] T3.9: Update `skills/parallel-cleanup-feature/SKILL.md` — add worktree setup for merge/archive, teardown + GC at end
- [ ] T3.10: Update `skills/linear-cleanup-feature/SKILL.md` — same pattern as T3.9

**Documentation**:
- [ ] T3.11: Update `docs/two-level-parallel-agentic-development.md` with two-layer isolation model and launcher invariant
- [ ] T3.12: Update `CLAUDE.md` worktree section to reference launcher invariant

### T4: Integration Testing (`wp-integration`)

- [ ] T4.1: End-to-end test: worktree setup → dispatch → merge → teardown lifecycle
- [ ] T4.2: Test vendor isolation flag propagation from agents.yaml
- [ ] T4.3: Test merge conflict detection and scope violation reporting
- [ ] T4.4: Test degraded mode (no vendor isolation, cd-only)
- [ ] T4.5: Test multiple orchestrators from same checkout (launcher invariant)
- [ ] T4.6: Test root package worktree lifecycle (setup → implement → merge → teardown)
- [ ] T4.7: Test planning worktree reuse by implementation
- [ ] T4.8: Verify existing worktree tests still pass
- [ ] T4.9: Run `openspec validate --strict` on updated specs

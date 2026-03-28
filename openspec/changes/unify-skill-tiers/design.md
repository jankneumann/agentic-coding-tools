# Design: Unify Skill Tiers

## Architecture Decision: Tiered Execution Model

### Context

Each skill currently exists in two forms (linear and parallel) with a binary fallback. We need a graduated approach that preserves valuable artifacts across all tiers.

### Decision

Introduce a three-tier execution model within each unified skill. Tier selection happens at Step 0 based on coordinator detection and feature complexity analysis.

### Tier Selection Logic

```
Step 0: Run check_coordinator.py --json

If COORDINATOR_AVAILABLE and all required capabilities present:
  → TIER = "coordinated"

Else if work-packages.yaml exists OR feature has 3+ independent tasks:
  → TIER = "local-parallel"

Else:
  → TIER = "sequential"
```

The tier is set once at skill start and governs which steps execute. Steps are annotated with `[coordinated]`, `[local-parallel+]`, or `[all tiers]` markers.

### Tier Capabilities Matrix

| Capability | Sequential | Local Parallel | Coordinated |
|-----------|-----------|---------------|-------------|
| Contracts generation | No | Yes | Yes |
| Work-packages.yaml | No | Yes | Yes |
| Change context / RTM | Yes | Yes | Yes |
| DAG execution | No | Agent tool | Coordinator |
| Per-package worktrees | No | Yes | Yes |
| Context slicing | No | Yes | Yes |
| Scope enforcement | No | Prompt-based | Lock-based |
| Resource claims | No | No | Yes |
| Cross-feature locks | No | No | Yes |
| Multi-vendor review | No | No | Yes |
| Merge queue | No | No | Yes |
| Evidence completeness | No | Yes | Yes |

## Architecture Decision: Skill Directory Structure

### Decision

Keep the base skill names as canonical directories. Remove `linear-*` and `parallel-*` directories. Add their trigger phrases to the unified skills.

**Before:**
```
skills/
  plan-feature/SKILL.md          (alias → linear-plan-feature)
  linear-plan-feature/SKILL.md   (canonical linear)
  parallel-plan-feature/SKILL.md (canonical parallel)
```

**After:**
```
skills/
  plan-feature/SKILL.md          (unified, all tiers)
```

### Rationale

- Single source of truth per workflow stage
- No alias confusion
- Backward-compatible triggers cover all old invocations
- `parallel-review-*` skills remain separate (they are utilities called by implement-feature, not standalone workflow stages)

## Architecture Decision: install.sh Deprecated Skill Cleanup

### Decision

Add a `DEPRECATED_SKILLS` array to `install.sh`. Before installing current skills, iterate over deprecated names and remove matching directories from agent config dirs (`.claude/skills/`, `.codex/skills/`, `.gemini/skills/`). Only remove directories that were installed by the script (match source skill structure), never user-created content.

### Safety mechanism

To avoid deleting user-managed skills, the cleanup only removes a directory if:
1. The skill name appears in the `DEPRECATED_SKILLS` list, AND
2. The directory contains a `SKILL.md` file (our marker for managed skills)

### Deprecated skills list

```bash
DEPRECATED_SKILLS=(
  linear-plan-feature
  linear-implement-feature
  linear-explore-feature
  linear-validate-feature
  linear-cleanup-feature
  linear-iterate-on-plan
  linear-iterate-on-implementation
  parallel-plan-feature
  parallel-implement-feature
  parallel-explore-feature
  parallel-validate-feature
  parallel-cleanup-feature
)
```

## Architecture Decision: Trigger Consolidation

### Decision

Each unified skill absorbs all triggers from its linear and parallel counterparts:

**plan-feature triggers:**
```yaml
triggers:
  - "plan feature"
  - "plan a feature"
  - "design feature"
  - "propose feature"
  - "start planning"
  - "linear plan feature"
  - "parallel plan feature"
  - "parallel plan"
  - "plan parallel feature"
```

Similar merging for all other skills. The `linear-*` and `parallel-*` trigger phrases invoke the same unified skill.

## Architecture Decision: Local Parallel DAG Execution

### Decision

When tier is `local-parallel` and `work-packages.yaml` exists, implement-feature uses the built-in Agent tool for DAG execution:

1. Parse work-packages.yaml and compute topological order (same as coordinated tier)
2. Execute root packages sequentially in per-package worktrees
3. Merge root packages into feature branch
4. Dispatch independent packages as parallel Agent calls with `run_in_background=true`
5. Each agent prompt includes:
   - Package scope (`write_allow`, `read_allow`, `deny` globs)
   - Relevant context slice (contracts, specs subset)
   - Worktree path and branch
   - Verification steps from work-packages.yaml
6. Collect Agent results, run integration merge
7. Run full verification suite

### Differences from coordinated tier

- No `acquire_lock()` / `release_lock()` — scope enforcement is prompt-based
- No `discover_agents()` — use Agent tool completion notifications
- No `get_work()` / `complete_work()` — direct Agent dispatch
- No multi-vendor review dispatch — single-vendor self-review only
- No merge queue — direct git merge

### Differences from sequential tier

- Work is decomposed into packages with explicit scopes
- Independent packages run concurrently via Agent tool
- Context slicing reduces per-agent context window usage
- Per-package verification catches issues earlier

# Design: Unify Skill Tiers

## Architecture Decision: Tiered Execution Model

### Context

Each skill currently exists in two forms (linear and parallel) with a binary fallback. We need a graduated approach that preserves valuable artifacts across all tiers.

### Decision

Introduce a three-tier execution model within each unified skill. Tier selection happens at Step 0 based on coordinator detection, feature complexity, and user intent.

### Tier Selection Logic

Tier detection differs by skill phase:

**plan-feature** (artifacts don't exist yet):
```
Step 0: Run check_coordinator.py --json

If COORDINATOR_AVAILABLE and all required capabilities present:
  → TIER = "coordinated"

Else if user invoked via "parallel plan" trigger OR feature touches 2+ architectural boundaries:
  → TIER = "local-parallel"

Else:
  → TIER = "sequential"
```

**implement-feature** (artifacts may already exist from planning):
```
Step 0: Run check_coordinator.py --json

If COORDINATOR_AVAILABLE and all required capabilities present:
  → TIER = "coordinated"

Else if work-packages.yaml exists at openspec/changes/<change-id>/:
  → TIER = "local-parallel"

Else if tasks.md has 3+ independent tasks with non-overlapping file scopes:
  → TIER = "local-parallel"

Else:
  → TIER = "sequential"
```

**Tier override**: If the user invoked via a `parallel-*` trigger phrase (e.g., "parallel plan feature"), the skill SHALL select at least the local-parallel tier regardless of complexity analysis.

**Tier notification**: At startup, the skill SHALL emit a status line indicating the selected tier and rationale, e.g.:
```
Tier: local-parallel — coordinator unavailable, generating contracts and work-packages for local DAG execution
```

The tier is set once at skill start and governs which steps execute. Steps are annotated with `[coordinated only]`, `[local-parallel+]`, or `[all tiers]` markers.

### Tier Capabilities Matrix

| Capability | Sequential | Local Parallel | Coordinated |
|-----------|-----------|---------------|-------------|
| Contracts generation | No | Yes | Yes |
| Work-packages.yaml | No | Yes | Yes |
| Change context / RTM | Yes | Yes | Yes |
| DAG execution | No | Agent tool | Coordinator |
| Per-package worktrees | No | No | Yes |
| Context slicing | No | Yes | Yes |
| Scope enforcement | No | Prompt-based | Lock-based |
| Resource claims | No | No | Yes |
| Cross-feature locks | No | No | Yes |
| Multi-vendor review | No | No | Yes |
| Merge queue | No | No | Yes |
| Evidence completeness | No | Yes | Yes |

Note: Local-parallel uses a **single feature worktree** (same as sequential) with prompt-based scope constraints for dispatched agents. Per-package worktrees are coordinated-tier only, where lock management prevents merge conflicts.

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

## Architecture Decision: Infrastructure Script Relocation

### Context

Scripts currently in `parallel-implement-feature/scripts/` are imported by multiple skills (`auto-dev-loop`, `fix-scrub`, `merge-pull-requests`) via `sys.path` manipulation. Deleting `parallel-implement-feature/` would break these imports.

### Decision

Split shared scripts into two non-user-invocable infrastructure skills:

**`coordination-bridge`** (existing, expanded):
- Already has `scripts/coordination_bridge.py` for HTTP fallback
- Gains `check_coordinator.py` (moved from 4 duplicated copies in `parallel-*/scripts/`)
- Responsibility: "Can I talk to the coordinator?"

**`parallel-infrastructure`** (new):
- `scripts/dag_scheduler.py` — DAG computation and topological sort
- `scripts/scope_checker.py` — Post-execution scope verification
- `scripts/package_executor.py` — Work package execution protocol
- `scripts/review_dispatcher.py` — Multi-vendor review dispatch
- `scripts/consensus_synthesizer.py` — Review finding synthesis
- `scripts/integration_orchestrator.py` — Cross-package integration
- `scripts/result_validator.py` — Work-queue result validation
- `scripts/circuit_breaker.py` — Fault tolerance for external calls
- `scripts/escalation_handler.py` — Escalation protocol
- `scripts/tests/` — Test suite for the above
- `scripts/__init__.py`, `scripts/__main__.py`
- Responsibility: "How do I run work packages?"
- `user_invocable: false`

### Import path migration

All consumers (`auto-dev-loop`, `fix-scrub`, `merge-pull-requests`, `implement-feature`) update their `sys.path` references from:
```python
sys.path.insert(0, "skills/parallel-implement-feature/scripts")
```
to:
```python
sys.path.insert(0, "skills/parallel-infrastructure/scripts")
```

### Rationale

- `coordination-bridge` is about coordinator detection and HTTP fallback — adding `check_coordinator.py` fits naturally
- `parallel-infrastructure` is about execution machinery — DAG scheduling, review, consensus — useful even without a coordinator (local-parallel tier)
- Clean separation: detection vs. execution
- Both are non-user-invocable infrastructure skills

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

Similar merging for all other skills. The `linear-*` and `parallel-*` trigger phrases invoke the same unified skill. Parallel-prefixed triggers additionally signal a tier override to at least local-parallel.

## Architecture Decision: Local Parallel DAG Execution

### Decision

When tier is `local-parallel` and `work-packages.yaml` exists, implement-feature uses the built-in Agent tool for DAG execution within a **single feature worktree**:

1. Parse work-packages.yaml and compute topological order (same as coordinated tier)
2. Execute root packages sequentially (in the feature worktree)
3. Dispatch independent packages as parallel Agent calls with `run_in_background=true`
4. Each agent prompt includes:
   - Package scope (`write_allow`, `read_allow`, `deny` globs) for prompt-based enforcement
   - Relevant context slice (contracts, specs subset)
   - "Do NOT commit — the orchestrator will handle commits"
   - Verification steps from work-packages.yaml
5. Collect Agent results
6. Run scope check to verify agents stayed within declared boundaries
7. Run full verification suite

### Differences from coordinated tier

- Single worktree, not per-package worktrees
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

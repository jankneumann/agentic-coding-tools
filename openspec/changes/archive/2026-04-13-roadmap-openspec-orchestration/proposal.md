# Proposal: Roadmap-Oriented OpenSpec Planning and Execution

**Change ID**: `roadmap-openspec-orchestration`
**Status**: Draft
**Created**: 2026-04-13
**Updated**: 2026-04-13 (iteration 3)
**Author**: Codex

## Why

Large model-authored strategy markdown (Claude Chat / Perplexity / ChatGPT Pro) is rich in intent but too coarse for direct implementation. Today, `/plan-feature` and `/autopilot` are optimized for one change at a time. We are missing a roadmap-level layer that can:

1. Decompose one long proposal into multiple OpenSpec changes with explicit ordering.
2. Execute those changes iteratively while carrying forward implementation learnings.
3. Handle vendor usage limits with explicit time-vs-cost policy instead of ad hoc retries.
4. Persist context as artifacts so long programs do not depend on one model session.

## What Changes

Add two new skills and shared scripts:

1. **`plan-roadmap`**
   - Input: long markdown proposal
   - Output: roadmap artifact (`roadmap.yaml`) with candidate OpenSpec changes, dependency DAG, priority, and acceptance outcomes
   - Creates approved change scaffolds under `openspec/changes/<change-id>/`

2. **`autopilot-roadmap`**
   - Executes ready roadmap items via existing `/implement-feature`, `/iterate-on-implementation`, and review skills
   - Stores checkpoints and learning artifacts between items
   - Re-ranks remaining roadmap items from evidence after each completed item
   - Applies configurable policy when vendor/session limits are hit

3. **Shared roadmap runtime library** (`skills/roadmap-runtime/`)
   - Artifact models with JSON Schema validation (against `contracts/*.schema.json`)
   - Checkpoint save/restore/advance logic
   - Policy engine (wait vs switch vendor) with cascading failover
   - Learning-log read/write with progressive disclosure (root index + per-item entries)
   - Sanitization utilities preventing secret exposure in persisted artifacts
   - Bounded context assembly helpers

## Impact

### Affected Specs
- **New capability**: `roadmap-orchestration` (this change adds the initial spec delta)

### Affected Skills
- New: `skills/roadmap-runtime/` (shared library)
- New: `skills/plan-roadmap/`
- New: `skills/autopilot-roadmap/`
- Reused (not replaced): `explore-feature`, `plan-feature`, `autopilot`, `iterate-on-plan`, `parallel-review-plan`, `parallel-review-implementation`

### Affected Documentation
- `CLAUDE.md` (workflow table: add roadmap skill entry points, maintaining progressive disclosure)
- `docs/skills-workflow.md` (new roadmap phase entry)
- `docs/parallel-agentic-development.md` (roadmap orchestration + policy routing)

### Affected Contracts
- New: `contracts/roadmap.schema.json` — roadmap artifact schema
- New: `contracts/checkpoint.schema.json` — checkpoint state schema
- New: `contracts/learning-log.schema.json` — learning entry schema

## Approaches Considered

### Approach A: Standalone roadmap orchestrators reusing existing skills (Recommended)

Add `plan-roadmap` and `autopilot-roadmap` as orchestration skills and keep existing skills focused on single-change execution.

**Pros**
- Lowest regression risk for current workflows.
- Clear separation between roadmap planning and single-change execution.
- Easy to attach usage-limit and cost policy controls at orchestrator boundary.
- Reuses existing validation and review loops.

**Cons**
- Introduces new state artifacts and lifecycle management.
- Requires strict contracts between orchestration and delegated skills.

**Effort**: M

### Approach B: Extend `plan-feature` and `autopilot` with roadmap mode

**Pros**
- Fewer commands for users.
- Potentially less duplicated orchestration code.

**Cons**
- Expands already complex skills.
- Harder to test roadmap logic independently.
- Higher risk of regressions for existing commands.

**Effort**: M/L

### Approach C: Coordinator-only roadmap service

**Pros**
- Strong central state and scheduling.
- Uniform API surface for cloud and local agents.

**Cons**
- More coordinator complexity and deployment overhead.
- Slower iteration for roadmap behavior changes.

**Effort**: L

## Selected Approach

**Approach A** is selected.

## Explicit Planning Decisions (resolved assumptions)

1. **State canonical source**: Filesystem artifacts are canonical; coordinator state is optional acceleration cache.
2. **Policy defaults**: Default policy is `wait_if_budget_exceeded`; opt-in `switch_if_time_saved` requires configured cost ceiling.
3. **Roadmap granularity**: Target 3-12 roadmap items; items smaller than one implementable change are merged.
4. **Approval model**: User approval remains required per OpenSpec change before implementation.

## Scope Boundaries

### In Scope
- New skills, scripts, and tests for roadmap decomposition + execution.
- Roadmap artifacts (`roadmap.yaml`, `checkpoint.json`, `learning-log.md` + `learnings/`) with JSON Schema contracts.
- Usage-limit-aware scheduling policy engine with cascading vendor failover.
- Learning feedback loop with progressive disclosure (root index + per-item entries, compaction at 50 entries).
- Artifact sanitization preventing secret exposure in persisted state.
- Structured observability events for item transitions, policy decisions, and checkpoint operations.

### Out of Scope
- Auto-merge to main without existing gates.
- New coordinator transport protocols.
- Replacing current `autopilot`/`plan-feature` internals.

## Success Criteria

1. Given a long markdown proposal, `plan-roadmap` produces a dependency-aware roadmap with 3+ viable changes.
2. Roadmap execution resumes from checkpoint after interruption without duplicating completed phases.
3. Policy decisions (wait/switch) are recorded with reason, cost delta, and latency delta.
4. Completed roadmap items write learning entries that are consumed before planning the next item.
5. Existing single-change skill behavior remains backward compatible.

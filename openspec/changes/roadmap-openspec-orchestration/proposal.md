# Proposal: Roadmap-Oriented OpenSpec Planning and Execution

**Change ID**: `roadmap-openspec-orchestration`
**Status**: Draft
**Created**: 2026-04-13
**Author**: Codex

## Why

Teams increasingly start with long, model-generated strategy documents (from Claude Chat, Perplexity, or ChatGPT Pro). Those documents are rich but too broad for direct implementation. The current workflow supports planning and implementation of a single change well, but lacks a first-class way to:

1. Decompose one large markdown proposal into an adaptive roadmap of multiple OpenSpec changes.
2. Execute roadmap items with autopilot while preserving learnings between phases.
3. Optimize parallelism and vendor usage under model session/rate limits using explicit time-vs-cost policies.
4. Avoid context-window overload by externalizing progress and decisions into persistent artifacts.

## What Changes

Introduce a roadmap layer above existing OpenSpec lifecycle skills using two new orchestrator skills:

- `plan-roadmap`: Converts a long markdown proposal into a prioritized, dependency-aware roadmap of OpenSpec changes and seeds each change with scaffold artifacts.
- `autopilot-roadmap`: Executes approved roadmap changes iteratively, re-plans between phases based on implementation evidence and learned constraints.

These new skills will reuse existing capabilities from `explore-feature`, `plan-feature`, `iterate-on-plan`, `parallel-review-plan`, and `autopilot`, rather than replacing them.

## Approaches Considered

### Approach A: Standalone roadmap skills that orchestrate existing skills (Recommended)

Create `plan-roadmap` and `autopilot-roadmap` as orchestrators that call existing planning/implementation skills and add durable roadmap state.

**Pros**
- Maximizes reuse of mature skills and validation logic.
- Keeps single-change flows unchanged.
- Easiest path to cost/time policy controls at orchestration layer.
- Supports progressive context loading from artifact files and coordinator state.

**Cons**
- Requires clear contracts between orchestrator and child skills.
- Adds state-management complexity (roadmap registry, checkpoints, retries).

**Effort**: M

### Approach B: Extend `autopilot` and `plan-feature` directly with roadmap mode

Add roadmap decomposition and multi-change orchestration as optional modes in existing skills.

**Pros**
- Fewer top-level commands.
- Shared code paths by default.

**Cons**
- Increases complexity of already-heavy skills.
- Harder to reason about roadmap-specific behaviors and failure recovery.
- Higher regression risk for current workflows.

**Effort**: M/L

### Approach C: Coordinator-only roadmap engine with no new skills

Implement roadmap planning/execution as coordinator APIs and keep CLI skills thin wrappers.

**Pros**
- Strong central state and scheduling control.
- Potentially easier multi-agent observability.

**Cons**
- Larger coordinator surface area and deployment complexity.
- Slower iteration because every behavior change requires coordinator updates.

**Effort**: L

### Selected Approach

**Approach A** is selected. It matches your objective of adding roadmap-focused capabilities while reusing existing skills and introducing explicit time-vs-money controls with context-window-safe artifact handoffs.

## Scope Boundaries

### In Scope
- Skill definitions and scripts for `plan-roadmap` and `autopilot-roadmap`.
- Roadmap artifact schema and on-disk state model.
- Policy-based vendor selection and rate-limit handling.
- Learning-feedback loop from completed change artifacts back into remaining roadmap items.

### Out of Scope
- Rewriting existing `autopilot` internals end-to-end.
- New coordinator transport protocols.
- Automatic merging/deploy of roadmap outputs beyond current approval gates.

## Success Criteria

1. A long proposal markdown can be transformed into a roadmap with 3+ ordered OpenSpec changes and explicit dependencies.
2. Roadmap execution can resume after interruption using persisted checkpoints.
3. At least one execution policy can choose to wait for limits vs pay for alternate vendor based on configured cost/time threshold.
4. Each completed roadmap item writes a learning artifact consumed before planning the next item.
5. Existing single-change commands remain backward compatible.

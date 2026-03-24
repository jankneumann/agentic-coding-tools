# Proposal: Unify Worktree Isolation for Parallel Agents

**Change ID**: `unify-worktree-isolation`
**Status**: Draft
**Author**: claude-code-1
**Date**: 2026-03-24

## Summary

Fix agent conflicts by enforcing a **launcher invariant** across all skills that modify the checkout: the shared checkout is read-only; all work happens in worktrees. Combine our registry-managed worktree system (`scripts/worktree.py`) with vendor-provided agent isolation (e.g., Claude Code's `isolation: "worktree"`) into a two-layer approach that works across agent vendors. Applies to both parallel and linear skill families.

## Problem

Any skill that modifies the checkout (git add, commit, branch checkout) conflicts with other agents running from the same directory. This affects **all workflow stages**, not just implementation:

1. **Planning**: Two terminals running `/parallel-plan-feature` for different features both try to commit artifacts to the same checkout
2. **Implementation**: Parallel Agent calls share the same working directory instead of using worktrees
3. **Cleanup**: Merge/archive operations race on branch checkout and git staging

Specific failure modes:
- **Git staging conflicts**: Multiple agents running `git add`/`git commit` concurrently
- **Branch switching races**: One agent checking out a branch while another is mid-operation
- **File contention**: Even with non-overlapping write scopes, shared files like `uv.lock` can conflict

The `parallel-implement-feature` skill says "Each work package runs in its own worktree" — but this is aspirational, not enforced. And the planning and cleanup skills don't mention worktrees at all.

## Root Cause

Two isolation mechanisms exist but aren't connected:

| Layer | What exists | Who manages it | Status |
|-------|------------|----------------|--------|
| **Orchestrator worktrees** | `scripts/worktree.py` with registry, heartbeat, GC, bootstrap | Our code | Ready but never called by skill |
| **Vendor agent isolation** | Claude Code `isolation: "worktree"`, Codex sandboxes, etc. | Agent vendor | Available but not leveraged |

The orchestrator needs to bridge these two layers.

## Proposed Solution: Two-Layer Isolation

### Layer 1: Orchestrator Worktree Setup (before agent dispatch)

The orchestrator calls `scripts/worktree.py setup` for each work package **before** dispatching agents. This gives us:
- Registry tracking (who owns which worktree)
- Heartbeat monitoring (detect stuck agents)
- GC protection (pin during execution)
- Deterministic branch names (`openspec/<change-id>/<package-id>`)
- Bootstrap (venv, deps, skills sync)

### Layer 2: Vendor Agent Isolation (during agent dispatch)

When the Agent tool supports it (Claude Code does), use `isolation: "worktree"` as a **safety net**. The agent gets its own copy even if our Layer 1 setup fails or the agent drifts.

When the vendor doesn't support isolation (Codex cloud, Gemini), the agent is instructed to `cd` into the Layer 1 worktree path.

### Execution Flow

The shared checkout is a **launcher only** — no orchestrator ever modifies it directly. This prevents conflicts when multiple orchestrators run from the same checkout in different terminals.

```
Orchestrator (shared checkout — READ ONLY, never modified)
  │
  ├─ Phase 0: Create feature branch openspec/<change-id>
  │
  ├─ Phase 1: Root packages (sequential, each in own worktree)
  │   ├─ worktree.py setup <change-id> --agent-id <package-id>
  │   ├─ Implement in worktree, commit, push
  │   └─ Merge root branch into feature branch
  │
  ├─ Phase 2: Parallel packages (each in own worktree)
  │   ├─ worktree.py setup <change-id> --agent-id <package-id>
  │   │   → creates .git-worktrees/<change-id>/<package-id>/
  │   │   → branch openspec/<change-id>/<package-id>
  │   │   → bootstrap (uv sync, skills sync)
  │   │
  │   └─ Agent(prompt=..., isolation="worktree")   [if vendor supports]
  │      OR
  │      Agent(prompt="cd <worktree-path> && ...")  [if vendor doesn't]
  │
  ├─ Phase 3: Wait for all parallel packages to complete
  │
  └─ Phase 4: Integration
      ├─ worktree.py setup <change-id> --agent-id integrator
      ├─ Merge each package branch into feature branch
      ├─ Run full test suite
      └─ worktree.py teardown (all)
```

This means multiple orchestrators can safely run from the same checkout:

```
Terminal 1: orchestrator for feature-a
  └─ .git-worktrees/feature-a/{wp-contracts, wp-backend, ...}

Terminal 2: orchestrator for feature-b
  └─ .git-worktrees/feature-b/{wp-contracts, wp-frontend, ...}

Shared checkout: untouched by either
```

### Vendor Compatibility Matrix

| Vendor | Local/Cloud | Isolation Support | Layer 1 | Layer 2 |
|--------|------------|-------------------|---------|---------|
| Claude Code (CLI) | Local | `isolation: "worktree"` | Our worktree setup | Agent worktree (safety net) |
| Claude Code (Web/API) | Cloud | None (runs in sandbox) | Our worktree setup | Agent `cd`s into worktree |
| Codex (local) | Local | Unknown | Our worktree setup | Agent `cd`s into worktree |
| Codex (cloud) | Cloud | Sandbox | N/A (cloud) | Vendor sandbox |
| Gemini (local) | Local | Unknown | Our worktree setup | Agent `cd`s into worktree |

**Key principle**: Our worktree system is the **source of truth** for tracking, lifecycle, and merge coordination. Vendor isolation is a bonus safety layer, not a replacement.

## Scope

### In Scope

**Skills that modify the checkout** (launcher invariant required):

| Skill | Current State | Change Needed |
|-------|--------------|---------------|
| `parallel-plan-feature` | Works on shared checkout | Use feature-level worktree for artifact creation |
| `parallel-implement-feature` | Describes worktrees but never creates them | Enforce worktree-per-package |
| `parallel-cleanup-feature` | Merges on shared checkout | Use worktree for merge/archive |
| `linear-plan-feature` | Works on shared checkout | Use feature-level worktree |
| `linear-implement-feature` | Already uses worktree (single) | No change (already correct) |
| `linear-cleanup-feature` | Works on shared checkout | Use worktree for merge/archive |

**Skills that are read-only** (no change needed):
- `parallel-explore-feature`, `linear-explore-feature` — read-only analysis
- `parallel-review-plan`, `parallel-review-implementation` — read-only review
- `parallel-validate-feature`, `linear-validate-feature` — read-only verification

Additional changes:
- Add integration merge protocol (`scripts/merge_worktrees.py`)
- Add vendor isolation config to `agents.yaml`
- Handle vendor isolation gracefully (use when available, skip when not)
- Update `docs/two-level-parallel-agentic-development.md`
- Tests for the updated orchestration flow

### Out of Scope

- Changing `scripts/worktree.py` core logic (already production-ready)
- Adding new vendor integrations
- Cloud agent worktree management (cloud agents use vendor sandboxes)
- Changing the DAG scheduler or work queue protocol
- Read-only skills (explore, review, validate)

## Success Criteria

1. **No agent ever modifies the shared checkout** — it is a read-only launcher
2. Every package (including root packages) runs in its own worktree
3. Each package's work is on a separate, named branch
4. Multiple orchestrators can run from the same checkout without conflict
5. Integration merge produces a clean feature branch
6. Worktree registry accurately tracks all active agents
7. GC can reclaim worktrees after completion
8. Works with Claude Code's `isolation: "worktree"` as safety net
9. Degrades to `cd`-into-worktree for vendors without isolation support

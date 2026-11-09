# Handoff Proposal: Continuous Integration for Agentic Workflows

**Repo**: [jankneumann/agentic-coding-tools](https://github.com/jankneumann/agentic-coding-tools)  
**Author**: Jan Neumann (with Grok)  
**Date**: 2026-11-01  
**Status**: Proposal — ready for OpenSpec `/plan-feature` or direct implementation  
**Goal**: Unblock merges, shift from big-bang feature PRs to continuous small landings, and elevate AI review to the primary quality gate — without sacrificing the safety rails that already exist.

---

## 1. Problem Statement

The current process is stuck in a high-WIP trap:

- **Global locking semantics**: Active work (claims held by any agent/feature) blocks merges across the board. Because there is almost always active work, nothing merges.
- **Large feature units**: OpenSpec features land as large PRs. Integration is therefore a big bang rather than a stream of small, verified increments.
- **Result**: 10–20 unresolved mergers accumulate while new work continues. AI reviews after planning and implementation stages already succeed, but they are subordinated to the freeze. Feedback loops are delayed, and the system fails to demonstrate the acceleration a 5–10 person team would need.

This recreates the classic PR bottleneck under a new name, even though agents make the meta-work of small increments (feature flags, dual-running migrations, incremental refactors) cheap.

## 2. Desired End State

- Non-overlapping changes can merge while other work continues.
- The primary unit of integration is a small, independently landable slice (behind a flag or as a non-breaking step), not a complete feature.
- Successful multi-vendor AI review + CI is sufficient to land low-risk changes; humans (or high-scrutiny agents) intervene only on high-risk surfaces or conflicts.
- Merge readiness is independent of “any active work exists.”
- A documented “solo / small-team continuous” mode exists that a 5–10 person team can adopt as a reference.

Quality is preserved via existing CI, AI review, feature flags, fast reverts, and thread/OpenSpec linkage — not via global freezes.

## 3. Proposed Changes

### 3.1 Decouple active work from merge eligibility

**Target**: `agent-coordinator` merge queue + claim logic (`merge_queue.py`, `merge_train.py`, claim/lock tables).

- An active claim blocks only overlapping resources (same lock prefix or same files).
- Non-overlapping partitions continue to be eligible for speculative trains and actual merges.
- Remove or demote any global “active work → no merges” gate.
- Keep the fail-closed execute kernel for the actual merge step.

**Acceptance**: A feature holding a claim on `api:users` does not prevent a ready feature that only touches `docs/` or `flag:new-ui` from landing.

### 3.2 Force smaller integration units

**Targets**: `/plan-feature`, `/implement-feature`, `/quick-task`, OpenSpec work-package guidance.

- Prefer (or constrain, in continuous mode) work packages that can land independently.
- Expand `/quick-task` and add a lightweight “land-slice” path that does not require a full OpenSpec feature ceremony.
- Explicitly encourage feature flags and dual-running patterns in planning skills; agents already handle this well.
- Keep rebase-merge for agent-authored small logical commits.

**Acceptance**: Median landed change size drops; features routinely land as a series of trunk commits/PRs rather than one large PR.

### 3.3 Elevate AI review + CI to primary merge gate

**Targets**: `merge-pull-requests` skill, parallel-review skills, merge-plan logic.

- Changes that pass multi-vendor AI review (plan and/or implementation), CI, and have no overlapping active claims become auto-enqueueable or auto-mergeable (with optional one-click confirmation).
- High-risk surfaces (auth, migrations, public APIs, security-sensitive paths) remain human-gated or high-scrutiny.
- Every landing records a link back to the agent thread and/or OpenSpec change-id for auditability.

**Acceptance**: Low-risk, reviewed, non-overlapping changes no longer wait for a human or for global quiet.

### 3.4 Continuous rebase-and-land

**Targets**: Merge queue / train service, rebase coordination.

- Speculative trains actually land non-overlapping partitions as soon as they pass verification.
- Ready items are automatically rebased onto current main (agents handle routine conflicts).
- Fast reverts are treated as a first-class recovery mechanism.

**Acceptance**: Time-to-land for a ready, non-overlapping slice is measured in minutes/hours, not days.

### 3.5 Explicit “solo / small-team continuous” mode

**Targets**: Multiplayer collaboration guide, skill defaults, documentation.

- A mode (flag, config, or skill parameter) that defaults to smaller slices, AI-primary gates, and non-blocking locks.
- Surfaces “merge readiness” independently of “other work active.”
- Documents the quality rails so the mode is usable as a reference implementation for a 5–10 person team.

**Acceptance**: A new contributor or team can enable the mode and understand the expected velocity/quality trade-off from the docs alone.

## 4. Suggested Work Packages (for OpenSpec)

1. **Coordinator lock & queue semantics** — Change claim checks so only overlapping resources block; update tests for merge queue and trains.
2. **Continuous mode flag & defaults** — Add config/skill parameter; wire it into planning and merge skills.
3. **AI-primary auto-enqueue path** — Extend merge-plan / execute kernel to auto-progress low-risk, reviewed, non-overlapping items.
4. **Small-slice guidance in skills** — Update `/plan-feature` and `/implement-feature` prompts/constraints; strengthen `/quick-task`.
5. **Documentation & reference guide** — Update multiplayer guide, workflow docs, and add a short “Continuous Integration for Agentic Teams” note that can be shared externally.
6. **Observability** — Expose merge-readiness metrics and “blocked-only-by-overlap” vs “blocked-by-global-lock” distinction.

## 5. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Overlapping changes land out of order and create subtle bugs | Keep speculative trains + pre-merge conflict re-validation; fast reverts; feature flags |
| AI review misses a high-risk issue | Explicit high-risk surface list remains human-gated; existing multi-vendor review is retained |
| Smaller slices increase noise | Conventional commits + OpenSpec change-id linkage keep history navigable; squash still available for dependency/automation PRs |
| Solo mode is too aggressive for a real team | Mode is opt-in; quality rails are documented; team can start with AI-primary but human-confirm |

## 6. Success Criteria

- Open PRs no longer accumulate solely because other work is active.
- At least one non-overlapping slice can land while another feature holds claims.
- Median time from “AI review green + CI green” to landed drops significantly.
- A short external note exists that a 5–10 person team could use as a starting point.
- No regression in existing CI, security, or OpenSpec contract validation.

## 7. Next Steps

1. Create an OpenSpec change (e.g. `openspec/changes/continuous-integration-for-agents/`) from this proposal.
2. Run `/plan-feature` (or equivalent) to refine work packages and contracts.
3. Implement coordinator lock changes first — they unblock everything else.
4. Add the continuous mode and AI-primary path.
5. Update docs and validate with a real feature landing under the new rules.

---

**This proposal is intentionally implementation-oriented.** It can be dropped into an OpenSpec proposal or used directly as the starting brief for an agent-driven implementation pass. The existing safety rails (CI, multi-vendor review, flags, reverts, thread linkage) stay; the global freeze and big-bang unit of integration go.

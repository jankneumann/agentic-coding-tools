# Proposal: Universal Planning Artifacts

**Change ID**: `universal-planning-artifacts`
**Date**: 2026-04-03
**Status**: Draft

## Why

The current tiered planning model skips contracts and work-packages for sequential-tier features. This creates two problems:

1. **Broken parallel reviews at merge time**: When `/merge-pull-requests` dispatches multi-vendor reviews (Claude, Codex, Gemini) via `/parallel-review-implementation`, the skill assumes work-packages exist to scope per-package reviews. Sequential-tier PRs lack these artifacts, so structured review dispatch fails silently — vendors can't scope their analysis without package definitions.

2. **Lost constraint value in sequential implementation**: Contracts define machine-readable interface boundaries (OpenAPI, DB schemas, event schemas) that serve as guardrails during implementation. Sequential-tier features miss this — tests can't assert against contracted interfaces, and there's no formal validation that the implementation matches the designed surface area.

3. **Friction when upgrading tiers**: A feature planned sequentially can't later be parallelized without re-running planning to generate the missing artifacts. The artifacts should always be present so `/implement-feature` can opportunistically parallelize.

## What Changes

### 1. Always generate contracts and work-packages during planning (plan-feature)

- Remove `[local-parallel+]` tier gate from Steps 7 and 8 — make them `[all tiers]`
- For sequential-tier plans, work-packages contain a single `wp-main` package covering the full feature scope (no parallelization, but the artifact exists for reviews and constraints)
- Contracts are full-fidelity regardless of tier — same OpenAPI, DB schema, event schema artifacts

### 2. Whole-branch review fallback in parallel-review-implementation

- When `work-packages.yaml` is missing (legacy PRs, external contributions, pre-change PRs), fall back to treating the entire diff as a single review unit
- Vendors receive the full branch diff as context instead of per-package scoped diffs
- Scope verification (Step 2) is skipped when no package definition exists

### 3. Implement-feature always consumes contracts as input constraints

- Sequential-tier implementation reads contracts to validate interface conformance
- The Requirement Traceability Matrix (Step 3a) always maps requirements to contract refs
- Failing tests assert against contracted schemas, not just behavioral expectations

### 4. Update CLAUDE.md tier table and documentation

- The "Planning Artifacts" column for sequential tier changes from "Tasks.md only" to "Tasks.md + contracts + work-packages (single package)"
- Update the context slicing table in plan-feature to include sequential tier

## Approaches Considered

### Approach 1: Universal Artifacts with Single-Package Fallback (Recommended)

**Description**: Always generate full-fidelity contracts and work-packages during planning. Sequential-tier features get a single `wp-main` package that encompasses the entire feature scope, using the same artifact format as parallel tiers.

**Pros**:
- Unified artifact format — every change has contracts and work-packages regardless of tier
- Reviews, implementation, and validation skills can assume artifacts exist (no conditional paths)
- Sequential features can be upgraded to parallel mid-implementation by splitting `wp-main`
- Tests always validate against contracted interfaces

**Cons**:
- Slightly more planning time for simple sequential features (generating contracts + single work-package)
- `wp-main` is a degenerate work-package (no parallelization benefit) — could mislead about complexity

**Effort**: M

### Approach 2: Lazy Generation on Demand

**Description**: Keep the tier-based skip logic in planning, but add lazy generation to skills that need the artifacts. When `/merge-pull-requests` dispatches a review and finds no work-packages, it auto-generates them from the existing diff. When `/implement-feature` finds no contracts, it generates them from specs.

**Pros**:
- No change to the planning flow — minimal skill disruption
- Artifacts are generated only when actually needed

**Cons**:
- Duplicated generation logic across multiple skills (DRY violation)
- Late-generated artifacts haven't been reviewed as part of the plan — quality risk
- Race conditions if multiple skills try to generate simultaneously
- The generated artifacts won't match what would have been produced during planning (different context)

**Effort**: L

### Approach 3: Tier-Aware Optional Consumption

**Description**: Keep artifacts optional but make every consuming skill handle both cases gracefully. Add explicit "with contracts" vs "without contracts" code paths to implement-feature, parallel-review-implementation, and merge-pull-requests.

**Pros**:
- Backward compatible — existing sequential plans work unchanged
- Each skill decides independently how much value contracts add

**Cons**:
- Every consuming skill needs conditional logic (4+ skills affected)
- Testing matrix doubles (with/without artifacts for each tier)
- Ongoing maintenance burden as new skills are added — each must handle both paths
- Doesn't solve the "lost constraint value" problem for sequential features

**Effort**: M

## Scope

### In Scope
- `skills/plan-feature/SKILL.md` — Remove tier gates on Steps 7-8
- `skills/parallel-review-implementation/SKILL.md` — Add whole-branch fallback
- `skills/implement-feature/SKILL.md` — Always consume contracts
- `skills/merge-pull-requests/SKILL.md` — Document review behavior with universal artifacts
- `CLAUDE.md` — Update tier table
- `openspec/specs/skill-workflow/spec.md` — Spec amendments
- `openspec/specs/merge-pull-requests/spec.md` — Spec amendments

### Out of Scope
- Changes to the coordinator or agent-coordinator codebase
- Changes to parallel-infrastructure scripts (review_dispatcher.py, consensus_synthesizer.py) — these are already artifact-agnostic
- Schema changes to `work-packages.schema.json` — the single-package pattern already conforms
- Changes to validate-packages scripts — `wp-main` validates against existing schema

## Selected Approach

**Approach 1: Universal Artifacts with Single-Package Fallback** — selected because:
- Contracts and work-packages are most useful when created during planning, where they benefit from the full proposal/design context
- A single `wp-main` package is the correct degenerate case — it's a valid work-package that happens to cover everything
- Consuming skills can drop conditional "if artifacts exist" logic, simplifying maintenance
- The additional planning time for sequential features is minimal (contracts are derived from specs, `wp-main` is a template fill)

### Other Approaches

- **Lazy Generation**: Rejected — duplicated generation logic, quality risk from late generation, race conditions
- **Tier-Aware Optional**: Rejected — ongoing maintenance burden, doesn't solve the constraint value problem

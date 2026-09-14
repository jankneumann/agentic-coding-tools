# Tasks: retire-skill-literal-model-hints

> Migrated from `consolidate-model-tier-sources` F1 during post-merge cleanup
> on 2026-09-14 (PR #538). Scaffold only — expand via `/plan-feature` before
> implementation.

## 0. Planning (complete the proposal)

**Dependencies**: none — parent Phase 1 is merged.

- [ ] 0.1 Expand this change with full `design.md`, work packages, and spec
      deltas (drop `skip_specs` when requirements are ready)
      **Files**: `openspec/changes/retire-skill-literal-model-hints/`

## 1. Inventory and replace literals (from parent F1)

**Dependencies**: 0.1
**Files**: `skills/**/SKILL.md`, related skill scripts/docs, optional
`skills/tests/` grep-guard

- [ ] F1 Inventory skill `Task()` / `Agent()` / CLI `-m` model literals and
      replace them with archetype/tier resolution (Phase 2 of
      `consolidate-model-tier-sources`)
- [ ] F1a Add a CI/contract guard that fails on new policy-pinning literals
      (with an explicit allowlist if illustrative prose must remain)

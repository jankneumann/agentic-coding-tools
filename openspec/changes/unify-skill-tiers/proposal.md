# Proposal: Unify Skill Tiers

**Change ID**: `unify-skill-tiers`
**Status**: Draft
**Created**: 2026-03-28

## Problem

The current skill architecture maintains two separate families — `linear-*` and `parallel-*` — for each workflow stage (plan, implement, explore, validate, cleanup). When the coordinator is unavailable, parallel skills hard-fallback to their linear equivalents, discarding all parallel-specific artifacts:

- **Contracts** (OpenAPI, DB schemas, event schemas, generated types)
- **Work-packages.yaml** (DAG-structured decomposition with scopes, locks, dependencies)
- **Change context** (Requirement Traceability Matrix, Design Decision Trace)
- **Resource claim analysis** (feasibility assessment)
- **Evidence completeness checking**

These artifacts are valuable even without a coordinator — they provide structured decomposition, interface boundaries, context slicing for within-feature Agent parallelism, and verification guidance.

Additionally, the dual skill families create maintenance burden: 10+ SKILL.md files that overlap significantly, confusing user-facing skill names, and an `install.sh` that installs both sets without cleanup.

## Solution

Consolidate into a single set of unified skills with **tiered execution**:

| Tier | Trigger | Planning | Execution |
|------|---------|----------|-----------|
| **Coordinated** | Coordinator available | Contracts + work-packages + resource claims | Multi-agent DAG via coordinator |
| **Local parallel** | No coordinator, complex feature | Contracts + work-packages (no claims) | DAG via built-in Agent parallelism |
| **Sequential** | Simple feature / few tasks | Tasks.md only | Single-agent sequential |

The base skill names (`plan-feature`, `implement-feature`, etc.) become canonical. Both `linear-*` and `parallel-*` prefixes become backward-compatible trigger aliases in the unified skills. The separate `linear-*` and `parallel-*` skill directories are removed, and `install.sh` gains a deprecated-skill cleanup mechanism.

## Scope

### In scope
- Merge parallel artifacts (contracts, work-packages, DAG execution) into base skills
- Add tiered execution detection (coordinated / local-parallel / sequential)
- Relocate shared scripts into two infrastructure skills:
  - `coordination-bridge` — gains `check_coordinator.py` (coordinator detection)
  - New `parallel-infrastructure` — homes DAG scheduler, review dispatcher, consensus synthesizer, scope checker, and other parallel execution machinery
- Update `install.sh` with deprecated skill removal
- Update `auto-dev-loop`, `fix-scrub`, `merge-pull-requests` import paths to reference new script locations
- Update `CLAUDE.md` workflow documentation
- Remove deprecated `linear-*` and `parallel-*` skill directories
- Preserve `parallel-review-plan` and `parallel-review-implementation` (used by implementation phase)

### Out of scope
- Changes to the coordinator itself
- Changes to the OpenSpec CLI or schemas
- Changes to worktree management scripts
- New coordinator capabilities
- Renaming `parallel-review-*` skills (deferred to follow-up)

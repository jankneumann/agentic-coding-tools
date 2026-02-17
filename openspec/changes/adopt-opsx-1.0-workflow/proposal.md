# Change: Adopt OpenSpec 1.0 OPSX Workflow

## Why

OpenSpec 1.0 introduces a configuration-driven system (OPSX) with schema-defined artifact dependency graphs, per-artifact rules, project context injection, and granular commands (`opsx:explore`, `opsx:new`, `opsx:continue`, `opsx:ff`, `opsx:apply`, `opsx:sync`, `opsx:archive`). Our current skills hard-code artifact management logic that OPSX now handles natively. Adopting OPSX lets us define custom artifact types (exploration reports, iteration findings, validation reports, deferred task lists) as first-class schema nodes with dependency tracking, while simplifying skill implementations by delegating artifact lifecycle to the framework.

## What Changes

### Configuration Layer
- Add `openspec/config.yaml` with schema selection, project context, and per-artifact rules
- Create custom schema `feature-workflow` at `openspec/schemas/feature-workflow/` with artifact dependency graph extending `spec-driven` with `exploration`, `plan-findings`, `impl-findings`, `validation-report`, and `deferred-tasks` artifacts
- Add artifact templates for each custom artifact type

### Skills Layer — OPSX Command Integration
- **`/plan-feature`**: Replace inline `openspec-proposal` call with `opsx:explore` for context gathering + `opsx:ff` (or `opsx:new` + `opsx:continue`) for artifact creation
- **`/iterate-on-plan`**: Produce `plan-findings` artifact via `opsx:continue`; use OPSX state tracking for iteration progress
- **`/implement-feature`**: Replace `openspec-apply` call with `opsx:apply`; remove inline task-tracking logic that OPSX handles
- **`/iterate-on-implementation`**: Produce `impl-findings` artifact via `opsx:continue`; same pattern as plan iteration
- **`/validate-feature`**: Register `validation-report` as OPSX artifact; write report via OPSX artifact creation
- **`/cleanup-feature`**: Replace `openspec-archive` call with `opsx:sync` + `opsx:archive`; produce `deferred-tasks` artifact for migrated open tasks

### Skills Layer — Retirement
- **`/openspec-proposal`**: Retire in favor of `opsx:new` / `opsx:ff` (keep as thin redirect during transition)
- **`/openspec-apply`**: Retire in favor of `opsx:apply`
- **`/openspec-archive`**: Retire in favor of `opsx:archive`

### Documentation
- Update `openspec/AGENTS.md` to reference OPSX commands and the `feature-workflow` schema
- Update `CLAUDE.md` OpenSpec section to reference OPSX 1.0

## Impact

- Affected specs: `skill-workflow`
- Affected code: All 6 core skills (`plan-feature`, `iterate-on-plan`, `implement-feature`, `iterate-on-implementation`, `validate-feature`, `cleanup-feature`), 3 retired skills (`openspec-proposal`, `openspec-apply`, `openspec-archive`), `openspec/AGENTS.md`, `CLAUDE.md`
- No breaking changes to the external workflow — skill names and approval gates remain identical
- Requires OpenSpec CLI upgrade to 1.0+

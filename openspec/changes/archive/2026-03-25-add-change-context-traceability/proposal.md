# Proposal: Add change-context.md Traceability Artifact

## Why

PR reviews are difficult because the relationship between spec requirements, code changes, tests, and validation evidence is scattered across 4-5 separate artifacts (proposal.md, design.md, tasks.md, specs/, validation-report.md). Reviewers must manually reconstruct the spec-to-code-to-test mapping. Additionally, the current TDD guidance in implement-feature is weak (3-line advisory note at line 128) and disconnected from spec requirements — tests are routinely written after implementation to match code rather than derived from specs first.

## What Changes

- **New artifact**: `change-context.md` — a structured traceability matrix mapping spec requirements to code, tests, and validation evidence, built incrementally in 3 phases (test plan → implementation → validation)
- **TDD enforcement**: Structural integration of test-driven development into the implementation workflow — tests derived from spec scenarios before code is written
- **Validation report refactoring**: Spec compliance section of `validation-report.md` replaced with reference to `change-context.md`, eliminating duplication
- **Skill updates**: Modified instructions in 5 skills (linear-implement-feature, linear-iterate-on-implementation, linear-validate-feature, parallel-implement-feature, parallel-validate-feature)
- **Schema + config**: New artifact entry in `schema.yaml` and rules in `config.yaml`

## Impact

### Affected Specs
- `skill-workflow` — delta: `specs/skill-workflow/spec.md` (new requirements for change-context artifact and TDD enforcement)

### Affected Architecture Layers
- **Execution** — Skill instruction files that guide agent behavior during implementation and validation
- **Governance** — OpenSpec schema and config that define artifact conventions

### Affected Code/Files
- `openspec/schemas/feature-workflow/templates/change-context.md` (NEW)
- `openspec/schemas/feature-workflow/schema.yaml` (MODIFY)
- `openspec/config.yaml` (MODIFY)
- `openspec/schemas/feature-workflow/templates/validation-report.md` (MODIFY)
- `skills/linear-implement-feature/SKILL.md` (MODIFY)
- `skills/linear-iterate-on-implementation/SKILL.md` (MODIFY)
- `skills/linear-validate-feature/SKILL.md` (MODIFY)
- `skills/parallel-implement-feature/SKILL.md` (MODIFY)
- `skills/parallel-validate-feature/SKILL.md` (MODIFY)

## Rollback Plan

All changes are to markdown instruction files and YAML config — no runtime code. Rollback is a simple revert of the commit. Pre-existing changes without `change-context.md` continue to work because `validate-feature` generates the skeleton on-the-fly if missing.

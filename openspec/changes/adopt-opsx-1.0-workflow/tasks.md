# Tasks: Adopt OpenSpec 1.0 OPSX Workflow

## 1. OpenSpec 1.0 Setup

- [ ] 1.1 Install OpenSpec 1.0 CLI and verify `opsx:*` commands are available
  **Dependencies**: None
  **Files**: package.json or install script (external)

## 2. Custom Schema Definition

- [ ] 2.1 Create `openspec/schemas/feature-workflow/schema.yaml` with artifact dependency graph
  **Dependencies**: 1.1
  **Files**: openspec/schemas/feature-workflow/schema.yaml (new)

- [ ] 2.2 Create artifact templates for custom artifact types
  **Dependencies**: 2.1
  **Files**: openspec/schemas/feature-workflow/templates/exploration.md (new), openspec/schemas/feature-workflow/templates/plan-findings.md (new), openspec/schemas/feature-workflow/templates/impl-findings.md (new), openspec/schemas/feature-workflow/templates/validation-report.md (new), openspec/schemas/feature-workflow/templates/deferred-tasks.md (new)

## 3. Project Configuration

- [ ] 3.1 Create `openspec/config.yaml` with schema selection, context, and per-artifact rules
  **Dependencies**: 2.1
  **Files**: openspec/config.yaml (new)

- [ ] 3.2 Verify configuration with `openspec schemas --json` and `openspec validate`
  **Dependencies**: 3.1

## 4. Core Skills — OPSX Integration

- [ ] 4.1 Update `/plan-feature` to use `opsx:explore` + `opsx:ff` for artifact creation
  **Dependencies**: 2.1, 3.1
  **Files**: skills/plan-feature/SKILL.md

- [ ] 4.2 Update `/iterate-on-plan` to produce `plan-findings` artifact via OPSX
  **Dependencies**: 2.2, 3.1
  **Files**: skills/iterate-on-plan/SKILL.md

- [ ] 4.3 Update `/implement-feature` to use `opsx:apply` for task execution
  **Dependencies**: 2.1, 3.1
  **Files**: skills/implement-feature/SKILL.md

- [ ] 4.4 Update `/iterate-on-implementation` to produce `impl-findings` artifact via OPSX
  **Dependencies**: 2.2, 3.1
  **Files**: skills/iterate-on-implementation/SKILL.md

- [ ] 4.5 Update `/validate-feature` to register validation-report as OPSX artifact
  **Dependencies**: 2.2, 3.1
  **Files**: skills/validate-feature/SKILL.md

- [ ] 4.6 Update `/cleanup-feature` to use `opsx:sync` + `opsx:archive` and produce `deferred-tasks` artifact
  **Dependencies**: 2.2, 3.1
  **Files**: skills/cleanup-feature/SKILL.md

## 5. Legacy Skills — Wrapper Conversion

- [ ] 5.1 Convert `/openspec-proposal` to thin wrapper calling `opsx:new` / `opsx:ff`
  **Dependencies**: 2.1, 3.1
  **Files**: skills/openspec-proposal/SKILL.md

- [ ] 5.2 Convert `/openspec-apply` to thin wrapper calling `opsx:apply`
  **Dependencies**: 2.1
  **Files**: skills/openspec-apply/SKILL.md

- [ ] 5.3 Convert `/openspec-archive` to thin wrapper calling `opsx:sync` + `opsx:archive`
  **Dependencies**: 2.1
  **Files**: skills/openspec-archive/SKILL.md

## 6. Documentation Updates

- [ ] 6.1 Update `openspec/AGENTS.md` to reference OPSX commands and `feature-workflow` schema
  **Dependencies**: 2.1, 3.1
  **Files**: openspec/AGENTS.md

- [ ] 6.2 Update `CLAUDE.md` OpenSpec section to reference OPSX 1.0
  **Dependencies**: 6.1
  **Files**: CLAUDE.md

- [ ] 6.3 Update `docs/skills-workflow.md` to document OPSX integration points
  **Dependencies**: 4.1-4.6
  **Files**: docs/skills-workflow.md

## 7. Validation

- [ ] 7.1 Run end-to-end test: `/plan-feature` on a test change using the new schema
  **Dependencies**: 4.1, 6.1
- [ ] 7.2 Verify `openspec validate --strict` passes with new config and schema
  **Dependencies**: 3.1, 6.1

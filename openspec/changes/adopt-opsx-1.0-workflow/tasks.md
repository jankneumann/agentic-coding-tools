# Tasks: Adopt OpenSpec 1.0 OPSX Workflow

## 1. Baseline Verification

- [x] 1.1 Verify OpenSpec 1.0 command surface used by this repo (`openspec new change`, `openspec instructions`, `openspec status`, `openspec templates`, `openspec schema validate`, `openspec archive`)
  **Dependencies**: None
  **Files**: None (command verification)

- [x] 1.2 Inventory generated agent-native OpenSpec artifacts and map to workflow stages (plan/apply/validate/archive) for Claude, Codex, and Gemini
  **Dependencies**: None
  **Files**: .claude/commands/opsx/*.md, .claude/skills/openspec-*/SKILL.md, .codex/skills/openspec-*/SKILL.md, .gemini/commands/opsx/*.toml, .gemini/skills/openspec-*/SKILL.md

## 2. Custom Schema Definition

- [x] 2.1 Validate `openspec/schemas/feature-workflow/schema.yaml` with `openspec schema validate feature-workflow`
  **Dependencies**: 1.1
  **Files**: openspec/schemas/feature-workflow/schema.yaml

- [x] 2.2 Align artifact templates with command-driven instructions for custom artifact types
  **Dependencies**: 2.1
  **Files**: openspec/schemas/feature-workflow/templates/exploration.md, openspec/schemas/feature-workflow/templates/plan-findings.md, openspec/schemas/feature-workflow/templates/impl-findings.md, openspec/schemas/feature-workflow/templates/architecture-impact.md, openspec/schemas/feature-workflow/templates/validation-report.md, openspec/schemas/feature-workflow/templates/deferred-tasks.md

## 3. Project Configuration

- [x] 3.1 Update `openspec/config.yaml` rules to use current OpenSpec 1.0 command patterns and artifact IDs
  **Dependencies**: 2.1
  **Files**: openspec/config.yaml

- [x] 3.2 Verify configuration with `openspec schemas --json`, `openspec templates --schema feature-workflow --json`, and `openspec validate --strict`
  **Dependencies**: 3.1
  **Files**: None (command verification)

## 4. Core Skills — OpenSpec 1.0 Integration

- [x] 4.0 Add `/explore-feature` supporting skill for pre-planning opportunity discovery and routing into `/plan-feature`, including weighted scoring, quick-win/big-bet buckets, blocker tracking, recommendation history, and machine-readable outputs
  **Dependencies**: 1.2, 2.1, 3.1
  **Files**: skills/explore-feature/SKILL.md, docs/skills-workflow.md, openspec/changes/adopt-opsx-1.0-workflow/specs/skill-workflow/spec.md

- [x] 4.1 Update `/plan-feature` to replace `/openspec-proposal` calls with `openspec new change` + `openspec instructions` workflow
  **Dependencies**: 1.2, 2.1, 3.1
  **Files**: skills/plan-feature/SKILL.md

- [x] 4.2 Update `/iterate-on-plan` to produce `plan-findings` using `openspec instructions plan-findings --change <id>` and `openspec status --change <id>`
  **Dependencies**: 1.2, 2.2, 3.1
  **Files**: skills/iterate-on-plan/SKILL.md

- [x] 4.3 Update `/implement-feature` to use `openspec instructions apply --change <id>` for task execution guidance
  **Dependencies**: 1.2, 2.1, 3.1
  **Files**: skills/implement-feature/SKILL.md

- [x] 4.4 Update `/iterate-on-implementation` to produce `impl-findings` using `openspec instructions impl-findings --change <id>`
  **Dependencies**: 1.2, 2.2, 3.1
  **Files**: skills/iterate-on-implementation/SKILL.md

- [x] 4.5 Update `/validate-feature` to produce `architecture-impact` and `validation-report` via `openspec instructions` while preserving deployment validation phases
  **Dependencies**: 1.2, 2.2, 3.1
  **Files**: skills/validate-feature/SKILL.md

- [x] 4.6 Update `/cleanup-feature` to use direct `openspec archive <change-id> --yes` flow and produce `deferred-tasks` before archiving
  **Dependencies**: 1.2, 2.2, 3.1
  **Files**: skills/cleanup-feature/SKILL.md

- [x] 4.7 Update `/plan-feature` exploration phase to call `/refresh-architecture` when architecture artifacts are stale
  **Dependencies**: 2.1, 3.1
  **Files**: skills/plan-feature/SKILL.md

- [x] 4.8 Update `/cleanup-feature` to call `/refresh-architecture` after merge to keep docs/architecture-analysis/ current on main
  **Dependencies**: 2.1, 3.1
  **Files**: skills/cleanup-feature/SKILL.md

## 5. Documentation Updates

- [x] 5.1 Update `AGENTS.md` OpenSpec guidance to reference OpenSpec 1.0 command model and `feature-workflow` schema
  **Dependencies**: 2.1, 3.1
  **Files**: AGENTS.md

- [x] 5.2 Update `CLAUDE.md` OpenSpec section to reference the same command model and remove wrapper/deprecated command references
  **Dependencies**: 5.1
  **Files**: CLAUDE.md

- [x] 5.3 Update `docs/skills-workflow.md` to document OpenSpec 1.0 integration points and artifact lifecycle checks
  **Dependencies**: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
  **Files**: docs/skills-workflow.md

- [x] 5.4 Document precedence rule in all workflow docs: agent-native OpenSpec artifacts first, direct CLI fallback second
  **Dependencies**: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
  **Files**: AGENTS.md, CLAUDE.md, docs/skills-workflow.md

## 6. Validation

- [ ] 6.1 Run end-to-end test: `/plan-feature` on a test change using agent-native-first flow with CLI fallback verification
  **Dependencies**: 4.1, 5.1, 5.4
  **Files**: None (workflow validation)

- [x] 6.2 Verify `openspec validate --strict` passes with updated config, schema, and skill docs
  **Dependencies**: 3.2, 5.1, 5.2, 5.3
  **Files**: None (command verification)

- [x] 6.3 Verify cross-agent parity checklist for Claude/Codex/Gemini mappings and fallback behavior
  **Dependencies**: 1.2, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.4
  **Files**: .claude/commands/opsx/*.md, .claude/skills/openspec-*/SKILL.md, .codex/skills/openspec-*/SKILL.md, .gemini/commands/opsx/*.toml, .gemini/skills/openspec-*/SKILL.md, docs/skills-workflow.md

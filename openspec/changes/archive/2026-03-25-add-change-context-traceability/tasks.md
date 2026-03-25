# Tasks: add-change-context-traceability

## Task 1: Create change-context.md template and register in schema

- [x] Create `openspec/schemas/feature-workflow/templates/change-context.md` with 3-phase template
- [x] Add `change-context` artifact entry to `openspec/schemas/feature-workflow/schema.yaml` (after validation-report)
- [x] Add `change-context` rules to `openspec/config.yaml` (after validation-report rules)

**Files**: `openspec/schemas/feature-workflow/templates/change-context.md` (NEW), `openspec/schemas/feature-workflow/schema.yaml`, `openspec/config.yaml`
**Dependencies**: None
**Traces to**: Change Context Traceability Artifact requirement

## Task 2: Update validation-report.md template

- [x] Replace "Spec Compliance Details" section (lines 25-31) with reference to change-context.md
- [x] Add summary count placeholder

**Files**: `openspec/schemas/feature-workflow/templates/validation-report.md`
**Dependencies**: Task 1
**Traces to**: Validation Report Spec Compliance Refactoring requirement

## Task 3: Add TDD + change-context steps to linear-implement-feature

- [x] Insert new step 3a "Generate Change Context & Test Plan" between step 2 (Setup Worktree) and step 3 (Implement Tasks)
- [x] Remove existing TDD advisory note (lines 128-131)
- [x] Add Phase 2 update instruction to step 3 (update Files Changed column after implementation)
- [x] Add `**Change Context**` link to PR body template in step 9

**Files**: `skills/linear-implement-feature/SKILL.md`
**Dependencies**: Task 1
**Traces to**: TDD Enforcement via Change Context, Implement Feature Skill Step Structure, 3-Phase Incremental Generation, PR Body Includes Change Context Link

## Task 4: Add change-context update to linear-iterate-on-implementation

- [x] Add bullet to step 9 "Update OpenSpec Documents" for change-context.md maintenance

**Files**: `skills/linear-iterate-on-implementation/SKILL.md`
**Dependencies**: Task 3
**Traces to**: Change Context Update During Iteration requirement

## Task 5: Replace spec compliance phase in linear-validate-feature

- [x] Replace step 7 "Spec Compliance Phase" with "Spec Compliance Phase (via Change Context)"
- [x] Add backward compatibility: generate skeleton on-the-fly if change-context.md missing
- [x] Modify step 11 "Validation Report" to replace Spec Compliance Details with change-context.md reference

**Files**: `skills/linear-validate-feature/SKILL.md`
**Dependencies**: Task 1, Task 2
**Traces to**: Validation Report Spec Compliance Refactoring, 3-Phase Incremental Generation (Phase 3)

## Task 6: Add TDD + change-context phases to parallel-implement-feature

- [x] Insert step A3.5 "Generate Change Context & Test Plan" in Phase A
- [x] Add change-context.md rows to work-package context slices
- [x] Insert step C5.5 "Finalize Change Context" in Phase C (after integration merge)

**Files**: `skills/parallel-implement-feature/SKILL.md`
**Dependencies**: Task 1, Task 3
**Traces to**: Change Context Traceability Artifact (parallel), 3-Phase Incremental Generation, TDD Enforcement

## Task 7: Add evidence population to parallel-validate-feature

- [x] Insert step 4.5 "Populate Change Context Evidence" between steps 4 and 5
- [x] Add `change_context` field to step 5 JSON output

**Files**: `skills/parallel-validate-feature/SKILL.md`
**Dependencies**: Task 1, Task 6
**Traces to**: 3-Phase Incremental Generation (Phase 3), Change Context Traceability Artifact (parallel)

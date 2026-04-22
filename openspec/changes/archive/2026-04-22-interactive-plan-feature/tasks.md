# Tasks: interactive-plan-feature

## 1. Template and Schema Updates

- [x] 1.1 Add "Approaches Considered" and "Selected Approach" sections to proposal.md template
  **Dependencies**: None
  **Files**: `openspec/schemas/feature-workflow/templates/proposal.md`

- [x] 1.2 Update proposal artifact instruction in schema.yaml to reference approaches
  **Dependencies**: 1.1
  **Files**: `openspec/schemas/feature-workflow/schema.yaml`

- [x] 1.3 Update plan-findings artifact instruction in schema.yaml to include assumptions type
  **Dependencies**: None
  **Files**: `openspec/schemas/feature-workflow/schema.yaml`

## 2. Plan Feature Skill Restructuring

- [x] 2.1 Add `--explore` flag parsing and interactive mode documentation to plan-feature
  **Dependencies**: None
  **Files**: `skills/plan-feature/SKILL.md`

- [x] 2.2 Add Step 3: Present Context and Discovery Questions phase
  **Dependencies**: 2.1
  **Files**: `skills/plan-feature/SKILL.md`

- [x] 2.3 Modify Step 4: Restrict to proposal-only with mandatory Approaches section
  **Dependencies**: 1.1, 2.2
  **Files**: `skills/plan-feature/SKILL.md`

- [x] 2.4 Add Step 5: Gate 1 Direction Approval with approach selection
  **Dependencies**: 2.3
  **Files**: `skills/plan-feature/SKILL.md`

- [x] 2.5 Add Step 6: Generate remaining artifacts (specs, tasks, design) driven by selected approach
  **Dependencies**: 2.4
  **Files**: `skills/plan-feature/SKILL.md`

- [x] 2.6 Renumber Steps 7-11 (was 4-8) and update Step 12 to Gate 2 with revision options
  **Dependencies**: 2.5
  **Files**: `skills/plan-feature/SKILL.md`

## 3. Iterate on Plan: Assumptions Type

- [x] 3.1 Add "assumptions" to finding type categories and plan smells
  **Dependencies**: None
  **Files**: `skills/iterate-on-plan/SKILL.md`

- [x] 3.2 Add assumption-surfacing behavior with AskUserQuestion to Step 7
  **Dependencies**: 3.1
  **Files**: `skills/iterate-on-plan/SKILL.md`

- [x] 3.3 Add unstated assumptions to high-criticality level definition
  **Dependencies**: 3.1
  **Files**: `skills/iterate-on-plan/SKILL.md`

## 4. Sync and Verification

- [x] 4.1 Run install.sh to sync all skill changes to runtime directories
  **Dependencies**: 2.6, 3.3
  **Files**: `.claude/skills/`, `.agents/skills/`

- [x] 4.2 Verify sync correctness (diff source vs runtime copies)
  **Dependencies**: 4.1
  **Files**: None (verification only)

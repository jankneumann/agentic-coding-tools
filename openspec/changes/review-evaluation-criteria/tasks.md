# Tasks: review-evaluation-criteria

## Phase 1: Schema Foundation

- [ ] 1.1 Update `openspec/schemas/review-findings.schema.json` — Add `observability`, `compatibility`, `resilience` to the `type` enum (7 → 10)
  **Dependencies**: None

- [ ] 1.2 Update `openspec/schemas/consensus-report.schema.json` — Add `observability`, `compatibility`, `resilience` to the `agreed_type` enum (7 → 10)
  **Dependencies**: None

- [ ] 1.3 Update `skills/merge-pull-requests/scripts/vendor_review.py` — Add the 3 new types to the hardcoded type enum in the PR review prompt (line 209)
  **Dependencies**: None

## Phase 2: iterate-on-plan Enhancements

- [ ] 2.1 Add `security` and `performance` type categories to `skills/iterate-on-plan/SKILL.md` — Insert after `assumptions` in the type categories section (after line 175)
  **Dependencies**: None

- [ ] 2.2 Add new plan smells to `skills/iterate-on-plan/SKILL.md` — Add `unprotected-endpoint`, `secret-in-config`, `missing-input-validation`, `missing-pagination`, `missing-observability` to the plan smells checklist (after line 196)
  **Dependencies**: None

- [ ] 2.3 Add Schema Type Mapping section to `skills/iterate-on-plan/SKILL.md` — Document the mapping from all 10 plan dimensions to schema finding types, inserted after the plan smells section
  **Dependencies**: 2.1

## Phase 3: iterate-on-implementation Enhancements

- [ ] 3.1 Promote `security` to its own dimension and add `observability` + `resilience` in `skills/iterate-on-implementation/SKILL.md` — Modify type categories section (line 154-159): extract security from bug, add 3 new dimensions
  **Dependencies**: None

- [ ] 3.2 Update criticality levels in `skills/iterate-on-implementation/SKILL.md` — Add examples for the new dimensions at each criticality level (lines 161-165)
  **Dependencies**: 3.1

- [ ] 3.3 Add Schema Type Mapping section to `skills/iterate-on-implementation/SKILL.md` — Document the mapping from all 8 implementation dimensions to schema finding types
  **Dependencies**: 3.1

## Phase 4: parallel-review-plan Enhancements

- [ ] 4.1 Add Performance, Observability, Compatibility, and Resilience checklist sections to `skills/parallel-review-plan/SKILL.md` — Insert after the existing Security Review checklist (after line 75)
  **Dependencies**: None

- [ ] 4.2 Update Finding Types documentation in `skills/parallel-review-plan/SKILL.md` — Add `observability`, `compatibility`, `resilience` to the documented finding types list (lines 106-113)
  **Dependencies**: None

## Phase 5: parallel-review-implementation Enhancements

- [ ] 5.1 Add observability, compatibility, and resilience checklist items to Code Quality Review in `skills/parallel-review-implementation/SKILL.md` — Insert after existing performance bullet (after line 91)
  **Dependencies**: None

- [ ] 5.2 Update Finding Types documentation in `skills/parallel-review-implementation/SKILL.md` — Add `observability`, `compatibility`, `resilience` to the documented finding types list (lines 125-132)
  **Dependencies**: None

## Phase 6: Validation

- [ ] 6.1 Verify all type enums are in sync across: `review-findings.schema.json`, `consensus-report.schema.json`, `vendor_review.py`, and all 4 skill SKILL.md files
  **Dependencies**: 1.1, 1.2, 1.3, 2.1, 3.1, 4.2, 5.2

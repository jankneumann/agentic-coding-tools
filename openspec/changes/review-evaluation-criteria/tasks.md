# Tasks: review-evaluation-criteria

## Phase 1: Schema Foundation

- [ ] 1.1 Verify existing schema tests pass before modifications — Run `skills/.venv/bin/python -m pytest skills/parallel-infrastructure/scripts/tests/test_consensus_synthesizer.py -v` to establish baseline
  **Dependencies**: None

- [ ] 1.2 Update `openspec/schemas/review-findings.schema.json` — Add `observability`, `compatibility`, `resilience` to the `type` enum (7 → 10)
  **Dependencies**: 1.1

- [ ] 1.3 Update `openspec/schemas/consensus-report.schema.json` — Add `observability`, `compatibility`, `resilience` to the `agreed_type` enum (7 → 10)
  **Dependencies**: 1.1

- [ ] 1.4 Update `skills/merge-pull-requests/scripts/vendor_review.py` — Add the 3 new types to the hardcoded type enum in the PR review prompt (line 209)
  **Dependencies**: 1.1

- [ ] 1.5 Add test fixtures for new types — Update `skills/parallel-infrastructure/scripts/tests/test_consensus_synthesizer.py` and `test_review_dispatcher.py` to include findings with `observability`, `compatibility`, `resilience` types. Run tests to confirm schema conformance with expanded enum.
  **Dependencies**: 1.2, 1.3

## Phase 2: iterate-on-plan Enhancements

- [ ] 2.1 Add `security` and `performance` type categories to `skills/iterate-on-plan/SKILL.md` — Insert after `assumptions` in the type categories section (after line 175)
  **Dependencies**: None

- [ ] 2.2 Add new plan smells to `skills/iterate-on-plan/SKILL.md` — Add `unprotected-endpoint`, `secret-in-config`, `missing-input-validation`, `missing-pagination`, `missing-observability` to the plan smells checklist (after line 196)
  **Dependencies**: None

- [ ] 2.3 Add Schema Type Mapping section to `skills/iterate-on-plan/SKILL.md` — Document the mapping from all 10 plan dimensions to schema finding types, inserted after the plan smells section. Mapping:
  - completeness → spec_gap
  - clarity → spec_gap, style
  - feasibility → architecture, performance
  - scope → spec_gap, correctness
  - consistency → contract_mismatch, correctness
  - testability → spec_gap
  - parallelizability → architecture
  - assumptions → architecture, security, compatibility
  - security → security
  - performance → performance
  **Dependencies**: 2.1

## Phase 3: iterate-on-implementation Enhancements

- [ ] 3.1 Promote `security` to its own dimension and add `observability` + `resilience` in `skills/iterate-on-implementation/SKILL.md` — Modify type categories (lines 154-159): extract "security issues" from bug description, add security, observability, resilience as new dimensions
  **Dependencies**: None

- [ ] 3.2 Update criticality levels in `skills/iterate-on-implementation/SKILL.md` — Add examples for new dimensions at each criticality level (lines 161-165). E.g., critical: "authentication bypass, missing TLS"; high: "no retry on external calls, missing health endpoint"
  **Dependencies**: 3.1

- [ ] 3.3 Add Schema Type Mapping section to `skills/iterate-on-implementation/SKILL.md` — Document mapping from all 8 implementation dimensions to schema finding types. Mapping:
  - bug → correctness
  - security → security
  - edge-case → correctness, resilience
  - workflow → style, architecture
  - performance → performance
  - UX → style, correctness
  - observability → observability
  - resilience → resilience
  **Dependencies**: 3.1

## Phase 4: parallel-review-plan Enhancements

- [ ] 4.1 Add Performance, Observability, Compatibility, and Resilience checklist sections to `skills/parallel-review-plan/SKILL.md` — Insert after existing Security Review checklist (after line 75)
  **Dependencies**: None

- [ ] 4.2 Update Finding Types documentation in `skills/parallel-review-plan/SKILL.md` — Add `observability`, `compatibility`, `resilience` with descriptions to the finding types list (after line 113)
  **Dependencies**: None

## Phase 5: parallel-review-implementation Enhancements

- [ ] 5.1 Add observability, compatibility, and resilience checklist items to Code Quality Review in `skills/parallel-review-implementation/SKILL.md` — Insert after existing performance bullet (after line 91)
  **Dependencies**: None

- [ ] 5.2 Update Finding Types documentation in `skills/parallel-review-implementation/SKILL.md` — Add `observability`, `compatibility`, `resilience` with descriptions to the finding types list (after line 132)
  **Dependencies**: None

## Phase 6: Spec Delta and Validation

- [ ] 6.1 Review spec delta at `openspec/changes/review-evaluation-criteria/specs/skill-workflow/spec.md` — Verify it accurately reflects the type enum changes for iterate-on-implementation and the new schema mapping requirement
  **Dependencies**: 3.1

- [ ] 6.2 Verify type enum sync across all files — Grep for the type enum in all 7 files and confirm all 10 types (`spec_gap`, `contract_mismatch`, `architecture`, `security`, `performance`, `style`, `correctness`, `observability`, `compatibility`, `resilience`) appear in each:
  - `openspec/schemas/review-findings.schema.json`
  - `openspec/schemas/consensus-report.schema.json`
  - `skills/merge-pull-requests/scripts/vendor_review.py`
  - `skills/iterate-on-plan/SKILL.md` (in mapping table)
  - `skills/iterate-on-implementation/SKILL.md` (in mapping table)
  - `skills/parallel-review-plan/SKILL.md` (in finding types list)
  - `skills/parallel-review-implementation/SKILL.md` (in finding types list)
  **Dependencies**: 1.2, 1.3, 1.4, 2.3, 3.3, 4.2, 5.2

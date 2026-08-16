# Tasks: introduce-fitness-function-gates

Scenario references use document order within each delta spec:
`fitness-functions.1`–`.16` = scenarios in `specs/fitness-functions/spec.md`;
`skill-workflow.1`–`.5` = scenarios in `specs/skill-workflow/spec.md`.

## Phase 1 — Findings schema, consensus axis (wp-schema)

- [x] 1.1 Update schema tests to the 8-axis enum with a three-copy identity assertion [S]
  **Spec scenarios**: skill-workflow.2 (NFR axes accepted), skill-workflow.5 (copies identical)
  **Contracts**: contracts/review-findings-axis.md
  **Dependencies**: None
- [x] 1.2 Extend the axis enum in all three schema copies [S]
  **Spec scenarios**: skill-workflow.1, skill-workflow.3, skill-workflow.4
  **Design decisions**: D2
  **Dependencies**: 1.1
- [ ] Checkpoint: run tests, review diff, verify scope
- [x] 1.3 Write consensus axis tests — round-trip, same-line different-axis split [M]
  **Spec scenarios**: fitness-functions.4 (axis round-trips), fitness-functions.5 (matching uses axis)
  **Design decisions**: D3
  **Dependencies**: 1.2
- [x] 1.4 Add axis to consensus_synthesizer.py Finding, ConsensusFinding, matching keys [M]
  **Design decisions**: D3
  **Dependencies**: 1.3
- [x] 1.5 Update axis tables in parallel-review SKILL.md files, impl_review_driver prompt, skills catalogue [S]
  **Design decisions**: D2
  **Dependencies**: 1.2
- [x] 1.6 Mark validate-feature-findings-gate proposal SUPERSEDED [XS]
  **Design decisions**: D7
  **Dependencies**: None
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 2 — Gates, linters, degradation (wp-gates)

- [ ] 2.1 Write linter schema-validation tests using jsonschema.validate [S]
  **Spec scenarios**: fitness-functions.6 (linter findings validate), fitness-functions.7 (tests enforce validity)
  **Dependencies**: 1.2
- [ ] 2.2 Emit required axis, severity fields from the three architecture linters [S]
  **Design decisions**: D2
  **Dependencies**: 2.1
- [ ] 2.3 Write gate_logic tests — mode-conditional required phases, DEGRADED parsing, override flag [M]
  **Spec scenarios**: fitness-functions.8, fitness-functions.9, fitness-functions.14, fitness-functions.15, fitness-functions.16
  **Design decisions**: D4, D6
  **Dependencies**: None
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 2.4 Add gates.architecture section with populated severity_thresholds to architecture.config.yaml [S]
  **Spec scenarios**: fitness-functions.10 (thresholds populated)
  **Contracts**: contracts/architecture-gates-config.md
  **Design decisions**: D4
  **Dependencies**: 2.3
- [ ] 2.5 Wire mode-conditional Architecture phase into gate_logic.py REQUIRED_PHASES with new-cycle severity mapping [M]
  **Spec scenarios**: fitness-functions.8 (advisory reports), fitness-functions.9 (blocking fails on cycle)
  **Design decisions**: D4
  **Dependencies**: 2.3, 2.4
- [ ] 2.6 Add DEGRADED status to validation-report parsing with --accept-degraded override in gate_logic.py [M]
  **Spec scenarios**: fitness-functions.14, fitness-functions.15, fitness-functions.16
  **Design decisions**: D6
  **Dependencies**: 2.3
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 2.7 Emit DEGRADED from fail-open producers — GATEKEEPER fallback, sub-2-vendor review, degraded security pass [M]
  **Spec scenarios**: fitness-functions.14 (degraded status written)
  **Design decisions**: D6
  **Dependencies**: 2.6
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 3 — Planning templates, discovery rubric (wp-templates)

- [x] 3.1 Write template-contract tests for NFR sections in templates plus rubric category [S]
  **Spec scenarios**: fitness-functions.1, fitness-functions.2, fitness-functions.3
  **Design decisions**: D8
  **Dependencies**: None
- [x] 3.2 Add Non-Functional Requirements section to the proposal.md template [XS]
  **Spec scenarios**: fitness-functions.1
  **Dependencies**: 3.1
- [x] 3.3 Add fitness-function mapping subsection to the design.md template [XS]
  **Spec scenarios**: fitness-functions.2
  **Dependencies**: 3.1
- [x] 3.4 Add NFR elicitation category 7 to plan-feature discovery rubric [S]
  **Spec scenarios**: fitness-functions.3
  **Design decisions**: D8
  **Dependencies**: 3.1
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 4 — Coverage ratchet (wp-coverage)

- [ ] 4.1 Write ratchet script tests — decrease fails, tolerance respected, improvement message [M]
  **Spec scenarios**: fitness-functions.12 (fails on decrease), fitness-functions.13 (baseline updates)
  **Contracts**: contracts/coverage-baseline.schema.json
  **Design decisions**: D5
  **Dependencies**: None
- [ ] 4.2 Add coverage ratchet script with seeded coverage-baseline.json [S]
  **Design decisions**: D5
  **Dependencies**: 4.1
- [ ] 4.3 Add non-required coverage-ratchet job to ci.yml additively [S]
  **Spec scenarios**: fitness-functions.11 (CI reports coverage)
  **Design decisions**: D5
  **Dependencies**: 4.2
- [ ] 4.4 Document ratchet promotion command in session-completion guide [XS]
  **Design decisions**: D5
  **Dependencies**: 4.3
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 5 — Integration (wp-integration)

- [ ] 5.1 Run full test suites, openspec validate --strict, validate_flows against merged branch [S]
  **Dependencies**: Phases 1–4
- [ ] 5.2 Run validate-feature spec plus evidence phases; confirm advisory architecture block renders in validation-report.md [S]
  **Spec scenarios**: fitness-functions.8
  **Dependencies**: 5.1
- [ ] Checkpoint: run tests, review diff, verify scope

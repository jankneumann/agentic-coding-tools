# Change Context: introduce-fitness-function-gates

<!-- Phase 1 (pre-implementation): Req ID, Spec Source, Description, Contract Ref, Design
     Decision, Test(s) planned. Files Changed = "---". Evidence = "---". -->

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| skill-workflow.1 | specs/skill-workflow/spec.md | Findings schema SHALL encode an 8-axis categorization (adds observability, resilience, compatibility) | contracts/review-findings-axis.md | D2 | openspec/schemas/review-findings.schema.json, agent-coordinator/agents.yaml | test_review_findings_schema.py::test_axis_enum_values | pass 31c059b |
| skill-workflow.2 | specs/skill-workflow/spec.md | `axis` and `severity` SHALL remain required on every finding | contracts/review-findings-axis.md | D2 | openspec/schemas/review-findings.schema.json | test_review_findings_schema.py::test_axis_and_severity_required | pass 31c059b |
| skill-workflow.3 | specs/skill-workflow/spec.md | All three schema copies SHALL carry an identical enum | contracts/review-findings-axis.md | D2 | install_assets mirror, agents.yaml | test_review_findings_schema.py::test_schema_copies_identical | pass 31c059b |
| fitness-functions.1 | specs/fitness-functions/spec.md | proposal.md/design.md templates SHALL provide an NFR section with attribute, metric, target, verifying phase | --- | D8 | templates/proposal.md | skills/tests/plan-feature/test_nfr_templates.py::test_proposal_template_has_nfr_section | pass 31c059b |
| fitness-functions.2 | specs/fitness-functions/spec.md | design.md SHALL map each declared NFR to its verifying fitness function | --- | D8 | templates/design.md | skills/tests/plan-feature/test_nfr_templates.py::test_design_template_has_fitness_mapping | pass 31c059b |
| fitness-functions.3 | specs/fitness-functions/spec.md | plan-feature discovery rubric SHALL include an NFR elicitation category | --- | D8 | skills/plan-feature/SKILL.md | skills/tests/plan-feature/test_nfr_templates.py::test_rubric_has_nfr_category | pass 31c059b |
| fitness-functions.4 | specs/fitness-functions/spec.md | Consensus synthesizer SHALL parse, retain, and emit `axis` | contracts/review-findings-axis.md | D3 | consensus_synthesizer.py | test_consensus_axis.py::test_axis_round_trips | pass 31c059b |
| fitness-functions.5 | specs/fitness-functions/spec.md | Cross-vendor matching SHALL use axis with file_path and line_range | contracts/review-findings-axis.md | D3 | consensus_synthesizer.py | test_consensus_axis.py::test_different_axis_same_line_not_merged | pass 31c059b |
| fitness-functions.6 | specs/fitness-functions/spec.md | Architecture linters SHALL emit schema-valid findings including axis and severity | contracts/review-findings-axis.md | D2 | linters/{dependency_direction,file_size,naming_conventions,severity}.py | test_linters.py::test_findings_validate_against_schema | pass 31c059b |
| fitness-functions.7 | specs/fitness-functions/spec.md | Linter test suite SHALL assert schema validity with jsonschema.validate | contracts/review-findings-axis.md | D2 | scripts/tests/test_linters.py | test_linters.py::test_missing_required_field_fails | pass 31c059b |
| fitness-functions.8 | specs/fitness-functions/spec.md | Advisory mode SHALL report architecture findings without failing the gate | contracts/architecture-gates-config.md | D4 | gate_logic.py, architecture.config.yaml | test_gate_logic_architecture.py::test_advisory_mode_does_not_block | pass 31c059b |
| fitness-functions.9 | specs/fitness-functions/spec.md | Blocking mode SHALL fail the hard gate on a new dependency cycle | contracts/architecture-gates-config.md | D4 | gate_logic.py | test_gate_logic_architecture.py::test_blocking_mode_fails_on_new_cycle | pass 31c059b |
| fitness-functions.10 | specs/fitness-functions/spec.md | architecture.config.yaml SHALL carry populated severity_thresholds and gates.architecture.mode | contracts/architecture-gates-config.md | D4 | architecture.config.yaml | test_gate_logic_architecture.py::test_config_thresholds_populated | pass 31c059b |
| fitness-functions.11 | specs/fitness-functions/spec.md | CI SHALL report line coverage per measured suite | contracts/coverage-baseline.schema.json | D5 | .github/workflows/ci.yml | scripts/tests/test_coverage_ratchet.py::test_reports_measured_coverage | pass 31c059b |
| fitness-functions.12 | specs/fitness-functions/spec.md | Ratchet SHALL fail when coverage drops beyond tolerance | contracts/coverage-baseline.schema.json | D5 | scripts/coverage_ratchet.py | scripts/tests/test_coverage_ratchet.py::test_fails_on_decrease | pass 31c059b |
| fitness-functions.13 | specs/fitness-functions/spec.md | CI SHALL print an update command and an explicit maintainer update SHALL move improved baselines upward only | contracts/coverage-baseline.schema.json | D5 | scripts/coverage_ratchet.py, coverage-baseline.json | scripts/tests/test_coverage_ratchet.py::test_update_writes_improved_values_only | pass 31c059b |
| fitness-functions.14 | specs/fitness-functions/spec.md | Fail-open gates SHALL record DEGRADED status naming what was not checked | contracts/architecture-gates-config.md | D6 | gate_logic.py, autopilot.py, review_dispatcher.py, security-review/gate.py | test_gate_logic_degraded.py::test_degraded_status_parsed | pass 31c059b |
| fitness-functions.15 | specs/fitness-functions/spec.md | Hard gate SHALL block on a DEGRADED required phase absent an override | contracts/architecture-gates-config.md | D6 | gate_logic.py | test_gate_logic_degraded.py::test_hard_gate_blocks_on_degraded | pass 31c059b |
| fitness-functions.16 | specs/fitness-functions/spec.md | Override SHALL be explicit and logged in the gate summary | contracts/architecture-gates-config.md | D6 | gate_logic.py | test_gate_logic_degraded.py::test_accept_degraded_override_logged | pass 31c059b |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Machinery exists but is unwired; a registry abstracts over signals that don't exist yet | Extend gate_logic.py, architecture.config.yaml, review-findings.schema.json, feature-workflow templates in place | Rejected fitness-functions.yaml registry (XL, premature abstraction) — recorded as follow-up |
| D2 | Three copies of the axis enum drift silently | 8-value enum in all copies + copy-identity test | Turns future drift into a test failure rather than a review catch |
| D3 | consensus_synthesizer.py drops axis, contradicting documented matching | Add axis to Finding/ConsensusFinding, key matching on (axis, file_path, line_range) | Prerequisite for NFR findings surviving consensus |
| D4 | Immediate blocking risks failing in-flight changes on pre-existing findings | gates.architecture.mode advisory now, blocking flip after 3 clean runs | Mirrors context-drift-gate rollout precedent |
| D5 | Absolute coverage threshold penalizes legacy code | Non-required CI job, stored baseline, no-decrease ratchet with tolerance | Measures drift rather than an arbitrary bar |
| D6 | Fail-open gates are indistinguishable from passing ones | DEGRADED status in validation-report + gate_logic, --accept-degraded override | Rejected treating DEGRADED as failure everywhere (would incentivize deleting checks) |
| D7 | validate-feature-findings-gate targets the same surface, untouched at 0/31 | Record supersession in this change only; do not migrate tasks or touch a second change directory | One-change-directory CI invariant |
| D8 | Reviewers check NFRs against an implicit house standard | NFR section in proposal/design templates + rubric category 7 | Gives fitness functions a declared target to test against |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

## Coverage Summary

- **Requirements traced**: 19/19
- **Tests mapped**: 19 requirements have at least one test planned
- **Evidence collected**: 19/19 requirements have pass/fail evidence
- **Gaps identified**: none
- **Deferred items**: Docker-dependent phases (Deploy, Smoke, E2E, Logs) deferred to /cleanup-feature's merge-time gate

# Tasks: Software Factory Tooling

**Change ID**: `add-software-factory-tooling`

## Phase 1: Scenario Pack Management

- [ ] 1.1 Write tests for scenario-pack manifest parsing, visibility filtering, provenance tracking, and visibility-aware reporting
  **Files**: `agent-coordinator/tests/test_evaluation/test_gen_eval/test_manifest.py`, `agent-coordinator/tests/test_evaluation/test_gen_eval/test_reports.py`, `skills/gen-eval-scenario/tests/test_manifest_bootstrap.py`
  **Spec scenarios**: `gen-eval-framework.1.1-1.3`, `gen-eval-framework.2.3`
  **Design decisions**: `D1`, `D2`
  **Dependencies**: None

- [ ] 1.2 Add scenario-pack manifest model, loader, and report filtering to gen-eval
  **Files**: `agent-coordinator/evaluation/gen_eval/models.py`, `agent-coordinator/evaluation/gen_eval/descriptor.py`, `agent-coordinator/evaluation/gen_eval/generator.py`, `agent-coordinator/evaluation/gen_eval/reports.py`
  **Spec scenarios**: `gen-eval-framework.1.1-1.3`, `gen-eval-framework.2.1-2.3`
  **Design decisions**: `D1`, `D2`
  **Dependencies**: `1.1`

- [ ] 1.3 Extend `/gen-eval-scenario` to bootstrap scenarios from specs, contracts, incidents, and archived exemplars
  **Files**: `skills/gen-eval-scenario/SKILL.md`, `skills/gen-eval-scenario/scripts/bootstrap.py`, `skills/gen-eval-scenario/tests/test_bootstrap.py`
  **Spec scenarios**: `gen-eval-framework.4.1-4.3`, `software-factory-tooling.3.1-3.2`
  **Design decisions**: `D1`, `D6`
  **Dependencies**: `1.1`, `1.2`

## Phase 2: DTU Scaffold

- [ ] 2.1 Write tests for doc-derived DTU scaffold generation, unsupported-surface capture, and fidelity scoring
  **Files**: `agent-coordinator/tests/test_evaluation/test_gen_eval/test_dtu_scaffold.py`, `agent-coordinator/tests/test_evaluation/test_gen_eval/test_fidelity_report.py`
  **Spec scenarios**: `gen-eval-framework.3.1-3.3`
  **Design decisions**: `D3`
  **Dependencies**: None

- [ ] 2.2 Implement DTU-lite scaffold generation and fidelity report contracts for external projects
  **Files**: `agent-coordinator/evaluation/gen_eval/descriptor.py`, `agent-coordinator/evaluation/gen_eval/dtu_scaffold.py`, `agent-coordinator/evaluation/gen_eval/fidelity.py`, `agent-coordinator/evaluation/gen_eval/__main__.py`
  **Spec scenarios**: `gen-eval-framework.3.1-3.3`, `software-factory-tooling.3.1-3.3`
  **Design decisions**: `D3`
  **Dependencies**: `2.1`

- [ ] 2.3 Add external-project bootstrap templates for scenario packs and DTU scaffolds
  **Files**: `skills/gen-eval/SKILL.md`, `skills/gen-eval-scenario/SKILL.md`, `openspec/schemas/feature-workflow/templates/`, `docs/software-factory-tooling.md`
  **Spec scenarios**: `software-factory-tooling.3.1-3.3`
  **Design decisions**: `D3`, `D7`
  **Dependencies**: `2.2`

## Phase 3: Validation-Driven Rework

- [ ] 3.1 Write tests for `rework-report.json` generation, holdout gating, and iteration routing
  **Files**: `skills/validate-feature/scripts/tests/test_rework_report.py`, `skills/validate-feature/scripts/tests/test_holdout_gates.py`, `skills/iterate-on-implementation/tests/test_rework_consumption.py`
  **Spec scenarios**: `skill-workflow.1.1-1.3`, `skill-workflow.3.1-3.3`
  **Design decisions**: `D2`, `D4`
  **Dependencies**: None

- [ ] 3.2 Implement visibility-aware validation gates and `rework-report.json` emission
  **Files**: `skills/validate-feature/SKILL.md`, `skills/validate-feature/scripts/gate_logic.py`, `skills/validate-feature/scripts/phase_smoke.py`, `skills/validate-feature/scripts/rework_report.py`
  **Spec scenarios**: `skill-workflow.1.1-1.3`, `skill-workflow.3.1-3.3`
  **Design decisions**: `D2`, `D4`
  **Dependencies**: `3.1`, `1.2`

- [ ] 3.3 Add `process-analysis.md` / `process-analysis.json` generation from validation, iteration, and session artifacts
  **Files**: `openspec/schemas/feature-workflow/schema.yaml`, `openspec/schemas/feature-workflow/templates/process-analysis.md`, `skills/validate-feature/scripts/process_analysis.py`, `skills/session-log/SKILL.md`
  **Spec scenarios**: `skill-workflow.2.1-2.3`
  **Design decisions**: `D5`
  **Dependencies**: `3.1`

- [ ] 3.4 Update `/iterate-on-implementation`, `/cleanup-feature`, and `/merge-pull-requests` to consume rework/process-analysis artifacts
  **Files**: `skills/iterate-on-implementation/SKILL.md`, `skills/cleanup-feature/SKILL.md`, `skills/merge-pull-requests/SKILL.md`
  **Spec scenarios**: `skill-workflow.1.2-1.3`, `skill-workflow.2.1-2.3`, `skill-workflow.3.1-3.3`
  **Design decisions**: `D4`, `D5`
  **Dependencies**: `3.2`, `3.3`

## Phase 4: Archive Intelligence

- [ ] 4.1 Write tests for archive normalization, exemplar scoring, missing-artifact handling, and scenario-seed extraction
  **Files**: `skills/explore-feature/tests/test_archive_index.py`, `skills/gen-eval-scenario/tests/test_exemplar_registry.py`, `skills/session-log/scripts/test_extract_session_log.py`
  **Spec scenarios**: `software-factory-tooling.1.1-1.3`, `software-factory-tooling.2.1-2.3`
  **Design decisions**: `D5`, `D6`
  **Dependencies**: None

- [ ] 4.2 Implement archive miner and normalized exemplar registry over archived OpenSpec artifacts
  **Files**: `skills/explore-feature/scripts/archive_index.py`, `skills/explore-feature/scripts/exemplar_registry.py`, `docs/feature-discovery/README.md`, `docs/factory-intelligence/`
  **Spec scenarios**: `software-factory-tooling.1.1-1.3`, `software-factory-tooling.2.1-2.3`
  **Design decisions**: `D5`, `D6`
  **Dependencies**: `4.1`, `3.3`

- [ ] 4.3 Integrate archive intelligence into `/explore-feature`, `/plan-feature`, and `/gen-eval-scenario`
  **Files**: `skills/explore-feature/SKILL.md`, `skills/plan-feature/SKILL.md`, `skills/gen-eval-scenario/SKILL.md`
  **Spec scenarios**: `software-factory-tooling.2.1-2.3`, `software-factory-tooling.3.1-3.3`
  **Design decisions**: `D6`
  **Dependencies**: `4.2`

## Phase 5: Dogfood On This Repository

- [ ] 5.1 Classify `agent-coordinator` gen-eval scenarios into public and holdout packs with initial manifests
  **Files**: `agent-coordinator/evaluation/gen_eval/manifests/`, `agent-coordinator/evaluation/gen_eval/scenarios/`
  **Spec scenarios**: `gen-eval-framework.2.1-2.3`, `skill-workflow.3.1`
  **Design decisions**: `D2`, `D7`
  **Dependencies**: `1.2`

- [ ] 5.2 Create DTU-lite dogfood fixtures for GitHub PR/check/review flows and transport/auth degradation
  **Files**: `agent-coordinator/evaluation/gen_eval/dtu/github/`, `agent-coordinator/evaluation/gen_eval/dtu/transports/`, `agent-coordinator/evaluation/gen_eval/descriptors/agent-coordinator.yaml`
  **Spec scenarios**: `gen-eval-framework.3.1-3.3`
  **Design decisions**: `D3`, `D7`
  **Dependencies**: `2.2`, `5.1`

- [ ] 5.3 Run dogfood validation, capture baseline `process-analysis`, and update lessons learned
  **Files**: `openspec/changes/add-software-factory-tooling/process-analysis.md`, `docs/lessons-learned.md`, `docs/factory-intelligence/archive-index.json`
  **Spec scenarios**: `skill-workflow.2.1-2.3`, `software-factory-tooling.2.1`
  **Design decisions**: `D5`, `D7`
  **Dependencies**: `3.3`, `4.2`, `5.2`

## Phase 6: Integration

- [ ] 6.1 Run end-to-end validation for scenario packs, DTU scaffolds, workflow rework gates, archive intelligence, and dogfood fixtures
  **Files**: `agent-coordinator/tests/test_evaluation/`, `skills/validate-feature/scripts/tests/`, `skills/explore-feature/tests/`, `docs/software-factory-tooling.md`
  **Spec scenarios**: `gen-eval-framework.1.1-4.3`, `skill-workflow.1.1-3.3`, `software-factory-tooling.1.1-3.3`
  **Design decisions**: `D1-D7`
  **Dependencies**: `1.3`, `2.3`, `3.4`, `4.3`, `5.3`

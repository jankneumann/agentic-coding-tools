# Tasks: add-security-review-skill

## Requirement Mapping

- R1 Cross-Project Security Review Skill → 1.1, 1.2, 4.1
- R2 Project Profile Detection and Scanner Matrix Selection → 2.1, 2.2
- R3 OWASP Dependency-Check Adapter → 3.1
- R4 OWASP ZAP Docker Adapter → 3.2
- R5 Normalized Risk-Gated Reporting → 4.1, 4.2
- R6 Security Workflow Position → 5.1, 5.2
- R7 Dependency Bootstrap and Install Guidance → 1.3, 5.3
- R8 Skill Script Directory Convention → 1.3
- R9 Security Review Artifact Dependency Flow → 4.2, 5.4

## 1. Skill Foundation

- [x] 1.1 Create `skills/security-review/SKILL.md` with arguments, preflight checks, scanner orchestration flow, and explicit degraded-mode behavior.
  **Dependencies**: None
  **Files**: skills/security-review/SKILL.md

- [x] 1.2 Create a shared result schema and adapter contract for scanner outputs.
  **Dependencies**: 1.1
  **Files**: skills/security-review/scripts/schema.py, skills/security-review/scripts/models.py

- [x] 1.3 Add dependency bootstrap entrypoint and OS-aware prerequisite checks for Java, Docker, and scanner toolchains.
  **Dependencies**: 1.1
  **Files**: skills/security-review/scripts/install_deps.sh, skills/security-review/scripts/check_prereqs.sh

## 2. Cross-Project Detection

- [x] 2.1 Implement repository profile detection (Python/Node/Java/containerized API/mixed) from manifest and config signals.
  **Dependencies**: 1.2
  **Files**: skills/security-review/scripts/detect_profile.py, skills/security-review/scripts/profile_rules.yaml

- [x] 2.2 Implement scanner matrix planning from detected profile(s), including override flags.
  **Dependencies**: 2.1
  **Files**: skills/security-review/scripts/build_scan_plan.py, skills/security-review/scripts/profile_rules.yaml

## 3. Scanner Adapters

- [x] 3.1 Implement OWASP Dependency-Check adapter with native execution and Docker fallback plus normalized parser.
  **Dependencies**: 2.2
  **Files**: skills/security-review/scripts/run_dependency_check.sh, skills/security-review/scripts/parse_dependency_check.py

- [x] 3.2 Implement ZAP Docker adapter for baseline/api/full modes with target preflight and normalized parser.
  **Dependencies**: 2.2
  **Files**: skills/security-review/scripts/run_zap_scan.sh, skills/security-review/scripts/parse_zap_results.py

## 4. Risk Gate and Reporting

- [x] 4.1 Implement normalized aggregation and gate decision logic (`PASS`/`FAIL`/`INCONCLUSIVE`) with `--fail-on` threshold support.
  **Dependencies**: 3.1, 3.2
  **Files**: skills/security-review/scripts/aggregate_findings.py, skills/security-review/scripts/gate.py

- [x] 4.2 Implement report emitters (machine-readable JSON + markdown summary) and exit-code mapping.
  **Dependencies**: 4.1
  **Files**: skills/security-review/scripts/render_report.py, skills/security-review/scripts/main.py

## 5. Workflow and Documentation Integration

- [x] 5.1 Update workflow docs to add `/security-review` as an optional security gate with recommended invocation points.
  **Dependencies**: 1.1, 4.2
  **Files**: docs/skills-workflow.md, openspec/changes/add-security-review-skill/specs/skill-workflow/spec.md

- [x] 5.2 Update repository skill catalog documentation and installation guidance for the new skill.
  **Dependencies**: 1.1
  **Files**: AGENTS.md, skills/install.sh

- [x] 5.3 Add platform-specific dependency installation instructions and bootstrap usage examples.
  **Dependencies**: 1.1, 1.3
  **Files**: skills/security-review/docs/dependencies.md, skills/security-review/SKILL.md

- [x] 5.4 Add security-review-report artifact flow and enforce pre-validation check in `/validate-feature`.
  **Dependencies**: 4.2
  **Files**: openspec/schemas/feature-workflow/schema.yaml, openspec/schemas/feature-workflow/templates/security-review-report.md, skills/validate-feature/SKILL.md, docs/skills-workflow.md

## 6. Validation

- [x] 6.1 Add tests for profile detection, adapter parsing, and risk gate decisions.
  **Dependencies**: 2.2, 3.1, 3.2, 4.1
  **Files**: skills/security-review/tests/test_detect_profile.py, skills/security-review/tests/test_dependency_check_parser.py, skills/security-review/tests/test_zap_parser.py, skills/security-review/tests/test_gate.py, skills/security-review/tests/test_render_report.py, skills/security-review/tests/test_build_scan_plan.py, skills/security-review/tests/test_main_helpers.py, skills/security-review/tests/test_runner_scripts.py

- [x] 6.2 Validate planning artifacts and implementation readiness (`openspec validate add-security-review-skill --strict`).
  **Dependencies**: 5.1, 5.3, 5.4
  **Files**: openspec/changes/add-security-review-skill/proposal.md, openspec/changes/add-security-review-skill/specs/skill-workflow/spec.md, openspec/changes/add-security-review-skill/tasks.md, openspec/changes/add-security-review-skill/design.md

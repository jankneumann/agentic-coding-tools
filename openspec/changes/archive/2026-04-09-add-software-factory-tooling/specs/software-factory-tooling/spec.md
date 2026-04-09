# software-factory-tooling Specification Delta

## ADDED Requirements

### Requirement: Archive Intelligence Index

The system SHALL provide an archive miner that indexes completed OpenSpec changes and normalizes their artifacts into a machine-readable archive-intelligence index.

The index SHALL support, at minimum, the following inputs when present:
- `proposal.md`
- `design.md`
- `tasks.md`
- spec deltas
- `change-context.md`
- `validation-report.md`
- `session-log.md`
- `process-analysis.md` / `process-analysis.json`
- merge logs

#### Scenario: Archive miner indexes completed change
Given an archived OpenSpec change with proposal, tasks, validation-report, and session-log artifacts
When archive mining runs
Then the change is added to the archive-intelligence index with normalized metadata

#### Scenario: Missing optional artifact does not fail indexing
Given an archived change without `process-analysis.json`
When archive mining runs
Then indexing succeeds and records the artifact as absent

#### Scenario: Index preserves change-level references
Given an archived change with linked requirement refs and change-id
When indexing completes
Then the normalized output preserves those references for downstream retrieval

#### Scenario: Incremental indexing skips already-indexed changes
Given an existing archive index with 10 indexed changes and 2 new archived changes
When archive mining runs
Then only the 2 new changes are processed and appended to the index

### Requirement: Exemplar Registry

The system SHALL derive reusable exemplars from the archive-intelligence index, including scenario seeds, repair patterns, DTU edge cases, and implementation patterns.

The exemplar registry SHALL expose confidence or quality metadata so downstream tools can prefer higher-signal exemplars.

#### Scenario: Scenario seed extracted from archived change
Given an archived change whose validation artifacts show a stable scenario pattern
When exemplar extraction runs
Then the pattern is added to the scenario-seed registry with a source change reference

#### Scenario: Repair pattern extracted from rework history
Given an archived change with validation failures followed by successful remediation
When exemplar extraction runs
Then the normalized fix pattern is added to the repair-pattern registry

#### Scenario: Low-signal exemplar is demoted
Given an archived artifact with incomplete data and no successful outcome evidence
When exemplar extraction runs
Then the exemplar receives a low-confidence score and is not marked preferred

### Requirement: External Project Bootstrap

The system SHALL provide a bootstrap flow for external projects adopting software-factory practices.

The bootstrap flow SHALL scaffold:
- scenario-pack manifests
- public and holdout pack locations
- DTU scaffold placeholders
- archive-intelligence directories
- CI or validation wiring guidance

#### Scenario: Bootstrap creates software-factory layout
Given a project with gen-eval enabled
When the software-factory bootstrap runs
Then it creates manifests, DTU placeholder directories, and archive-intelligence output locations

#### Scenario: Bootstrap references existing OpenSpec artifacts
Given a project already uses OpenSpec
When bootstrap runs
Then the generated guidance references the existing change workflow rather than creating a separate process

#### Scenario: Bootstrap fails gracefully without gen-eval
Given a project that has not enabled gen-eval (no descriptor or scenario directories)
When the software-factory bootstrap runs
Then it exits with a clear error indicating gen-eval must be configured first and provides setup guidance

#### Scenario: Bootstrap includes dogfood-ready example for this repository
Given this repository is the target project
When bootstrap runs
Then it creates scenario-pack manifests under `agent-coordinator/evaluation/gen_eval/manifests/`, DTU placeholder directories under `agent-coordinator/evaluation/gen_eval/dtu/`, and references existing scenario YAML files in the generated manifest

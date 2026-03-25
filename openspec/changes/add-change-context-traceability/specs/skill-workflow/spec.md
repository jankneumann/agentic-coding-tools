# skill-workflow Specification Delta

## ADDED Requirements

### Requirement: Change Context Traceability Artifact

The system SHALL produce a `change-context.md` artifact during the feature workflow that maps every spec requirement to its implementing code, tests, and validation evidence.

The artifact SHALL contain the following sections:
- **Requirement Traceability Matrix**: One row per SHALL/MUST requirement with columns: Req ID, Spec Source, Description, Files Changed, Test(s), Evidence
- **Design Decision Trace**: One row per decision from design.md (omitted when no design.md exists)
- **Review Findings Summary**: Synthesized review findings (parallel workflow only, omitted for linear)
- **Coverage Summary**: Exact counts of requirements traced, tests mapped, evidence collected, gaps, and deferred items

#### Scenario: Artifact generated during linear implementation
- **WHEN** the agent executes `/implement-feature <change-id>`
- **THEN** the system SHALL create `change-context.md` in the change directory
- **AND** the Requirement Traceability Matrix SHALL contain one row per SHALL/MUST clause from `specs/<capability>/spec.md`
- **AND** the Req ID format SHALL be `<capability>.<N>` where N is the ordinal position in the spec file

#### Scenario: Artifact generated during parallel implementation
- **WHEN** the orchestrator executes `/parallel-implement-feature <change-id>`
- **THEN** the system SHALL create `change-context.md` after integration merge
- **AND** the Files Changed column SHALL cross-reference `files_modified` from work-queue results per package
- **AND** the Review Findings Summary SHALL synthesize findings from all `review-findings.json` files

#### Scenario: Backward compatibility for pre-existing changes
- **WHEN** `/validate-feature` runs on a change that lacks `change-context.md`
- **THEN** the system SHALL generate the skeleton on-the-fly from specs and git diff
- **AND** proceed with evidence population as normal

#### Scenario: Coverage summary accuracy
- **WHEN** `change-context.md` is populated
- **THEN** the Coverage Summary SHALL use exact counts (not estimates)
- **AND** gaps SHALL list requirements with no test mapping
- **AND** deferred items SHALL list requirements that could not be verified

### Requirement: 3-Phase Incremental Generation

The `change-context.md` artifact SHALL be built incrementally across three workflow phases.

#### Scenario: Phase 1 — Test plan (pre-implementation)
- **WHEN** the agent reads spec delta files before implementing tasks
- **THEN** the system SHALL populate Req ID, Spec Source, Description, and Test(s) columns
- **AND** Files Changed SHALL be set to `---`
- **AND** Evidence SHALL be set to `---`
- **AND** the agent SHALL write failing tests (RED) for each row in the matrix

#### Scenario: Phase 2 — Implementation
- **WHEN** the agent completes implementation tasks
- **THEN** the system SHALL update the Files Changed column with actual source files modified
- **AND** tests from Phase 1 SHALL now pass (GREEN)
- **AND** the Design Decision Trace Implementation column SHALL be populated if design.md exists

#### Scenario: Phase 3 — Validation evidence
- **WHEN** `/validate-feature` runs the spec compliance phase
- **THEN** the system SHALL fill the Evidence column for each requirement row
- **AND** evidence values SHALL be one of: `pass <short-SHA>`, `fail <short-SHA>`, `deferred <reason>`

### Requirement: TDD Enforcement via Change Context

The implementation workflow SHALL enforce test-driven development structurally through the change-context artifact.

#### Scenario: Tests written before implementation code
- **WHEN** the agent begins the implementation phase
- **THEN** step 3a "Generate Change Context & Test Plan" SHALL execute before step 3 "Implement Tasks"
- **AND** the Test(s) column SHALL be populated with planned test function names derived from spec scenarios
- **AND** those tests SHALL be written as failing tests before any implementation code

#### Scenario: Tests encode spec scenarios
- **WHEN** the agent writes tests in Phase 1
- **THEN** each test function SHALL encode the corresponding spec scenario's WHEN/THEN/AND clauses as assertions
- **AND** tests for scenarios requiring live services SHALL use `@pytest.mark.integration` or `@pytest.mark.e2e` markers

#### Scenario: Existing TDD advisory replaced
- **WHEN** the skill instructions for `/implement-feature` are updated
- **THEN** the existing 3-line TDD advisory note SHALL be removed
- **AND** TDD enforcement SHALL be achieved through the structural step ordering (step 3a before step 3)

### Requirement: Validation Report Spec Compliance Refactoring

The `validation-report.md` template SHALL reference `change-context.md` for spec compliance instead of duplicating the data.

#### Scenario: Spec compliance section replaced
- **WHEN** `/validate-feature` generates the validation report
- **THEN** the "Spec Compliance Details" section SHALL be replaced with a reference to `change-context.md`
- **AND** only a summary count (N/M requirements verified) SHALL appear in the validation report

#### Scenario: Operational phases retained
- **WHEN** the validation report is generated
- **THEN** all operational phases (Deploy, Smoke, Security, E2E, Architecture, Logs, CI/CD) SHALL be retained unchanged

### Requirement: Change Context Update During Iteration

The `/iterate-on-implementation` skill SHALL update `change-context.md` when iteration findings change the requirement-to-code mapping.

#### Scenario: New requirement discovered during iteration
- **WHEN** an iteration finding reveals a missing spec requirement
- **THEN** a new row SHALL be added to the Requirement Traceability Matrix
- **AND** the corresponding test SHALL be written before the fix is implemented

#### Scenario: Files or tests changed during iteration
- **WHEN** an iteration adds new files, tests, or changes requirement mappings
- **THEN** the Files Changed and Test(s) columns SHALL be updated accordingly
- **AND** the Coverage Summary SHALL be updated with new counts

## MODIFIED Requirements

### Requirement: Implement Feature Skill Step Structure (MODIFIED)

The `/implement-feature` skill SHALL include a new step 3a "Generate Change Context & Test Plan" inserted before the existing "Implement Tasks" step.

#### Scenario: Step ordering enforces TDD
- **WHEN** the agent executes `/implement-feature <change-id>`
- **THEN** step 3a SHALL execute before step 3
- **AND** step 3a SHALL produce `change-context.md` with the traceability skeleton and failing tests
- **AND** step 3 SHALL reference tests from step 3a as the behavioral specification

### Requirement: PR Body Includes Change Context Link (MODIFIED)

The PR creation step SHALL include a link to `change-context.md` alongside the existing proposal link.

#### Scenario: Change context linked in PR
- **WHEN** the agent creates a PR via `gh pr create`
- **THEN** the PR body SHALL include: `**Change Context**: openspec/changes/<change-id>/change-context.md`

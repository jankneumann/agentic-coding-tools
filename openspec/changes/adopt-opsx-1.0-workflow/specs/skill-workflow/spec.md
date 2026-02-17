## MODIFIED Requirements

### Requirement: Feature Planning Workflow

The system SHALL use OPSX commands for artifact lifecycle management during feature planning. The `/plan-feature` skill SHALL call `opsx:explore` for context gathering and `opsx:ff` (or `opsx:new` followed by `opsx:continue`) for creating planning artifacts (proposal, specs, design, tasks). All artifacts SHALL be tracked by OPSX's dependency graph and state machine (BLOCKED/READY/DONE).

#### Scenario: Plan feature creates artifacts via OPSX
- **WHEN** user invokes `/plan-feature <description>`
- **THEN** the skill calls `opsx:explore` to gather context from specs, changes, and codebase
- **AND** calls `opsx:ff` to create all planning artifacts (proposal.md, specs, tasks.md, optional design.md)
- **AND** all artifacts are registered in OPSX state as DONE
- **AND** the skill validates with `openspec validate <change-id> --strict`

#### Scenario: Plan feature uses custom schema
- **WHEN** a new change is created via `/plan-feature`
- **THEN** OPSX uses the `feature-workflow` schema from `openspec/config.yaml`
- **AND** the exploration artifact is created if the schema defines it
- **AND** downstream artifacts respect the dependency graph

### Requirement: Iterative Plan Refinement

The system SHALL produce a `plan-findings` artifact during `/iterate-on-plan` iterations. Each iteration SHALL append structured findings (type, criticality, description, resolution) to the cumulative artifact. The iteration loop SHALL terminate when all findings are below the configured criticality threshold or max iterations are reached.

#### Scenario: Iterate on plan produces findings artifact
- **WHEN** user invokes `/iterate-on-plan <change-id>`
- **THEN** the skill creates or updates `plan-findings.md` in the change directory
- **AND** each iteration appends a findings table with type, criticality, description, and resolution columns
- **AND** the artifact is tracked by OPSX as part of the `feature-workflow` schema

#### Scenario: Iterate on plan terminates at threshold
- **WHEN** all findings in an iteration are below the criticality threshold
- **THEN** the iteration loop terminates
- **AND** a readiness checklist is presented with parallelizability assessment

### Requirement: Feature Implementation via OPSX Apply

The system SHALL use `opsx:apply` for feature implementation task tracking. The `/implement-feature` skill SHALL delegate task execution to OPSX while retaining orchestration responsibilities (worktree setup, parallel agent spawning, quality checks, PR creation).

#### Scenario: Implement feature delegates to OPSX apply
- **WHEN** user invokes `/implement-feature <change-id>`
- **THEN** the skill verifies the proposal is approved
- **AND** calls `opsx:apply` for task-by-task implementation
- **AND** runs parallel quality checks (pytest, mypy, ruff, openspec validate)
- **AND** creates a PR with test plan and task checklist

### Requirement: Iterative Implementation Refinement

The system SHALL produce an `impl-findings` artifact during `/iterate-on-implementation` iterations. Finding types SHALL include bug, edge-case, workflow, performance, and UX categories with criticality levels.

#### Scenario: Iterate on implementation produces findings artifact
- **WHEN** user invokes `/iterate-on-implementation <change-id>`
- **THEN** the skill creates or updates `impl-findings.md` in the change directory
- **AND** each iteration appends findings with implementation-specific type categories
- **AND** spec drift detection triggers updates to OpenSpec documents

### Requirement: Validation Report as OPSX Artifact

The system SHALL register the validation report as an OPSX artifact in the `feature-workflow` schema. The `/validate-feature` skill SHALL create the `validation-report.md` artifact through the OPSX artifact lifecycle, ensuring it is tracked as DONE in the dependency graph.

#### Scenario: Validate feature creates OPSX-tracked report
- **WHEN** user invokes `/validate-feature <change-id>`
- **THEN** the skill runs all validation phases (deploy, smoke, e2e, architecture, spec, logs, ci)
- **AND** writes `validation-report.md` as an OPSX artifact
- **AND** OPSX tracks the artifact state as DONE
- **AND** the report is posted as a PR comment if a PR exists

### Requirement: Architecture Impact as Per-Change Artifact

The system SHALL produce an `architecture-impact` artifact during `/validate-feature` that captures the structural consequences of a change on the project architecture. The `/refresh-architecture` skill SHALL remain standalone for project-global regeneration but SHALL be called at specific workflow touchpoints to keep `docs/architecture-analysis/` artifacts current.

#### Scenario: Validate feature produces architecture impact artifact
- **WHEN** user invokes `/validate-feature <change-id>`
- **THEN** the skill runs `make architecture-diff BASE_SHA=<merge-base>` against the changed files
- **AND** runs `make architecture-validate` scoped to changed files
- **AND** writes `architecture-impact.md` as an OPSX artifact in the change directory
- **AND** the artifact includes new/broken cross-layer flows, affected parallel zones, and validation findings

#### Scenario: Plan feature ensures architecture artifacts are current
- **WHEN** user invokes `/plan-feature <description>`
- **AND** `docs/architecture-analysis/` artifacts are older than the latest commit on main
- **THEN** the skill runs `make architecture` before proceeding to `opsx:explore`
- **AND** the exploration artifact references current architecture data

#### Scenario: Cleanup feature refreshes architecture after merge
- **WHEN** user invokes `/cleanup-feature <change-id>`
- **AND** the PR is merged to main
- **THEN** the skill runs `make architecture` on main after the merge
- **AND** the refreshed `docs/architecture-analysis/` artifacts reflect the merged change

#### Scenario: Architecture refresh remains independent
- **WHEN** user invokes `/refresh-architecture` directly (not via another skill)
- **THEN** the full 3-layer pipeline runs against the current codebase
- **AND** no per-change OPSX artifacts are created
- **AND** `docs/architecture-analysis/` artifacts are updated in place

### Requirement: Feature Cleanup via OPSX Sync and Archive

The system SHALL use `opsx:sync` for merging spec deltas and `opsx:archive` for completing changes. The `/cleanup-feature` skill SHALL produce a `deferred-tasks` artifact when open tasks are migrated to follow-up proposals or issue trackers.

#### Scenario: Cleanup feature uses OPSX sync and archive
- **WHEN** user invokes `/cleanup-feature <change-id>`
- **THEN** the skill merges the PR
- **AND** calls `opsx:sync` to merge delta specs into main specs
- **AND** calls `opsx:archive` to move the change to the archive directory
- **AND** produces `deferred-tasks.md` if any tasks remain unchecked

#### Scenario: Deferred tasks are tracked as artifact
- **WHEN** `/cleanup-feature` detects unchecked tasks in `tasks.md`
- **THEN** the skill creates `deferred-tasks.md` with task descriptions, original context, and migration target
- **AND** the artifact is tracked by OPSX before archival

### Requirement: OPSX Project Configuration

The system SHALL maintain an `openspec/config.yaml` that selects the `feature-workflow` schema, provides project context for artifact generation, and defines per-artifact rules enforcing project conventions.

#### Scenario: Config provides per-artifact rules
- **WHEN** an artifact is created via any OPSX command
- **THEN** OPSX injects the project context from `config.yaml` into the generation instructions
- **AND** per-artifact rules from the `rules` section are included as validation requirements

#### Scenario: Config selects custom schema
- **WHEN** a new change is created without explicit schema flag
- **THEN** OPSX uses the `feature-workflow` schema defined in `config.yaml`
- **AND** `openspec schemas --json` lists `feature-workflow` with all custom artifact IDs

### Requirement: Legacy Skill Compatibility

The system SHALL maintain backward-compatible wrappers for `/openspec-proposal`, `/openspec-apply`, and `/openspec-archive` that delegate to the equivalent OPSX commands. These wrappers SHALL be marked for deprecation after one release cycle.

#### Scenario: Legacy openspec-proposal redirects to OPSX
- **WHEN** user invokes `/openspec-proposal <description>`
- **THEN** the skill calls `opsx:new` or `opsx:ff` depending on the provided arguments
- **AND** produces the same artifact structure as before

#### Scenario: Legacy openspec-archive redirects to OPSX
- **WHEN** user invokes `/openspec-archive <change-id>`
- **THEN** the skill calls `opsx:sync` followed by `opsx:archive`
- **AND** validates with `openspec validate --strict`

## MODIFIED Requirements

### Requirement: Feature Opportunity Exploration

The system SHALL provide an `/explore-feature` supporting skill that analyzes architecture artifacts, active OpenSpec changes, and codebase signals to recommend high-value next features before planning.

#### Scenario: Explore feature produces ranked opportunities
- **WHEN** user invokes `/explore-feature`
- **THEN** the skill analyzes specs, active changes, and architecture artifacts
- **AND** returns a ranked shortlist of candidate features with impact, strategic fit, effort, and risk
- **AND** uses a documented weighted scoring model so ranking is reproducible
- **AND** labels each candidate as `quick-win` or `big-bet`
- **AND** recommends one concrete next `/plan-feature` action

#### Scenario: Explore feature records blockers per opportunity
- **WHEN** `/explore-feature` emits candidate opportunities
- **THEN** each opportunity includes an explicit `blocked-by` field
- **AND** blockers reference actionable dependencies (for example active change IDs, missing infrastructure, or unresolved design decisions)

#### Scenario: Explore feature incorporates recommendation history
- **WHEN** prior discovery recommendations exist and remain deferred without new evidence
- **THEN** `/explore-feature` uses recommendation history to avoid repeatedly elevating unchanged items
- **AND** documents when historical adjustments changed current ranking

#### Scenario: Explore feature emits machine-readable output
- **WHEN** `/explore-feature` completes
- **THEN** it writes a machine-readable ranked opportunity artifact
- **AND** it updates recommendation history metadata for future prioritization workflows
- **AND** downstream proposal-prioritization logic can consume these artifacts without free-text parsing

#### Scenario: Explore feature handles stale architecture artifacts
- **WHEN** architecture artifacts required for opportunity analysis are missing or stale
- **THEN** the skill refreshes architecture artifacts or reports refresh requirements
- **AND** avoids speculative recommendations without current structural data

### Requirement: Feature Planning Workflow

The system SHALL use agent-native OpenSpec artifacts/commands for artifact lifecycle management during feature planning when available for the active runtime, with direct OpenSpec CLI fallback when not available. The `/plan-feature` skill SHALL use generated OpenSpec assets first and fallback to `openspec new change` plus `openspec instructions <artifact> --change <id>`. Artifact readiness and completion SHALL be observable through `openspec status --change <id>`.

#### Scenario: Plan feature creates artifacts via OpenSpec commands
- **WHEN** user invokes `/plan-feature <description>`
- **THEN** the skill gathers context from specs, active changes, and codebase
- **AND** uses agent-native OpenSpec planning assets for the current runtime when present
- **AND** falls back to `openspec new change` plus `openspec instructions` when agent-native assets are unavailable
- **AND** artifact progress is visible through `openspec status --change <id>`
- **AND** the skill validates with `openspec validate <change-id> --strict`

#### Scenario: Plan feature uses custom schema
- **WHEN** a new change is created via `/plan-feature`
- **THEN** OpenSpec uses the `feature-workflow` schema from `openspec/config.yaml`
- **AND** the exploration artifact is created if the schema defines it
- **AND** downstream artifacts respect the dependency graph

#### Scenario: Plan feature handles missing schema configuration
- **WHEN** `/plan-feature` runs and `feature-workflow` cannot be resolved from configuration
- **THEN** the skill reports schema resolution failure before artifact generation
- **AND** does not proceed to proposal/spec/task authoring until configuration is fixed

#### Scenario: Plan feature handles missing agent-native assets
- **WHEN** `/plan-feature` cannot resolve generated OpenSpec assets for the active runtime
- **THEN** the skill falls back to direct OpenSpec CLI command family
- **AND** records that fallback path was used in workflow output

### Requirement: Iterative Plan Refinement

The system SHALL produce a `plan-findings` artifact during `/iterate-on-plan` iterations. Each iteration SHALL append structured findings (type, criticality, description, resolution) to the cumulative artifact. The iteration loop SHALL terminate when all findings are below the configured criticality threshold or max iterations are reached.

#### Scenario: Iterate on plan produces findings artifact
- **WHEN** user invokes `/iterate-on-plan <change-id>`
- **THEN** the skill creates or updates `plan-findings.md` in the change directory
- **AND** each iteration appends a findings table with type, criticality, description, and resolution columns
- **AND** the artifact is tracked as part of the `feature-workflow` schema

#### Scenario: Iterate on plan terminates at threshold
- **WHEN** all findings in an iteration are below the criticality threshold
- **THEN** the iteration loop terminates
- **AND** a readiness checklist is presented with parallelizability assessment

#### Scenario: Iterate on plan blocks on strict validation errors
- **WHEN** `openspec validate <change-id> --strict` fails during an iteration
- **THEN** the skill records the failure as a critical finding
- **AND** applies plan fixes before proceeding to the next iteration

### Requirement: Feature Implementation via OpenSpec Apply Instructions

The system SHALL prefer agent-native OpenSpec apply guidance for feature implementation task sequencing, with `openspec instructions apply --change <id>` as fallback. The `/implement-feature` skill SHALL retain orchestration responsibilities (branch/work context setup, parallel agent spawning, quality checks, PR creation).

#### Scenario: Implement feature delegates to OpenSpec apply instructions
- **WHEN** user invokes `/implement-feature <change-id>`
- **THEN** the skill verifies the proposal is approved
- **AND** uses runtime-native OpenSpec apply guidance when present
- **AND** falls back to `openspec instructions apply --change <change-id>` otherwise
- **AND** runs parallel quality checks (pytest, mypy, ruff, openspec validate)
- **AND** creates a PR with test plan and task checklist

#### Scenario: Implement feature blocks when required planning artifacts are missing
- **WHEN** `/implement-feature` is invoked and required planning artifacts are incomplete
- **THEN** the skill surfaces missing artifacts via `openspec status --change <change-id>`
- **AND** stops implementation execution until prerequisites are satisfied

### Requirement: Iterative Implementation Refinement

The system SHALL produce an `impl-findings` artifact during `/iterate-on-implementation` iterations. Finding types SHALL include bug, edge-case, workflow, performance, and UX categories with criticality levels.

#### Scenario: Iterate on implementation produces findings artifact
- **WHEN** user invokes `/iterate-on-implementation <change-id>`
- **THEN** the skill creates or updates `impl-findings.md` in the change directory
- **AND** each iteration appends findings with implementation-specific type categories
- **AND** spec drift detection triggers updates to OpenSpec documents

#### Scenario: Iterate on implementation escalates failing quality checks
- **WHEN** any required quality check fails during implementation iteration
- **THEN** the failure is captured in `impl-findings.md` with criticality and resolution plan
- **AND** the iteration does not mark implementation ready until addressed

### Requirement: Validation Report as OpenSpec Artifact

The system SHALL register the validation report as an OpenSpec artifact in the `feature-workflow` schema. The `/validate-feature` skill SHALL prefer runtime-native OpenSpec validation guidance and fallback to `openspec instructions validation-report --change <id>`, ensuring dependency tracking remains intact.

#### Scenario: Validate feature creates OpenSpec-tracked report
- **WHEN** user invokes `/validate-feature <change-id>`
- **THEN** the skill runs all validation phases (deploy, smoke, e2e, architecture, spec, logs, ci)
- **AND** writes `validation-report.md` as an OpenSpec artifact
- **AND** `openspec status --change <change-id>` reflects the artifact state
- **AND** the report is posted as a PR comment if a PR exists

#### Scenario: Validate feature falls back when runtime-native guidance is unavailable
- **WHEN** runtime-native OpenSpec validation guidance cannot be resolved
- **THEN** `/validate-feature` uses `openspec instructions validation-report --change <id>` as fallback
- **AND** continues to enforce strict validation and phase reporting requirements

#### Scenario: Validate feature records partial results on phase failure
- **WHEN** one or more validation phases fail during `/validate-feature`
- **THEN** the report records pass/fail/warn/skip per phase
- **AND** the overall result is marked as fail with explicit next steps

### Requirement: Architecture Impact as Per-Change Artifact

The system SHALL produce an `architecture-impact` artifact during `/validate-feature` that captures the structural consequences of a change on the project architecture. The `/refresh-architecture` skill SHALL remain standalone for project-global regeneration but SHALL be called at specific workflow touchpoints to keep `docs/architecture-analysis/` artifacts current.

#### Scenario: Validate feature produces architecture impact artifact
- **WHEN** user invokes `/validate-feature <change-id>`
- **THEN** the skill runs `make architecture-diff BASE_SHA=<merge-base>` against the changed files
- **AND** runs `make architecture-validate` scoped to changed files
- **AND** writes `architecture-impact.md` as an OpenSpec artifact in the change directory
- **AND** the artifact includes new/broken cross-layer flows, affected parallel zones, and validation findings

#### Scenario: Plan feature ensures architecture artifacts are current
- **WHEN** user invokes `/plan-feature <description>`
- **AND** `docs/architecture-analysis/` artifacts are older than the latest commit on main
- **THEN** the skill runs `make architecture` before proceeding to planning artifact generation
- **AND** the exploration artifact references current architecture data

#### Scenario: Cleanup feature refreshes architecture after merge
- **WHEN** user invokes `/cleanup-feature <change-id>`
- **AND** the PR is merged to main
- **THEN** the skill runs `make architecture` on main after the merge
- **AND** the refreshed `docs/architecture-analysis/` artifacts reflect the merged change

#### Scenario: Architecture refresh remains independent
- **WHEN** user invokes `/refresh-architecture` directly (not via another skill)
- **THEN** the full 3-layer pipeline runs against the current codebase
- **AND** no per-change OpenSpec artifacts are created
- **AND** `docs/architecture-analysis/` artifacts are updated in place

#### Scenario: Validate feature handles missing architecture tooling
- **WHEN** `/validate-feature` cannot run required architecture commands in the current environment
- **THEN** the `architecture-impact` artifact records the failure with actionable remediation
- **AND** the validation report marks architecture phase as fail or warn (not silent pass)

### Requirement: Feature Cleanup via OpenSpec Archive

The system SHALL prefer runtime-native OpenSpec archive guidance and fallback to `openspec archive <change-id> --yes` for completing changes and merging spec deltas. The `/cleanup-feature` skill SHALL produce a `deferred-tasks` artifact when open tasks are migrated to follow-up proposals or issue trackers.

#### Scenario: Cleanup feature uses OpenSpec archive
- **WHEN** user invokes `/cleanup-feature <change-id>`
- **THEN** the skill merges the PR
- **AND** uses runtime-native OpenSpec archive guidance when present
- **AND** falls back to `openspec archive <change-id> --yes` otherwise
- **AND** produces `deferred-tasks.md` if any tasks remain unchecked

#### Scenario: Deferred tasks are tracked as artifact
- **WHEN** `/cleanup-feature` detects unchecked tasks in `tasks.md`
- **THEN** the skill creates `deferred-tasks.md` with task descriptions, original context, and migration target
- **AND** the artifact is tracked before archival

#### Scenario: Cleanup feature blocks archive when migration metadata is missing
- **WHEN** unchecked tasks exist but migration target/provenance is missing
- **THEN** `/cleanup-feature` does not archive the change
- **AND** prompts for deferred task migration details first

### Requirement: OpenSpec Project Configuration

The system SHALL maintain an `openspec/config.yaml` that selects the `feature-workflow` schema, provides project context for artifact generation, and defines per-artifact rules enforcing project conventions.

#### Scenario: Config provides per-artifact rules
- **WHEN** an artifact is created via OpenSpec command-driven guidance
- **THEN** OpenSpec injects the project context from `config.yaml` into the generation instructions
- **AND** per-artifact rules from the `rules` section are included as validation requirements

#### Scenario: Config selects custom schema
- **WHEN** a new change is created without explicit schema flag
- **THEN** OpenSpec uses the `feature-workflow` schema defined in `config.yaml`
- **AND** `openspec schemas --json` lists `feature-workflow` with all custom artifact IDs

#### Scenario: Config validation fails for unresolved templates
- **WHEN** schema templates referenced in `feature-workflow` cannot be resolved
- **THEN** `openspec schema validate feature-workflow` fails
- **AND** the workflow blocks until template paths are corrected

### Requirement: Legacy Skill Compatibility

The system SHALL remove dependencies on legacy wrapper skills (`/openspec-proposal`, `/openspec-apply`, `/openspec-archive`) and standardize on agent-native OpenSpec artifacts first with direct OpenSpec CLI fallback across core skill internals and docs.

#### Scenario: Legacy wrapper dependencies are removed from core skills
- **WHEN** core skills are updated for OpenSpec 1.0
- **THEN** planning/implementation/cleanup paths no longer rely on `/openspec-*` wrapper skills
- **AND** documentation references direct CLI command usage instead

#### Scenario: Legacy wrapper references are removed during review
- **WHEN** outdated wrapper references remain in docs or skill instructions
- **THEN** review validation identifies them as drift from the adopted workflow
- **AND** cleanup work removes or rewrites those references before completion

### Requirement: Cross-Agent OpenSpec Parity

The system SHALL maintain equivalent workflow behavior across Claude, Codex, and Gemini generated OpenSpec artifacts for plan/apply/validate/archive stages, including identical fallback semantics and validation gates.

#### Scenario: Cross-agent mappings stay aligned
- **WHEN** generated OpenSpec artifacts exist in `.claude/commands/opsx/`, `.claude/skills/`, `.codex/skills/`, `.gemini/commands/opsx/`, and `.gemini/skills/`
- **THEN** each runtime maps plan/apply/validate/archive stages to equivalent OpenSpec intents
- **AND** no runtime bypasses required validation gates

#### Scenario: Parity check detects runtime drift
- **WHEN** one runtime's generated artifact behavior diverges from others
- **THEN** parity validation flags the mismatch before workflow rollout
- **AND** documentation and skill mappings are updated to restore equivalence

# skill-workflow Specification Delta

## MODIFIED Requirements

### Requirement: Universal Planning Artifact Generation

The `/plan-feature` skill SHALL generate contracts and work-packages for ALL execution tiers, not only for `local-parallel` and `coordinated` tiers.

#### Scenario: Sequential-tier plan generates contracts
- **WHEN** `/plan-feature` runs at sequential tier
- **THEN** it SHALL generate full-fidelity contracts (OpenAPI, DB schema, event schemas, type stubs) in `contracts/` using the same format as parallel tiers
- **AND** skip contract sub-types that are not applicable to the feature (e.g., no OpenAPI if no API endpoints)

#### Scenario: Sequential-tier plan generates work-packages
- **WHEN** `/plan-feature` runs at sequential tier
- **THEN** it SHALL generate a `work-packages.yaml` containing a single `wp-main` package
- **AND** `wp-main` SHALL have `write_allow: ["**"]` covering the full feature scope
- **AND** `wp-main` SHALL have no dependencies (root package)
- **AND** the work-packages file SHALL conform to `openspec/schemas/work-packages.schema.json`

#### Scenario: Commit message reflects universal artifacts
- **WHEN** `/plan-feature` commits planning artifacts at any tier
- **THEN** the commit message SHALL always include "contracts, work-packages" regardless of tier

### Requirement: Implementation Contract Consumption

The `/implement-feature` skill SHALL consume contracts as input constraints at ALL execution tiers.

#### Scenario: Sequential-tier implementation uses contracts
- **WHEN** `/implement-feature` runs at sequential tier with contracts present
- **THEN** it SHALL read contracts to validate interface conformance during implementation
- **AND** the Requirement Traceability Matrix SHALL map requirements to contract refs
- **AND** failing tests SHALL assert against contracted schemas where applicable

#### Scenario: Contract-less legacy implementation
- **WHEN** `/implement-feature` runs against a change that predates universal artifacts (no contracts directory)
- **THEN** it SHALL proceed without contract validation
- **AND** log a warning that contract-based validation was skipped

### Requirement: Review Fallback Without Work-Packages

The `/parallel-review-implementation` skill SHALL support reviewing changes when `work-packages.yaml` is missing.

#### Scenario: Whole-branch review fallback
- **WHEN** `/parallel-review-implementation` is invoked for a change without `work-packages.yaml`
- **THEN** it SHALL treat the entire branch diff as a single review unit
- **AND** dispatch vendors with the full diff as context
- **AND** skip scope verification (Step 2) since no package scopes are defined
- **AND** skip contract compliance review if `contracts/` is also missing

#### Scenario: Review with work-packages present
- **WHEN** `/parallel-review-implementation` is invoked for a change with `work-packages.yaml`
- **THEN** it SHALL use per-package scoped review as currently implemented
- **AND** behavior SHALL be unchanged from existing implementation

### Requirement: Merge-Time Review Resilience

The `/merge-pull-requests` skill's vendor review dispatch (Step 9) SHALL handle PRs regardless of whether planning artifacts exist.

#### Scenario: Vendor review for PR with universal artifacts
- **WHEN** a PR has contracts and work-packages in its change directory
- **THEN** vendor review SHALL include contract and scope information in the review prompt

#### Scenario: Vendor review for PR without planning artifacts
- **WHEN** a PR lacks contracts or work-packages (legacy, external contribution, non-OpenSpec)
- **THEN** vendor review SHALL proceed using only the PR diff as context
- **AND** the review SHALL NOT fail or skip due to missing artifacts

### Requirement: Updated Tier Documentation

The tier table in `CLAUDE.md` SHALL accurately reflect the universal artifact generation.

#### Scenario: CLAUDE.md tier table update
- **WHEN** the tier table is rendered
- **THEN** the sequential tier's "Planning Artifacts" column SHALL read "Tasks.md + contracts + work-packages (single package)"
- **AND** the table SHALL note that contracts and work-packages are generated at all tiers

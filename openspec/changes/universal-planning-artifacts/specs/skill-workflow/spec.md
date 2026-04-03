# skill-workflow Specification Delta

## MODIFIED Requirements

### Requirement: Universal Planning Artifact Generation

The `/plan-feature` skill SHALL generate contracts and work-packages for ALL execution tiers, not only for `local-parallel` and `coordinated` tiers.

#### Scenario: Sequential-tier plan generates contracts
- **WHEN** `/plan-feature` runs at sequential tier
- **THEN** it SHALL generate contracts in `contracts/` using the same directory structure and file format as parallel tiers
- **AND** include only contract sub-types applicable to the feature (OpenAPI if API endpoints exist, DB schema if migrations exist, event schemas if events exist)
- **AND** if no contract sub-types are applicable, create `contracts/README.md` documenting that no machine-readable contracts apply to this feature

#### Scenario: Sequential-tier plan generates work-packages
- **WHEN** `/plan-feature` runs at sequential tier
- **THEN** it SHALL generate a `work-packages.yaml` containing a single `wp-main` package
- **AND** `wp-main` SHALL have `write_allow: ["**"]` covering the full feature scope
- **AND** `wp-main` SHALL have no dependencies (root package)
- **AND** the work-packages file SHALL conform to `openspec/schemas/work-packages.schema.json`

#### Scenario: No applicable contract sub-types
- **WHEN** a feature has no API endpoints, no database changes, and no events
- **THEN** `/plan-feature` SHALL create a `contracts/` directory containing only a `README.md` stub
- **AND** the README SHALL state which contract sub-types were evaluated and why none apply
- **AND** consuming skills SHALL treat a `contracts/` directory with only `README.md` as "no contracts applicable"

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

#### Scenario: Partial contracts directory
- **WHEN** `/implement-feature` runs against a change where `contracts/` exists but contains only some sub-types (e.g., OpenAPI but no DB schema)
- **THEN** it SHALL validate against the contract sub-types that are present
- **AND** skip validation for absent sub-types without error
- **AND** the RTM SHALL use `---` for contract refs where no applicable contract exists

#### Scenario: Contract-less legacy implementation
- **WHEN** `/implement-feature` runs against a change that predates universal artifacts (no `contracts/` directory)
- **THEN** it SHALL proceed without contract validation
- **AND** log a warning that contract-based validation was skipped

#### Scenario: Malformed contract file
- **WHEN** a contract file exists but cannot be parsed (invalid YAML/JSON)
- **THEN** `/implement-feature` SHALL log an error identifying the malformed file
- **AND** skip validation for that contract sub-type
- **AND** proceed with implementation (do not block on parse failures)

### Requirement: Review Fallback Without Work-Packages

The `/parallel-review-implementation` skill SHALL support reviewing changes when `work-packages.yaml` is missing.

#### Scenario: Whole-branch review fallback
- **WHEN** `/parallel-review-implementation` is invoked for a change without `work-packages.yaml`
- **THEN** it SHALL treat the entire branch diff as a single review unit
- **AND** dispatch vendors with the full diff as context
- **AND** use `package_id: "whole-branch"` in findings output
- **AND** skip scope verification since no package scopes are defined
- **AND** skip contract compliance review if `contracts/` is also missing or contains only `README.md`

#### Scenario: Whole-branch review with contracts present
- **WHEN** `/parallel-review-implementation` is invoked without `work-packages.yaml` but with `contracts/` containing machine-readable artifacts
- **THEN** it SHALL include contract artifacts in the review context
- **AND** perform contract compliance review against the full diff

#### Scenario: Review with work-packages present
- **WHEN** `/parallel-review-implementation` is invoked for a change with `work-packages.yaml`
- **THEN** it SHALL use per-package scoped review as currently implemented
- **AND** behavior SHALL be unchanged from existing implementation

#### Scenario: Malformed work-packages file
- **WHEN** `work-packages.yaml` exists but cannot be parsed
- **THEN** the skill SHALL fall back to whole-branch review mode
- **AND** log a warning about the malformed file

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

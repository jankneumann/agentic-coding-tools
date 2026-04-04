# merge-pull-requests Specification Delta

## ADDED Requirements

### Requirement: Vendor Review Artifact Resilience

The vendor review dispatch (Step 9) SHALL handle PRs regardless of whether OpenSpec planning artifacts (contracts, work-packages) exist.

#### Scenario: Vendor review with planning artifacts
- **WHEN** a PR has an associated OpenSpec change directory containing contracts and work-packages
- **THEN** the vendor review prompt SHALL include contract and scope information for richer review context
- **AND** the review dispatch SHALL proceed normally

#### Scenario: Vendor review without planning artifacts
- **WHEN** a PR lacks contracts or work-packages (legacy PR, external contribution, non-OpenSpec PR)
- **THEN** the vendor review SHALL proceed using only the PR diff and metadata as context
- **AND** the review SHALL NOT fail, skip, or produce an error due to missing artifacts
- **AND** the review output SHALL note that artifact-based scoping was unavailable

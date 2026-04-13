# Roadmap Orchestration Specification

**Spec ID**: roadmap-orchestration
**Change ID**: roadmap-openspec-orchestration
**Status**: Draft

## ADDED Requirements

### Requirement: Proposal Decomposition into Roadmap Changes

The system SHALL provide a `plan-roadmap` workflow that decomposes a long markdown proposal into a prioritized sequence of OpenSpec changes with explicit dependencies and scope boundaries.

#### Scenario: Decompose markdown proposal into change candidates
WHEN a user provides a long markdown proposal as input to `plan-roadmap`
THEN the workflow SHALL extract capabilities, constraints, and phases
AND it SHALL produce a roadmap artifact containing candidate change IDs, dependencies, and acceptance goals
AND each candidate SHALL include a short rationale and estimated effort.

#### Scenario: Seed OpenSpec artifacts per selected roadmap item
WHEN the user approves selected roadmap candidates
THEN `plan-roadmap` SHALL create draft OpenSpec change folders for approved items
AND each folder SHALL include a proposal scaffold linked to the roadmap item.

### Requirement: Adaptive Roadmap Execution

The system SHALL provide an `autopilot-roadmap` workflow that executes roadmap items iteratively and updates remaining plans based on implementation evidence.

#### Scenario: Learning feedback updates future roadmap items
WHEN a roadmap item completes implementation and review
THEN `autopilot-roadmap` SHALL persist a learning artifact summarizing decisions, blockers, and deviations
AND before executing the next roadmap item it SHALL ingest prior learning artifacts
AND it SHALL adjust downstream task recommendations accordingly.

#### Scenario: Resume from persisted checkpoint
WHEN roadmap execution is interrupted
THEN `autopilot-roadmap` SHALL resume from the last completed checkpoint
AND it SHALL avoid re-running already-completed phases unless explicitly requested.

### Requirement: Usage-Limit-Aware Multi-Vendor Scheduling

The system SHALL support execution policies that trade off elapsed time and model cost when vendor/session limits are reached.

#### Scenario: Wait policy selected under budget constraints
WHEN the active preferred vendor reaches session or rate limits
AND policy is configured as `wait_if_budget_exceeded`
THEN `autopilot-roadmap` SHALL pause execution until the limit window resets
AND it SHALL record the pause reason and expected resume time in roadmap state.

#### Scenario: Alternate vendor selected to reduce wall-clock time
WHEN the active preferred vendor reaches session or rate limits
AND policy is configured as `switch_if_time_saved`
THEN `autopilot-roadmap` SHALL dispatch eligible work to an alternate configured vendor
AND it SHALL record cost and latency deltas for policy evaluation.

### Requirement: Progressive Context Management

Roadmap workflows SHALL externalize progress context to durable artifacts so that execution does not depend on a single large in-memory prompt.

#### Scenario: Progressive context reload between phases
WHEN a roadmap phase begins
THEN the workflow SHALL load only relevant roadmap, proposal, and learning artifacts for that phase
AND it SHALL avoid requiring full historical chat context to proceed.

#### Scenario: Coordinator-backed context fallback
WHEN coordinator context storage is available
THEN roadmap workflows SHALL store and retrieve phase summaries using coordinator APIs
AND when unavailable they SHALL use equivalent on-disk artifacts.

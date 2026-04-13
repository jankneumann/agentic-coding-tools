# Roadmap Orchestration Specification

**Spec ID**: roadmap-orchestration
**Change ID**: roadmap-openspec-orchestration
**Status**: Draft

## ADDED Requirements

### Requirement: Proposal Decomposition into Roadmap Changes

The system SHALL provide a `plan-roadmap` workflow that decomposes long markdown proposals into prioritized OpenSpec change candidates with explicit dependencies and acceptance outcomes.

#### Scenario: Decompose markdown proposal into roadmap candidates
WHEN a user provides a long markdown proposal to `plan-roadmap`
THEN the workflow SHALL extract candidate capabilities, constraints, and phases
AND it SHALL emit a roadmap artifact containing change IDs, dependency edges, priority, and acceptance outcomes
AND each candidate SHALL include effort estimate and rationale.

#### Scenario: Reject decomposition when proposal input is insufficient
WHEN the input markdown omits required implementation intent (no actionable capabilities or constraints)
THEN `plan-roadmap` SHALL fail with a structured validation error
AND it SHALL provide guidance for minimum required proposal sections.

#### Scenario: Seed OpenSpec change scaffolds from approved candidates
WHEN the user approves selected roadmap candidates
THEN `plan-roadmap` SHALL create draft OpenSpec change directories for each approved candidate
AND each created change SHALL include a proposal scaffold linked back to the roadmap item ID.

### Requirement: Adaptive Roadmap Execution

The system SHALL provide an `autopilot-roadmap` workflow that executes roadmap items iteratively and updates pending items using implementation evidence.

#### Scenario: Learning feedback updates remaining roadmap items
WHEN a roadmap item completes implementation and review
THEN `autopilot-roadmap` SHALL persist a learning entry with decisions, blockers, and deviations
AND before the next item begins it SHALL ingest prior learning entries
AND it SHALL update pending item recommendations accordingly.

#### Scenario: Resume from persisted checkpoint after interruption
WHEN roadmap execution stops before completion
THEN `autopilot-roadmap` SHALL resume from the last successful checkpoint
AND it SHALL skip phases already marked complete unless forced by user input.

#### Scenario: Abort item execution when prerequisite roadmap dependency is incomplete
WHEN a roadmap item is selected for execution
AND one or more of its dependency items are not complete
THEN `autopilot-roadmap` SHALL block execution of that item
AND it SHALL emit a dependency-blocked status with missing dependency IDs.

### Requirement: Usage-Limit-Aware Multi-Vendor Scheduling

The system SHALL apply explicit policy when vendor session/rate limits are encountered during roadmap execution.

#### Scenario: Wait policy selected under budget constraints
WHEN the preferred vendor hits a usage/session limit
AND active policy is `wait_if_budget_exceeded`
THEN `autopilot-roadmap` SHALL pause execution until the known reset window
AND it SHALL persist pause reason, blocked vendor, and expected resume timestamp.

#### Scenario: Switch policy selected when time saved exceeds configured threshold
WHEN the preferred vendor hits a usage/session limit
AND active policy is `switch_if_time_saved`
AND configured policy constraints allow alternate vendor cost
THEN `autopilot-roadmap` SHALL dispatch eligible work to an alternate vendor
AND it SHALL persist expected and observed cost/latency deltas.

#### Scenario: Fail closed when no eligible vendor exists
WHEN the preferred vendor is limited
AND no alternate vendor satisfies capability and policy constraints
THEN `autopilot-roadmap` SHALL transition roadmap state to blocked
AND it SHALL record required operator action to continue.

### Requirement: Progressive Context Management

Roadmap workflows SHALL externalize planning/execution context to durable artifacts so progress does not depend on one model context window.

#### Scenario: Progressive context reload per phase
WHEN a roadmap phase starts
THEN the workflow SHALL load only required artifacts (roadmap item, checkpoint, relevant learning entries)
AND it SHALL avoid requiring full historical chat transcript.

#### Scenario: Coordinator-backed context fallback
WHEN coordinator context APIs are available
THEN the workflow SHALL publish phase summaries to coordinator memory
AND when coordinator APIs are unavailable it SHALL continue using on-disk artifacts with equivalent content.

#### Scenario: Artifact corruption detected during load
WHEN a required roadmap artifact is malformed or missing required fields
THEN the workflow SHALL stop execution for that phase
AND it SHALL report a recoverable artifact-validation error with repair instructions.

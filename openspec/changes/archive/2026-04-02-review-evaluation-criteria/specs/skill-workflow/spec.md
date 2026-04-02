# skill-workflow Specification Delta: review-evaluation-criteria

## Requirement Change: Structured Improvement Analysis (iterate-on-implementation)

The existing requirement states:
> Each iteration SHALL produce a structured analysis where every finding contains:
> - **Type**: One of bug, edge-case, workflow, performance, UX

This requirement SHALL be updated to:
> Each iteration SHALL produce a structured analysis where every finding contains:
> - **Type**: One of bug, security, edge-case, workflow, performance, UX, observability, resilience

**Rationale**: Security was previously a sub-concern of "bug" but warrants its own dimension for systematic evaluation. Observability and resilience are new dimensions covering production readiness concerns.

## Requirement Change: Analysis Coverage (iterate-on-implementation)

The existing scenario states:
> - **THEN** it SHALL evaluate for bugs, unhandled edge cases, workflow improvements, performance issues, and UX issues

This requirement SHALL be updated to:
> - **THEN** it SHALL evaluate for bugs, security vulnerabilities, unhandled edge cases, workflow improvements, performance issues, UX issues, observability gaps, and resilience concerns

## New Requirement: Schema Type Mapping

Each iterate-* skill SHALL document an explicit mapping from its domain-specific type categories to the shared `review-findings.schema.json` finding types. This mapping SHALL be used when:
- Translating findings at the dispatch boundary to parallel-review-* skills
- Matching iterate-* findings against vendor consensus findings

### Scenario: Mapping consistency
- **WHEN** the review-findings schema adds or removes a finding type
- **THEN** both iterate-on-plan and iterate-on-implementation SHALL update their mapping tables to reflect the change

## New Requirement: Expanded Review Finding Types Schema

The `review-findings.schema.json` type enum SHALL include 10 finding types:
- `spec_gap`, `contract_mismatch`, `architecture`, `security`, `performance`, `style`, `correctness`, `observability`, `compatibility`, `resilience`

The `consensus-report.schema.json` `agreed_type` enum SHALL stay in sync with the `review-findings.schema.json` type enum at all times.

### Scenario: Schema sync verification
- **WHEN** a finding type is added or removed from `review-findings.schema.json`
- **THEN** the same change SHALL be applied to `consensus-report.schema.json` `agreed_type`
- **AND** to the hardcoded type enum in `vendor_review.py`

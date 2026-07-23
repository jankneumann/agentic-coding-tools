# Superseded spec delta

> **Status: SUPERSEDED — REPLACED BY
> `add-deterministic-context-producer-checks`**

## ADDED Requirements

### Requirement: Superseded Documentation Sync Proposal

The skills system SHALL treat `add-update-documentation-skill` as superseded by
`add-deterministic-context-producer-checks` and MUST NOT dispatch implementation
from this change. Documentation inventory generation SHALL be obtained through
the replacement change's registered producer.

This superseded change MUST NOT direct independent pre-commit, post-merge,
cleanup-feature, validate-feature, auto-commit, or main-writing integration.

#### Scenario: Superseded change is non-dispatchable

- **WHEN** a workflow inspects this change for implementation
- **THEN** it SHALL find no executable task or work package
- **AND** SHALL direct the caller to
  `add-deterministic-context-producer-checks`
- **AND** SHALL NOT modify hooks, cleanup-feature, validate-feature, or main

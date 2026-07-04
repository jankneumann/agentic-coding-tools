## ADDED Requirements

### Requirement: Task Routing Decision

The coordinator SHALL provide `POST /route/task` returning vendor, location (local or cloud), model, isolation, dispatch mode, and a rationale for a given task routing profile.

#### Scenario: Deterministic explainable decision

WHEN a synthetic task profile is submitted
THEN the router SHALL return a deterministic decision with a human-readable rationale.

#### Scenario: Config-driven rules

WHEN routing rules in routing.yaml change
THEN routing decisions SHALL change accordingly with no code edits.

### Requirement: Routing Decision Audit

Every routing decision SHALL be recorded to the audit log with its rationale.

#### Scenario: Phase dispatch logged

WHEN an autopilot phase dispatch is routed
THEN a routing audit record SHALL exist containing the decision, its inputs, and the rationale.

### Requirement: Router Degradation

The routing client SHALL fall back to a local static routing table with the same output shape when the coordinator is unreachable.

#### Scenario: Coordinator down

WHEN `/route/task` is unreachable
THEN dispatch SHALL proceed using the static fallback
AND the decision SHALL be marked as fallback-sourced.

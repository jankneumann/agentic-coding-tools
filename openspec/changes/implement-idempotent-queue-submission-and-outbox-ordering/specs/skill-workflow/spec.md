## ADDED Requirements

### Requirement: Outbox-Ordered Optional Queue Projection

The autopilot state machine SHALL provide an optional queue-projection callback that runs only after the authoritative `loop-state.json` write succeeds. Projection failure SHALL leave the new loop-state durable and SHALL be repairable by invoking reconciliation from the loaded loop-state on resume. With no callback, the state machine SHALL perform no coordinator import, probe, or request.

#### Scenario: State persists before projection

- **GIVEN** a phase transition produces a new loop-state
- **AND** a coordinated caller injected a projection callback
- **WHEN** the transition is persisted
- **THEN** the loop-state write SHALL complete before the callback begins
- **AND** a callback failure SHALL NOT revert the persisted state

#### Scenario: Crash window repairs on resume

- **GIVEN** a process terminates after loop-state persistence but before queue submission
- **WHEN** autopilot resumes with a coordinated reconciliation callback
- **THEN** it SHALL load the authoritative loop-state first
- **AND** it SHALL request reconciliation for the loaded `(change_id, phase, iteration)` before phase execution
- **AND** it SHALL NOT derive any loop-state field from the queue response

#### Scenario: Fallback tiers remain coordinator-free

- **GIVEN** local-parallel or sequential execution supplies no projection callback
- **WHEN** the state machine starts, transitions, or resumes
- **THEN** it SHALL make zero coordinator queue calls
- **AND** existing execution behavior SHALL remain unchanged

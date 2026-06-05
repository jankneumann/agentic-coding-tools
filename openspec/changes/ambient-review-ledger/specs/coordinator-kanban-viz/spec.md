## ADDED Requirements

### Requirement: Review-ledger swimlane

The Kanban board SHALL render a review-ledger swimlane that displays
finding-ledger state, updating live from the existing SSE event stream.

#### Scenario: Ledger findings render as cards

- **WHEN** the Kanban board is open and the review ledger contains findings
- **THEN** the board SHALL display a review-ledger swimlane with one card per
  finding, showing severity, lifecycle state (`open`/`addressed`/`retired`), and
  reviewer vendor
- **AND** cards SHALL be grouped or filterable by lifecycle state

#### Scenario: Live update on ledger change

- **WHEN** a finding is added, transitions lifecycle state, or is retired by
  `compact`
- **THEN** the board SHALL reflect the change via the SSE stream without a manual
  refresh

#### Scenario: Swimlane degrades gracefully without ledger data

- **WHEN** no review ledger is present for the active context
- **THEN** the swimlane SHALL render an empty state rather than an error

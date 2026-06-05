## ADDED Requirements

### Requirement: Local-first finding ledger

The system SHALL persist review findings in a local-first ledger at
`.review-ledger/` that survives across commits and sessions, and SHALL sync the
ledger to the coordinator when it is reachable.

#### Scenario: Finding written to local ledger

- **WHEN** a review (ambient or gate) produces a finding
- **THEN** the finding SHALL be written to the local ledger as the source of
  truth, keyed by a stable finding id
- **AND** the write SHALL succeed even when the coordinator is unreachable

#### Scenario: Best-effort coordinator sync

- **WHEN** the coordinator is reachable after a local ledger write
- **THEN** the ledger SHALL sync the finding to the coordinator
  (`memory`/`audit`) idempotently on the stable finding id
- **AND** a sync failure SHALL NOT lose or corrupt the local ledger entry

### Requirement: Finding lifecycle states

Each ledger finding SHALL carry a lifecycle state of `open`, `addressed`, or
`retired`, and the ledger SHALL record transitions between these states.

#### Scenario: New finding starts open

- **WHEN** a finding is first written to the ledger
- **THEN** its lifecycle state SHALL be `open`

#### Scenario: Finding marked addressed

- **WHEN** a subsequent commit changes the code referenced by an `open` finding
- **THEN** the ledger MAY transition the finding to `addressed` pending
  re-verification

### Requirement: Compact re-verification pass

The system SHALL provide a `compact` operation that re-checks `open` and
`addressed` findings against the current `HEAD`, retires findings that no longer
apply, and consolidates duplicate findings.

#### Scenario: Stale finding retired

- **WHEN** `compact` runs and an `open` finding references code that no longer
  exists or has been fixed at current `HEAD`
- **THEN** `compact` SHALL transition that finding to `retired` with a reason
- **AND** the finding SHALL NOT be reported as outstanding thereafter

#### Scenario: Duplicate findings consolidated

- **WHEN** `compact` runs and two ledger findings match under the
  `consensus_synthesizer` matching logic (same file/line/type or similar
  description above threshold)
- **THEN** `compact` SHALL consolidate them into a single ledger entry rather
  than reporting both

#### Scenario: Live finding preserved

- **WHEN** `compact` runs and an `open` finding still applies at current `HEAD`
- **THEN** the finding SHALL remain `open` and be unchanged except for
  re-verification metadata

### Requirement: Ledger feeds gate-time review

Gate-time review skills SHALL be able to read the curated ledger as warm
starting context, and the ambient ledger SHALL NOT replace or weaken gate-time
multi-vendor consensus.

#### Scenario: Gate review reads the ledger

- **WHEN** a gate-time review skill begins for a change with an existing ledger
- **THEN** it SHALL be able to load outstanding (`open`) ledger findings for the
  in-scope files as prior context
- **AND** it SHALL still perform its full multi-vendor consensus review

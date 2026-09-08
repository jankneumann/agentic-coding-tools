# gen-eval-framework — descriptor model naming levels

## ADDED Requirements

### Requirement: Descriptor Model Naming Levels

Descriptor model type names SHALL encode the level they describe: a type naming
a single surface element, or a per-surface container of elements, SHALL use the
`Spec` suffix, and a type naming a whole descriptor document SHALL use the
`Descriptor` suffix.

No single suffix SHALL denote both levels.

#### Scenario: Element and document types are distinguishable by name

- **WHEN** a reader encounters a descriptor model type name
- **THEN** the suffix SHALL indicate whether it names one element or a whole
  document
- **AND** no single suffix SHALL denote both levels

#### Scenario: A renamed element type is reachable under its new name

- **WHEN** a caller imports a renamed element type by its `Spec` name
- **THEN** the import SHALL succeed
- **AND** the type SHALL carry the fields it carried before the rename

### Requirement: Renamed Published Types Retain Warning Aliases

A rename of a model type published in the versioned descriptor schema SHALL
retain a deprecation alias under the previous name for at least one release.

Accessing an alias SHALL emit a deprecation warning naming the replacement.

A rename of a published model type SHALL increment the descriptor contract
version.

A subsequent change MAY reclaim a previous name for a different type before the
alias window elapses. Such a reclamation SHALL increment the descriptor contract
version and SHALL be announced to downstream consumers, because a reclaimed name
resolves successfully while denoting something else — a failure mode a
deprecation warning does not cover.

#### Scenario: A reclaimed name is announced rather than silently rebound

- **WHEN** a change assigns a previously-aliased name to a different type
- **THEN** the descriptor contract version SHALL be incremented
- **AND** the reclamation SHALL be recorded in a downstream notice naming both
  the old and the new meaning

#### Scenario: An old name still resolves and warns

- **WHEN** a caller imports a renamed type under its previous name
- **THEN** the import SHALL succeed
- **AND** a deprecation warning naming the replacement SHALL be emitted

#### Scenario: An alias that does not warn fails the gate

- **WHEN** a previous name resolves without emitting a deprecation warning
- **THEN** verification SHALL fail
- **AND** the absence of a warning SHALL NOT be treated as satisfying the alias
  requirement

#### Scenario: Renaming a published type bumps the contract version

- **WHEN** a model type published in the versioned descriptor schema is renamed
- **THEN** the descriptor contract version SHALL be incremented
- **AND** every generated contract artifact carrying that version SHALL be
  regenerated

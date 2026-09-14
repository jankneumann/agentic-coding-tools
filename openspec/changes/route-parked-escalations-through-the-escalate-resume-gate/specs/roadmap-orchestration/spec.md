## ADDED Requirements

### Requirement: Delegated Batch Apply Admits the Current Unapplied Cohort

A delegated batch apply SHALL require results for exactly the persisted attempts whose current application journal state is not `effects_applied`. It SHALL reject an empty required cohort, duplicate results, missing current results, and results for already-applied peers before any callback or durable state mutation. For every required attempt it SHALL retain exact dispatch identity, current lease generation, isolation, evidence, result-digest, and at-most-once journal validation.

#### Scenario: Initial batch remains exact

- **WHEN** a newly launched two-member delegated batch has no attempt with journal state `effects_applied`
- **THEN** apply SHALL require one current valid result for each member
- **AND** a missing result SHALL fail before either callback is invoked

#### Scenario: Resumed member applies without historical peer

- **WHEN** member A of a two-member batch parked, member B reached `effects_applied`, and authorized resume launches A at generation G+1
- **THEN** apply SHALL accept A's current-generation result as the complete required cohort
- **AND** it SHALL not access, revalidate, or invoke B's historical callback
- **AND** A and B SHALL retain their respective durable outcomes

#### Scenario: Historical and stale results fail closed

- **WHEN** the required cohort contains a resumed member
- **THEN** a supplied already-applied peer result or a pre-resume result SHALL be rejected before callback
- **AND** a terminal-persisted member that is not yet `effects_applied` SHALL remain required for recovery

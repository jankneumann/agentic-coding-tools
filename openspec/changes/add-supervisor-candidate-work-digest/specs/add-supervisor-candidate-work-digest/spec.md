## ADDED Requirements

### Requirement: Add supervisor candidate-work digest

The system SHALL deliver the outcomes below. This requirement is a preliminary
sketch generated from roadmap item `ri-13` and is refined by
`/plan-feature` before implementation.

#### Scenario: A supervise session produces a ranked digest of schema-valid…

- **WHEN** the roadmap item is implemented
- **THEN** A supervise session produces a ranked digest of schema-valid candidate stubs on request or at its periodic checkpoint

#### Scenario: Approving a stub from the digest routes it into /plan-roadmap…

- **WHEN** the roadmap item is implemented
- **THEN** Approving a stub from the digest routes it into /plan-roadmap without leaving the conversation

#### Scenario: Digest state (last-digested stubs, standing decisions) survives…

- **WHEN** the roadmap item is implemented
- **THEN** Digest state (last-digested stubs, standing decisions) survives session rehydration via the handoff record

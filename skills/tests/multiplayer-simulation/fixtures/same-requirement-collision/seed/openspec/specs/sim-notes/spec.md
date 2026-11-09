# sim-notes Specification

## Purpose

Seeded capability for the multiplayer-simulation harness. It exists only inside
simulated worlds.

## Requirements

### Requirement: Note Titles

The system SHALL require every note to carry a non-empty title.

#### Scenario: Title required

- **WHEN** a note is saved without a title
- **THEN** the save is rejected

### Requirement: Note Bodies

The system SHALL accept note bodies of up to 10000 characters.

#### Scenario: Long body

- **WHEN** a note body exceeds 10000 characters
- **THEN** the save is rejected

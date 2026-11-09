## ADDED Requirements

### Requirement: Sync-Point Guard Scope Declaration

The trust posture contract front matter SHALL accept an optional top-level
`sync_point` mapping with one field, `active_agent_guard`, whose value SHALL be
one of `repo-wide`, `overlap`, or `off`. When the mapping, the field, or the
contract file is absent, the loader SHALL resolve the mode to `overlap`. The
loader SHALL reject, as a validation error, a `sync_point` value that is not a
mapping, an unknown field inside it, or an `active_agent_guard` value outside
the closed set; it SHALL NOT silently fall back for a malformed value. The
posture digest SHALL cover the declared mode, and a posture that declares none
SHALL produce the same digest as it did before this field existed.

The loader SHALL expose `active_agent_guard_mode(posture)` returning the
resolved mode, accepting the absent-posture value.

#### Scenario: Absent key resolves to overlap

- **WHEN** the contract file is absent, or present without a `sync_point`
  mapping
- **THEN** `active_agent_guard_mode` MUST return `overlap`
- **AND** the posture digest MUST equal the digest of the same contract before
  this field existed

#### Scenario: Declared mode is returned

- **WHEN** the contract declares `sync_point: {active_agent_guard: repo-wide}`
- **THEN** `active_agent_guard_mode` MUST return `repo-wide`
- **AND** the posture digest MUST differ from the digest with the key absent

#### Scenario: Unknown mode is a validation error

- **WHEN** the contract declares `sync_point: {active_agent_guard: lenient}`
- **THEN** loading the contract MUST fail with a validation error that names
  the field and the accepted values
- **AND** no sync-point skill MUST proceed on that contract

#### Scenario: Unknown field is a validation error

- **WHEN** the contract declares `sync_point: {active_agent_guard: overlap, stale_hours: 2}`
- **THEN** loading the contract MUST fail with a validation error naming the
  unknown field

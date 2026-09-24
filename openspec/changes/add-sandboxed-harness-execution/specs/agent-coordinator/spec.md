## ADDED Requirements

### Requirement: Cloud dispatches SHALL carry per-dispatch coordinator identities

Each remote dispatch SHALL authenticate to the coordinator HTTP API with its own
short-lived identity, distinct per dispatch, so that revocation and audit are
per-dispatch rather than per-installation.

#### Scenario: Distinct identity per dispatch

- **WHEN** two remote dispatches are created from the same dispatcher
- **THEN** each SHALL hold a distinct coordinator API identity
- **AND** ledger and audit records SHALL attribute activity to the individual
  dispatch identity.

#### Scenario: Revocation isolates one dispatch

- **WHEN** a single dispatch identity is revoked
- **THEN** subsequent coordinator requests bearing that identity SHALL be rejected
- **AND** other in-flight dispatches SHALL be unaffected
- **AND** the revoked dispatch SHALL be marked failed in the ledger rather than
  left indeterminate.

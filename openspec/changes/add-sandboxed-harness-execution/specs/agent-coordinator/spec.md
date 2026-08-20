## ADDED Requirements

### Requirement: Network policy SHALL be exportable as a rendering input

The coordinator SHALL expose an export of the active network policy in a shape
consumable by execution-backend renderers, so that every enforced allowlist —
local sandbox settings and cloud sandbox egress rules alike — is a rendering of
the single authored policy.

#### Scenario: Enforced egress derives from the authored policy

- **WHEN** a backend renders an egress allowlist for a dispatch
- **THEN** every permitted destination SHALL derive from the exported coordinator
  policy
- **AND** no destination SHALL be introduced that the authored policy does not
  permit.

#### Scenario: Export unavailable narrows, never widens

- **WHEN** the policy export is unreachable at render time
- **THEN** the renderer SHALL fall back to the documented static minimum
  (coordinator hostname, git remote, inference gateway)
- **AND** the fallback SHALL NOT be wider than the last known exported policy
- **AND** an audit event SHALL record that the fallback was used.

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

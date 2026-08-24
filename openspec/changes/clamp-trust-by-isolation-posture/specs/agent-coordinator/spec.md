## ADDED Requirements

### Requirement: Effective trust is the vendor ceiling clamped by isolation posture

The coordinator SHALL compute an agent's effective trust level as the minimum
of the vendor trust ceiling declared for its identity and a cap derived from
the runtime's isolation posture, and SHALL use the effective value wherever
authorization compares against trust. The clamp SHALL be computed in exactly
one place (profile resolution) so no enforcement point can observe the
unclamped ceiling.

The vendor ceiling expresses how much the vendor's judgment is trusted at its
best; the posture cap expresses how much damage the runtime can do if that
judgment fails. Neither alone answers what an agent should be allowed to do.

#### Scenario: Contained runtime earns its vendor ceiling

- **WHEN** an agent whose vendor ceiling is 3 authenticates with a key whose
  identity records posture `fs=sandbox, net=open` (cap 3)
- **THEN** its effective trust SHALL be 3
- **AND** trust-gated operations requiring level 3 SHALL be authorized

#### Scenario: Raw filesystem runtime is clamped below its ceiling

- **WHEN** an agent whose vendor ceiling is 3 authenticates with a key whose
  identity records posture `fs=none, net=open` (cap 2)
- **THEN** its effective trust SHALL be 2
- **AND** operations requiring level 3 SHALL be denied
- **AND** automated verification applicable at level 2 SHALL remain in force

#### Scenario: Low vendor ceiling is never raised by strong isolation

- **WHEN** an agent whose vendor ceiling is 1 runs with posture
  `fs=vm, net=restricted` (cap 4)
- **THEN** its effective trust SHALL be 1

### Requirement: Posture caps are configuration with a conservative fallback

The posture→cap mapping SHALL be loaded from YAML policy configuration rather
than encoded in source, and SHALL resolve any unknown, partial, or unmapped
posture to the most conservative applicable cap. An identity entry that
records no isolation posture SHALL be treated as `fs=none, net=open`.

Every key minted before posture recording existed has no `isolation` field;
those identities must degrade safely rather than crash or — worse — default
open.

#### Scenario: Legacy identity without posture gets the conservative default

- **WHEN** an agent authenticates with an identity entry that has no
  `isolation` field
- **THEN** the clamp SHALL apply the cap mapped to `fs=none, net=open`

#### Scenario: Unrecognized posture value falls back conservatively

- **WHEN** an identity records a posture whose fs or net value is absent from
  the configured mapping
- **THEN** the clamp SHALL apply the most conservative cap in the mapping
- **AND** the resolution SHALL be recorded in the decision's audit context

### Requirement: Session posture reports are downgrade-only

The coordinator SHALL accept a self-reported isolation posture on session
registration and heartbeat, SHALL apply the minimum of the asserted cap and
the reported cap for the session's lifetime, and SHALL NOT allow a
self-report to raise the effective cap above the enrollment assertion. Any
difference between reported and asserted posture SHALL emit a
`posture_mismatch` audit event carrying both postures and the cap that won.

Detection runs client-side and is therefore untrusted for privilege
escalation: an agent claiming a VM it does not have must gain nothing. The
honest direction — an agent discovering it is less contained than the
operator believed — must tighten its leash and leave an audit trail, because
it means the host is not configured as asserted.

#### Scenario: Honest downgrade tightens the session

- **WHEN** a session whose enrollment asserts `fs=sandbox` reports detected
  posture `fs=none`
- **THEN** the session's effective cap SHALL be the cap for `fs=none`
- **AND** a `posture_mismatch` audit event SHALL record both postures

#### Scenario: Claimed upgrade gains nothing

- **WHEN** a session whose enrollment asserts `fs=none` reports detected
  posture `fs=vm, net=restricted`
- **THEN** the session's effective cap SHALL remain the cap for the asserted
  posture
- **AND** a `posture_mismatch` audit event SHALL record both postures

#### Scenario: Absent self-report leaves the assertion in force

- **WHEN** a session registers without reporting a detected posture
- **THEN** the enrollment-asserted posture SHALL determine the cap
- **AND** no `posture_mismatch` event SHALL be emitted

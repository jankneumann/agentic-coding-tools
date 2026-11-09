# agent-coordinator Specification (delta)

## ADDED Requirements

### Requirement: Atomic API-Key Identity Reload

When OpenBao is configured, the coordinator SHALL load every keyed registry agent's API key using the dedicated identity-reader service principal and build an immutable candidate identity map. It SHALL validate completeness, uniqueness, and shape before atomically replacing the active map. Successful reloads SHALL occur on a 30-second default cadence and make a valid key rotation observable within 60 seconds without process restart. Request authentication SHALL read exactly one installed snapshot per request. Static `X-API-Key` HTTP authentication SHALL remain in use until pca-03; this change SHALL not introduce session tokens.

When OpenBao is configured, the installed snapshot SHALL be the sole accepted
API-key allowlist. `COORDINATION_API_KEYS` SHALL NOT authorize a key absent from
that snapshot, including a rotated or unbound key. The 120-second age gate SHALL
apply before any identity lookup. Non-OpenBao mode SHALL retain the existing
static allowlist semantics. Configured-Bao cutover preflight SHALL report any `COORDINATION_API_KEYS` entry without a registry-bound identity as a blocker; there SHALL be no unbound service-key exception in pca-02.

#### Scenario: COORD-01 Rotation becomes active without restart

- **GIVEN** a complete installed identity snapshot
- **WHEN** one agent key is rotated in its own OpenBao document
- **THEN** the next successful reload SHALL atomically install the new complete map within 60 seconds
- **AND** the old key SHALL stop authenticating after installation

#### Scenario: COORD-02 Partial candidate never leaks

- **WHEN** one of several required agent reads fails or returns a duplicate or malformed key
- **THEN** no part of the candidate map SHALL become active
- **AND** an authentication request SHALL observe the previous complete snapshot or denial

#### Scenario: COORD-09 Static allowlist cannot bypass rotation

- **WHEN** OpenBao is configured and an old or unbound key remains in `COORDINATION_API_KEYS` after a successful rotation
- **THEN** that key SHALL be denied because it is absent from the installed identity snapshot
- **AND** the new key SHALL resolve to its declared principal

### Requirement: Bounded Identity Reload Degradation

On a configured OpenBao refresh failure, the coordinator SHALL retain the last-known-good identity snapshot for no longer than 120 seconds measured from its last successful installation, emit a sanitized audit event, and report degraded readiness. Once that age exceeds 120 seconds, it SHALL deny new API-key authentication until a valid complete snapshot is installed. Startup without a valid complete snapshot SHALL deny new API-key authentication and report degraded readiness. Every successful complete refresh SHALL clear the degraded state. The audit record SHALL include failure class, principal/path identifier when safe, snapshot age, and outcome, without key values, tokens, SecretIDs, wrapping tokens, or raw backend responses.

#### Scenario: COORD-03 Failed refresh within grace window

- **GIVEN** a complete snapshot installed 60 seconds ago
- **WHEN** the next refresh fails
- **THEN** the installed snapshot SHALL remain active
- **AND** readiness SHALL be degraded and a sanitized failure SHALL be audited

#### Scenario: COORD-04 Grace window expires

- **GIVEN** the last successful complete snapshot was installed more than 120 seconds ago
- **WHEN** a new API-key authentication is attempted
- **THEN** authentication SHALL be denied even if its key exists in the stale map
- **AND** readiness SHALL remain degraded

#### Scenario: COORD-05 Recovery installs whole snapshot

- **GIVEN** the coordinator is degraded after failed refreshes
- **WHEN** a complete valid refresh succeeds
- **THEN** it SHALL atomically install the new map, restore ready identity status, and audit recovery

#### Scenario: COORD-06 Startup cannot hydrate identities

- **WHEN** OpenBao is configured and the first complete identity load fails
- **THEN** no partial or static identity map SHALL be accepted
- **AND** readiness SHALL report identity degradation and new API-key authentication SHALL be denied

### Requirement: Credential Failure Audit and Readiness Contract

The coordinator SHALL expose identity reload health as a distinct readiness component so operators can distinguish it from database and unrelated optional-service health. A configured OpenBao authentication, authorization, timeout, missing-data, or malformed-data failure SHALL use the shared typed error taxonomy and produce a sanitized audit event. Error handling SHALL never substitute an ambient key, `.secrets.yaml`, or `secret/coordinator` data. Health and audit payloads SHALL not disclose credentials or raw `hvac` responses. During the 120-second last-known-good grace period, `/ready` SHALL return HTTP 200 with `identity: degraded`; startup failure or an expired snapshot SHALL return HTTP 503. This keeps the documented grace period routable while exposing degradation in the component field and audit stream.

#### Scenario: COORD-07 Typed backend failure is observable

- **WHEN** the identity reader receives an OpenBao permission denial
- **THEN** readiness SHALL identify the credential component as degraded
- **AND** the audit event SHALL identify `AUTHORIZATION_DENIED` as the error code without secret material

#### Scenario: COORD-10 Non-OpenBao readiness

- **WHEN** `BAO_ADDR` is absent and the database is healthy
- **THEN** `/ready` SHALL report `identity: disabled` and remain HTTP 200

#### Scenario: COORD-08 Database health is independent

- **WHEN** identity reload is degraded while the database is healthy
- **THEN** the readiness response SHALL show those component states separately

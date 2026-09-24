## ADDED Requirements

### Requirement: Network policy SHALL be exportable for one exact agent

The coordinator SHALL export the enabled global rules plus the exact agent's profile-specific
rules as a versioned, deterministic, default-deny document. Each export SHALL carry the exact
agent id, normalized ordered rules, schema revision, and content digest. Any malformed applicable
legacy rule SHALL make the whole export unrenderable; rules SHALL NOT be silently omitted.

The authenticated principal MAY export its own policy. Exporting another agent's policy requires
trust level 3 or greater so the dispatch host can prepare a child without granting arbitrary agents
cross-agent policy discovery.

#### Scenario: Exact-agent export preserves authored rules

WHEN an agent has profile-specific and global network rules
THEN export SHALL include only that profile's enabled rules and enabled global rules
AND profile-specific precedence and authored priority SHALL be explicit.

#### Scenario: Rendering never widens policy

WHEN authored precedence cannot be represented exactly by SRT deny-first semantics
THEN the exported rules SHALL render to a conservative narrower result
AND no destination absent from the authored effective policy SHALL be introduced.

#### Scenario: Policy outage denies network

WHEN an exact-agent export is unavailable or malformed at cold start
THEN sandbox preparation SHALL use a valid deny-all network document
AND SHALL NOT fall back to an independently maintained destination list.

### Requirement: Sandbox execution events SHALL be durably auditable

The coordinator SHALL accept a narrow sandbox execution event and SHALL not acknowledge durable
success until the audit row is inserted. `event_id` SHALL be an idempotency key and replay SHALL
return the original audit row id. Events SHALL include routing correlation, execution location and
scope, requested and applied isolation, runtime/preflight outcome, policy revision/digest,
canonical root, executable paths, allowed environment key names, and degradation reason without
secret values.

The request's `agent_id` names the target CLI lane; the audit actor SHALL be derived from the
authenticated principal and SHALL NOT be accepted from request JSON. Recording an event for
another agent requires trust level 3 or greater.

#### Scenario: Durable degradation event precedes fallback

WHEN sandbox preflight permits an unsandboxed fallback
THEN the coordinator SHALL persist `applied=false` before acknowledging the event
AND the fallback process SHALL not start before acknowledgement or a durable local outbox write.

#### Scenario: Secret values are excluded

WHEN a sandbox execution event is persisted
THEN environment metadata SHALL contain key names only
AND argv prompt bodies, credential values, and settings-file contents SHALL be absent.

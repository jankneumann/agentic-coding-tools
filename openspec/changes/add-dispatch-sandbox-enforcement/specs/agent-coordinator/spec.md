## ADDED Requirements

### Requirement: Network policy SHALL be exportable for one exact agent

The coordinator SHALL export the enabled global rules plus the exact agent's profile-specific
rules as a versioned, deterministic, default-deny document. Each export SHALL carry the exact
agent id, normalized ordered rules, schema revision, and canonical content digest. Any malformed
applicable legacy rule SHALL make the whole export unrenderable; rules SHALL NOT be silently
omitted. The digest SHALL cover canonical UTF-8 JSON for every snapshot field except the digest
itself, and applied execution events SHALL copy the exact revision and digest they enforced.

The authenticated principal MAY export its own policy. Exporting another agent's policy requires
trust level 3 or greater so the dispatch host can prepare a child without granting arbitrary agents
cross-agent policy discovery.
The exact agent SHALL have an enabled profile assignment; unknown, disabled, or unassigned agents
SHALL return a typed 404/409 and SHALL NOT receive a global-only export. Ordering SHALL be total:
profile before global, priority ascending (preserving legacy lower-is-higher semantics), deny before
allow on ties, then policy id ascending.
The empty revision SHALL be `v1:none:0`.

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
THEN sandbox preparation SHALL fail closed before vendor process start
AND SHALL NOT synthesize a destination list or treat the outage as fail-open.

### Requirement: Sandbox execution events SHALL be durably auditable

The coordinator SHALL accept a narrow sandbox execution event and SHALL not acknowledge durable
success until the audit row is inserted. `event_id` SHALL be generated once by the caller, remain
stable through outbox replay, and be an idempotency key; replay SHALL return the original audit row
id and `replayed=true`. Events SHALL include routing correlation and full-context digest, execution
location and authored scope/write capability, requested and applied isolation, runtime/preflight
outcome, policy revision/digest and endpoint digest (never raw endpoint credentials), canonical
root, executable paths, allowed environment key names, and degradation reason without secret
values.

The server SHALL author `created_at`. `sandbox_applied=true` SHALL require the SRT backend,
successful preflight, non-null runtime/policy/settings/root evidence, and no degradation reason.
`sandbox_applied=false` SHALL require a degradation reason. Cleanup failure SHALL carry residual
owned paths.

The request's `agent_id` names the target CLI lane; the audit actor SHALL be derived from the
authenticated principal and SHALL NOT be accepted from request JSON. Recording an event for
another agent requires trust level 3 or greater.

#### Scenario: Durable degradation event precedes fallback

WHEN sandbox preflight permits an unsandboxed fallback
THEN the coordinator SHALL persist `applied=false` before acknowledging the event
AND the fallback process SHALL not start before acknowledgement or a durable local outbox write.

#### Scenario: Permanent outbox rejection does not poison later evidence

WHEN an older queued event receives a permanent 4xx response during drain
THEN that record SHALL move atomically to a durable dead-letter file with response metadata
AND later queued records MAY continue draining
AND a live event receiving 4xx SHALL fail closed rather than enter the outbox.

#### Scenario: Secret values are excluded

WHEN a sandbox execution event is persisted
THEN environment metadata SHALL contain key names only
AND argv prompt bodies, credential values, and settings-file contents SHALL be absent.

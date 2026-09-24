## ADDED Requirements

### Requirement: Typed Configured Lane Registry

The coordinator SHALL expose every configured `AgentEntry` as a lane keyed by `agent_id`,
with separately typed `vendor_type`, `policy_vendor`, `catalog_vendor`, and
`location: local|cloud|unknown`. Bundled configuration SHALL declare location and identity
mapping explicitly; implementations SHALL NOT infer them from lane names, commands, or catalog
publishers.

#### Scenario: List configured lanes

WHEN an authorized client requests `GET /vendors`
THEN every configured lane SHALL include identity fields, location, capabilities, archetypes,
isolation, transport, dispatch modes, dispatchability, effective availability, and catalog price
projections.

#### Scenario: Dispatchability is configuration, not health

WHEN a lane has an executable configured transport or adapter
THEN `dispatchable` SHALL be true independently of live availability
AND automatic candidates SHALL require both dispatchability and eligible availability.

#### Scenario: Filter eligible lanes

WHEN a client supplies capability, archetype, dispatch-mode, location, or available-only filters
THEN every returned lane SHALL satisfy all supplied filters.

#### Scenario: Lane-specific state

WHEN one of two lanes for the same vendor type is unavailable
THEN their availability SHALL remain independent
AND provider-level consumers MAY group them by `vendor_type`.

#### Scenario: Unknown or ambiguous identity

WHEN a request names an unknown lane or a provider-only identity matching multiple lanes
THEN the coordinator SHALL reject it without creating or fanning out state.

### Requirement: Catalog-Owned Cost and Local Health

The registry SHALL batch-project price and local health from dg-00 `model_catalog` using explicit
configured join fields and SHALL NOT persist a second price table.

#### Scenario: Exact catalog projection

WHEN a lane has models authored in its CLI/SDK config or existing provider model map
THEN exact model ID SHALL be the primary catalog join, endpoint kind/base URL SHALL constrain it
when configured, optional catalog vendor SHALL further constrain it, and returned rows SHALL include
model, endpoint, prompt/completion price, availability, refreshed time, and stale provenance.

#### Scenario: Missing or ambiguous catalog row

WHEN no unique configured join can identify a catalog row
THEN the cost projection and request quote SHALL be unknown
AND the miss SHALL be audited without heuristic matching.

#### Scenario: Local catalog gate

WHEN a lane with `endpoint_kind=local` has no non-stale available matching catalog model
THEN it SHALL NOT be reported available even if its readiness probe succeeds
AND location-local cloud CLI lanes SHALL NOT be subjected to this gate.

#### Scenario: Request-scoped quote

WHEN policy supplies an exact model plus estimated prompt and completion token counts
THEN the registry price projection SHALL produce the decimal USD quote defined in D8
AND static tiers SHALL NOT populate USD deltas or enforce USD ceilings.

### Requirement: Fresh Probe Availability

The existing watchdog SHALL persist every lane probe snapshot, including the first baseline, with
`stale_after = observed_at + 2 × VENDOR_HEALTH_INTERVAL_SECONDS`.

#### Scenario: First watchdog poll

WHEN the watchdog completes its first vendor-health poll
THEN it SHALL persist each snapshot without emitting transition events.

#### Scenario: Later transition

WHEN a later poll changes health
THEN it SHALL refresh the snapshot and preserve existing `vendor.unavailable` or
`vendor.recovered` events.

#### Scenario: Probe becomes stale

WHEN current time is at or after `stale_after`
THEN the probe SHALL contribute `unknown`, not its old status.

#### Scenario: Lane has no probe method

WHEN a configured lane has no CLI or other readiness probe
THEN watchdog SHALL persist `unknown` with reason `no_probe_method` rather than omit it.

#### Scenario: Snapshot write fails

WHEN one lane snapshot cannot be persisted
THEN the failure SHALL be audited and logged
AND other snapshots and legacy transition events SHALL still be processed.

#### Scenario: Deployed probe

WHEN the coordinator watchdog runs in its production image
THEN it SHALL resolve the probe through `SKILLS_ROOT`, load the explicit `AGENTS_YAML` roster,
start independently of notification channels, and persist at least one configured snapshot.

### Requirement: Bounded Rate-Limit State

Authenticated dispatchers SHALL report lane-scoped rate limits with an idempotency key. Every
accepted limit SHALL have a server-normalized, non-null reset time bounded by configuration.

#### Scenario: Absolute or relative reset

WHEN exactly one of future `reset_at` or bounded `retry_after_seconds` is supplied
THEN the server SHALL normalize it to an absolute reset using server receipt time for retry-after.

#### Scenario: Reset is omitted

WHEN neither reset field is supplied
THEN the server SHALL apply `VENDOR_UNKNOWN_LIMIT_TTL_SECONDS` (default 900).

#### Scenario: Conflicting reset fields

WHEN both reset fields are supplied or a reset exceeds the configured maximum
THEN the coordinator SHALL reject the request.

#### Scenario: Replay and conflict

WHEN an observation ID is replayed with identical normalized content
THEN it SHALL be idempotent
BUT a replay with different content SHALL return conflict.

#### Scenario: Limit expires

WHEN current time is at or after reset
THEN the limit SHALL stop affecting availability, SHALL be omitted from active reads, and SHALL
be retained only for the bounded audit-retention period.

### Requirement: Authorized and Observable Ingestion

The coordinator SHALL bind observation identity to the authenticated principal, derive source and
receipt time server-side, and require either the explicit `report_vendor_rate_limit` operation or
a trust-level 3 administrative override for cross-lane writes.

#### Scenario: Principal reports own lane

WHEN a principal reports its own lane and the payload is valid
THEN the coordinator SHALL accept it and emit a structured audit record.

#### Scenario: Principal targets another lane

WHEN a dispatcher principal with `report_vendor_rate_limit` targets the concrete lane it dispatched
THEN the coordinator SHALL authorize the write even when source and target lanes differ.

#### Scenario: Principal lacks reporting authority

WHEN a non-administrator without the reporting operation targets another lane
THEN the coordinator SHALL return forbidden and SHALL NOT change state.

#### Scenario: Observation lifecycle telemetry

WHEN an observation is accepted, duplicated, rejected, expired, or compacted
THEN a structured audit/log record SHALL identify the lane, outcome, and non-secret reason.

### Requirement: Repository-Native Registry Bridge

The coordination bridge SHALL expose normalized list, availability-detail, and rate-limit write
helpers using existing authentication headers and existing status/operation/response-or-error
conventions.

#### Scenario: Coordinator is unavailable

WHEN a bridge operation encounters timeout, auth failure, not-found, server error, or malformed
payload
THEN it SHALL preserve that distinct error and SHALL NOT return an empty successful registry.

#### Scenario: Reporting fails after dispatch

WHEN a rate-limit report cannot be persisted
THEN the original dispatch result SHALL remain unchanged
AND the reporting failure SHALL be observable.

### Requirement: Exact Dispatcher Attribution

Dispatch result collectors SHALL report rate limits using the selected concrete `agent_id` and
available reset metadata.

#### Scenario: Adapter has lane context

WHEN a dispatcher classifies a terminal capacity failure
THEN its additive result carrier SHALL report the exact selected lane through the bridge once.

#### Scenario: One model limits before fallback succeeds

WHEN an adapter observes a model capacity failure and later succeeds on another model
THEN its per-attempt callback SHALL report the failed model as a model-scoped limit
AND the successful lane SHALL remain available for the fallback model.

#### Scenario: Legacy policy signal lacks lane

WHEN a legacy `vendor_limit:<policy_vendor>:<reason>` outcome has no
`dispatch_agent_id` in context
THEN the orchestrator SHALL skip durable persistence as ambiguous
AND SHALL exclude all lanes with that policy vendor for the current in-run decision only
AND SHALL record the skip and provider-scope exclusion in structured decision provenance.

### Requirement: Registry-Driven Roadmap Policy

The roadmap orchestrator SHALL obtain eligible lanes from a registry provider rather than a
hardcoded roster and SHALL preserve lane identity through selection and decision provenance.

#### Scenario: Registry is available

WHEN a roadmap dispatch is limited with a concrete lane
THEN candidates SHALL satisfy required capability, phase archetype, dispatch mode, location, model
limit, and effective availability
AND only the concrete limited lane SHALL be excluded before provider grouping.

#### Scenario: Registry is unavailable

WHEN the registry read fails
THEN automatic switching SHALL fail closed by default
UNLESS an explicit policy permits an injected agents.yaml-derived provider with unknown
availability
AND no fallback SHALL embed availability, prices, or a vendor roster.

#### Scenario: Cost ceiling has no exact quote

WHEN policy configures a USD ceiling but structured model/token estimates or catalog price are absent
THEN static tiers SHALL NOT enforce the ceiling
AND the decision SHALL record `cost_guard=unavailable` and continue under availability policy.

#### Scenario: Model-scoped limit has an alternate model

WHEN one model is limited but the same lane has another eligible model
THEN the lane SHALL remain available for the alternate model.

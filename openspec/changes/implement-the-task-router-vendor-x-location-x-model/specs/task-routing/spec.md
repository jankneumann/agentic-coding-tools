## ADDED Requirements

### Requirement: One additive routing surface

The coordinator SHALL extend `POST /routing/select_model` and its
`select_model_for_task` MCP mirror with task-profile and assignment fields, and SHALL NOT
add a second task-routing endpoint or scoring path.

#### Scenario: Existing HTTP and MCP surfaces stay aligned

- **WHEN** the same valid task-routing request is submitted through HTTP and direct MCP
- **THEN** both surfaces SHALL validate the same typed profile and return the same
  assignment/provenance shape
- **AND** no `POST /route/task` route SHALL be registered.

#### Scenario: Legacy caller remains compatible

- **WHEN** a caller sends only the dg-00 `task_signals.archetype` field
- **THEN** the request SHALL remain valid
- **AND** newly added inputs SHALL use additive defaults
- **AND** every successful response SHALL include non-null additive assignment and
  provenance
- **AND** the top-level assignment SHALL equal `selected.assignment`.

### Requirement: Typed task-routing profile

The request SHALL type phase/archetype, expected duration, scope, interactivity, secret
need, parallelism, repository shape, roadmap policy, and optional location, isolation,
and dispatch-mode constraints at the HTTP/MCP boundary.

#### Scenario: Invalid profile is rejected at the boundary

- **WHEN** a task profile contains an invalid enum, negative duration, non-positive
  parallelism, or malformed policy constraint
- **THEN** HTTP SHALL return 422
- **AND** direct MCP SHALL return the existing matching validation-error envelope.

#### Scenario: Config rules consume typed signals

- **WHEN** a validated `routing.yaml` rule matches a task-profile field
- **THEN** its configured location, isolation, or dispatch-mode constraint SHALL be
  applied deterministically
- **AND** the matching rule ID SHALL be recorded in decision provenance.

### Requirement: Registry-backed feasibility precedes utility

The router SHALL consume `VendorRegistryService` in process and remove infeasible
lane/model assignments before invoking the existing dg-00 utility scorer. A periodic
configuration-backed job SHALL materialize missing non-OpenRouter catalog identities from
explicit lane metadata and the canonical provider model map without overwriting live
catalog observations.

#### Scenario: Configured lane identity is materialized

- **WHEN** a configured non-OpenRouter lane model is absent from `model_catalog`
- **THEN** the catalog job SHALL insert its explicit vendor, model, endpoint kind, and
  base URL identity
- **AND** SHALL NOT infer any field from agent-name or publisher-name heuristics
- **AND** SHALL NOT overwrite existing price, posterior, availability, or refresh data.

#### Scenario: Exact lane and catalog association

- **WHEN** a registry lane projects a catalog model
- **THEN** routing SHALL associate it only by the exact projected catalog vendor, model,
  endpoint-kind, and base-URL identity
- **AND** SHALL NOT infer association from agent ID suffixes, publisher names, or fuzzy
  model strings.

#### Scenario: Infeasible assignment cannot win

- **WHEN** a lane is unavailable, rate limited, lacks the archetype or dispatch mode, or
  violates location, isolation, or roadmap-policy constraints
- **THEN** the lane/model assignment SHALL be excluded before dg-00 utility scoring
- **AND** the exclusion SHALL carry a machine-readable reason.

#### Scenario: Missing exact projection is excluded

- **WHEN** a configured lane has no unique exact catalog projection
- **THEN** it SHALL be excluded as `registry:no-catalog-projection`
- **AND** routing SHALL NOT infer missing identity fields.

#### Scenario: Registry failure fails closed

- **WHEN** the in-process registry snapshot cannot be loaded or validated
- **THEN** routing SHALL fail with `routing-registry-unavailable`
- **AND** SHALL NOT score catalog-only candidates or infer a lane association.

#### Scenario: No feasible assignment preserves dg-00 wire compatibility

- **WHEN** registry and catalog reads succeed but no feasible assignment remains
- **THEN** HTTP SHALL return 503 with dg-00 detail `no feasible model-routing candidate`.

#### Scenario: Unprojected catalog candidate remains explainable

- **WHEN** a catalog row has no exact configured lane projection
- **THEN** it SHALL NOT enter utility scoring
- **AND** it SHALL appear in exclusions as `catalog:no-configured-lane`.

#### Scenario: Feasible assignments retain dg-00 ranking

- **WHEN** two or more lane/model assignments remain feasible
- **THEN** their quality, cost, latency, headroom, and exploration ranking SHALL be
  produced by the existing dg-00 scorer without a second utility function
- **AND** equal scores SHALL be ordered by agent ID and exact catalog identity.

### Requirement: Versioned deterministic routing policy

Routing dimension rules SHALL be loaded from a schema-validated `routing.yaml` carrying
an explicit schema version and policy version.

#### Scenario: Policy edit changes a decision

- **WHEN** a test changes a valid constraint rule or dispatch default in `routing.yaml`
- **THEN** the resulting assignment SHALL change without a Python code edit
- **AND** repeated evaluation of the same profile, registry snapshot, catalog snapshot,
  and policy SHALL produce the same ordered candidates when exploration is disabled.

#### Scenario: Invalid policy fails loud

- **WHEN** `routing.yaml` contains an unknown field, unsupported schema version, invalid
  enum, duplicate rule ID, or reference to an unconfigured phase dispatch default
- **THEN** policy loading SHALL fail before routing a task
- **AND** SHALL NOT silently substitute permissive defaults.

### Requirement: Additive assignment and provenance

Every selected candidate SHALL expose exact lane assignment fields and every persisted
decision SHALL retain the task profile, policy version/checksum, matched rules, excluded
assignments, and source.

#### Scenario: Coordinator decision is durable and auditable

- **WHEN** the coordinator returns a routing decision
- **THEN** the same decision ID and assignment SHALL be written to `routing_decisions`
- **AND** a link-only coordinator audit event SHALL record decision ID, selected
  agent/model, routing-policy version/checksum, source, and success
- **AND** both records SHALL commit atomically before the response is returned.

#### Scenario: Durable write cannot be established

- **WHEN** the atomic decision-and-audit RPC fails
- **THEN** neither record SHALL remain committed
- **AND** HTTP SHALL return 503 detail `routing-durability-unavailable`
- **AND** MCP SHALL return its existing matching 503 error envelope.

#### Scenario: Persistence projection is bounded

- **WHEN** permissive legacy task signals include undeclared values such as path lists
- **THEN** the request remains valid for compatibility
- **AND** persistence SHALL retain only declared task signals and the typed routing
  profile, excluding all legacy extras
- **AND** the nested roadmap-policy projection SHALL reject unknown fields, arbitrary path
  lists, oversized arrays, and oversized identifiers.

#### Scenario: Alternative candidates retain lane identity

- **WHEN** feasible alternatives are returned
- **THEN** each alternative SHALL retain its own exact `agent_id`, vendor type,
  location, isolation, dispatch mode, model, endpoint kind, and base URL.

### Requirement: Honest local fallback

A coordinator-unreachable client path SHALL derive a deterministic assignment only from
the checkout's validated `routing.yaml`, `agents.yaml`, archetype model map, and caller's
static model/provider inputs.

#### Scenario: Coordinator is unreachable

- **WHEN** the coordinator routing operation times out or is unreachable
- **THEN** the local helper SHALL evaluate the same ordered rules and dispatch defaults
- **AND** it SHALL select only an exact provider/model lane and configured dispatch mode
- **AND** remaining assignments SHALL be ordered by configured location, isolation, and
  dispatch-mode fallback order, then agent ID
- **AND** the returned normal assignment shape SHALL carry `fallback=true`,
  `source=local-static`, `persisted=false`, and `durable_audit=false`
- **AND** SHALL NOT embed a roster, synthesize live availability, or claim a coordinator
  audit record exists
- **AND** its catalog key SHALL be null because no live catalog join occurred.

#### Scenario: No exact local fallback lane exists

- **WHEN** no configured lane matches the caller's exact static provider/model and a
  supported dispatch mode
- **THEN** the helper SHALL raise a bounded local-fallback error
- **AND** the caller SHALL preserve its existing static result without fabricating an
  assignment.

#### Scenario: Existing static fallback equality is preserved

- **WHEN** existing `resolve_archetype_for_phase` adaptive routing is disabled, fails,
  returns malformed data, or exceeds its bounded timeout
- **THEN** the returned `ResolvedArchetype` SHALL equal the dg-00 static result exactly.

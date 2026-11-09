# Design: extend routing to vendor × location × isolation × dispatch mode

## D1 — Extend one resolver and one public operation

DG-04 extends the dg-00 `RoutingService.select_model()` pipeline, HTTP
`POST /routing/select_model`, and MCP `select_model_for_task`. It does not add
`POST /route/task`, a second score function, or a second routing decision store.
The existing `selected.vendor/model/endpoint_kind` meaning remains observable and
unchanged; assignment and provenance are additive fields.

## D2 — Preserve compatibility with an optional strict profile

Legacy `task_signals` remains accepted with its current permissive extra-field
behavior because existing phase callers send fields such as `write_allow`. A new
optional `routing_profile` is strict (`extra=forbid`) and types:

- expected duration seconds;
- scope category (`read-only|bounded-write|broad-write`);
- interactivity (`interactive|headless`);
- secret need category (`none|brokered|direct`), never a secret value;
- positive parallelism;
- repository shape (`single-package|monorepo|unknown`);
- roadmap-policy constraints (allowed/excluded lane/vendor sets and an allowed-location set);
- optional required location, isolation, and dispatch mode.

Pydantic validates the external boundary and FastAPI/MCP share the same request model.
New request objects are optional for legacy callers. New assignment/provenance response
objects are required and populated on every successful DG-04 coordinator decision;
existing consumers remain compatible because the fields are additive.

## D3 — Rules are ordered, typed, and versioned

`agent-coordinator/routing.yaml` carries `schema_version`, `policy_version`,
dispatch-mode defaults, ordered first-match constraint rules, and a local-fallback
dimension table. A dedicated loader validates unknown fields, duplicate IDs, enum values,
ranges, and phase dispatch defaults, then records a SHA-256 checksum of canonical file
bytes.

Each rule has a typed `when` predicate over the profile and a typed `constrain` block for
location, isolation, and dispatch mode. Explicit request and roadmap constraints are
hard filters that intersect matching rule constraints; a conflict yields no feasible
assignment. Otherwise the first matching rule that mentions a dimension constrains that
dimension.
The phase-specific or global dispatch default is used only when no explicit or rule-based
dispatch mode exists; unmatched location/isolation remain unconstrained. Rules narrow
feasibility and never add a second utility score. Changing a rule therefore changes the
feasible assignment set without code edits.

The Docker image copies the file beside `agents.yaml` and the loader resolves it from
`ROUTING_CONFIG` or the package root, never the process working directory.

## D4 — DG-01 is the only lane source and joins are exact

`RoutingService` injects/loads `VendorRegistryService` in process and requests all
lanes without `available_only` prefiltering so exclusion provenance is retained. For
each lane it consumes dg-01's projected catalog models. It forms an assignment only when
the catalog candidate identity exactly equals the projection key:

`(catalog_vendor, model, endpoint_kind, base_url)`.

`base_url` and additive lane identity travel through `CandidateInput` and
`ScoredCandidate`. Agent-name suffixes, provider/publisher guesses, substring matches,
and fuzzy model names are forbidden. Missing or ambiguous projections remain explicit
registry misses and never become routable candidates.

A watchdog `ConfiguredCatalogSync` job materializes configured non-OpenRouter lane
models in `model_catalog`. `agents.yaml` explicitly sets `catalog_vendor` and
`endpoint_kind` for those lanes: local subscription CLIs use their exact vendor type plus
`vendor-cli`; remote SDK lanes use their exact vendor type plus `vendor-sdk`. CLI model
IDs come from the canonical provider model map; SDK model IDs come only from the lane's
SDK model/fallback list. The job inserts only missing identity rows, with enabled catalog
availability and unknown price/posterior, and never overwrites existing pricing,
posterior, availability, or refresh data. Registry probe/rate-limit state remains the live
lane-availability source.

OpenRouter/local catalog rows remain owned by their existing refresh/probe jobs; for a
multi-publisher OpenRouter lane, exact model/endpoint/base-URL matching must yield one row
before the row's catalog vendor becomes part of the four-field key. Missing or ambiguous
identity metadata is an explicit configuration miss, never filled from an agent-name
suffix or publisher guess. A real-agents.yaml test proves at least one configured CLI
lane projects exactly after this bootstrap.

The routing path constructs a read-only `VendorRegistryService(audit=None)` because the
router persists its own typed exclusions and atomic audit link; this avoids emitting one
generic projection-miss audit row per request. The registry and catalog snapshots are
each loaded once per request. A registry read or shape failure fails closed as
`routing-registry-unavailable`; it never falls back to catalog-only scoring. Catalog rows
with no exact configured lane projection are retained in `excluded` as
`catalog:no-configured-lane`, rather than disappearing silently.

## D5 — Feasibility precedes DG-00 utility

For each exact lane/model pair, pure feasibility checks apply in deterministic order:

1. live lane availability and lane/model rate limits;
2. dispatchability, archetype, and requested/default dispatch mode;
3. explicit/configured location and isolation constraints;
4. roadmap-policy allow/exclude sets;
5. catalog availability and dg-00 modality/quota constraints.

Reasons are machine-readable and sanitized. DG-00's existing `unavailable` and
`quota:exhausted` values remain accepted alongside DG-04's namespaced reasons. Only feasible lane/model candidates enter
the existing `score_and_rank`; DG-04 does not duplicate quality, posterior, cost,
latency, headroom, or exploration math. Multiple lanes may project the same catalog
model, so the final stable order is `(-score, agent_id, catalog identity)`.
Location and isolation constraints use exact equality and dispatch mode uses exact
membership in the lane's configured modes; DG-04 does not infer an isolation-strength
ordering.

## D6 — Assignment and provenance are additive

A successful response adds top-level:

- `assignment`: exact `agent_id`, `vendor_type`, `policy_vendor`,
  `catalog_vendor`, location, isolation, dispatch mode, model, endpoint kind, and base
  URL;
- `provenance`: source (`coordinator` or `local-static`), policy version/checksum,
  matched rule IDs, rationale, persistence flag, durable-audit flag, and exact
  lane/catalog key.

The selected candidate and every alternative carry their own non-null additive
`assignment`, while every successful response retains a non-null identical copy of the
selected assignment plus non-null provenance at top level for convenience. Runtime
contract tests assert `response.assignment == response.selected.assignment`. `Candidate` does not duplicate flat `agent_id` or per-candidate
provenance fields; lane identity lives only in `Candidate.assignment`, and provenance
lives only at response top level. Existing dg-00 candidate fields remain intact for older
consumers. Excluded assignments use a typed shape containing lane/catalog identity and a
bounded machine-readable reason.

## D7 — Durable routing record is authoritative; audit event is linked

The existing `routing_decisions` row is the authoritative durable routing audit. Its
sanitized `request` stores only declared task signals and the strict routing profile;
permissive legacy extras such as `write_allow` are never persisted. The persisted
routing profile and nested roadmap policy are strict bounded projections with
`additionalProperties=false`, bounded string arrays, and no path-list field; an attempted
arbitrary or oversized path list fails the persistence-schema probe. Its `selected` object
stores selected assignment plus provenance, and every item in `alternatives` stores its
own assignment. `excluded` stores typed exclusion records. These are additive JSONB
shapes and require no new table columns.

Migration `042_atomic_routing_audit.sql` adds one transaction-scoped RPC that inserts the
`routing_decisions` row and a sanitized link-only `routing_decision` audit-log event
atomically. The event contains only decision ID, selected agent/model, routing-policy
version/checksum, source, and success. The service awaits the RPC result and returns only
after both rows commit. RPC failure rolls back both writes and produces HTTP 503 detail
`routing-durability-unavailable`; the MCP mirror returns its existing 503 error envelope.
Fire-and-forget `AuditService.log_operation()` is not used for this invariant, and neither
an orphan decision nor an orphan audit link is observable. Existing dg-00 callers still
take their exact static fallback on any non-200 response.

The `routing_decisions.policy_version` column keeps dg-00 scorer version
`linear-utility-v1`; the routing YAML version/checksum live in selected provenance. No raw
secret, environment value, prompt, free-form task-signal extra, or unbounded path list
enters either record; only typed/bounded categories and rationale enter persistence.

## D8 — Local fallback is configuration-derived and honest

A skills-side bridge/helper may fall back only after transport timeout/unreachability. It
loads the checkout's validated `routing.yaml`, `agents.yaml`, and archetype model map,
then combines the caller's already-resolved static provider/model with the fallback
dimension order. It never embeds a roster, fabricates availability, or performs fuzzy
association.

The response has the normal assignment shape plus `fallback=true`,
`source=local-static`, `persisted=false`, `durable_audit=false`, and a bounded
failure reason. Its catalog key is null because no live catalog join occurred. A local
UUID is explicitly not retrievable from coordinator decision storage. Missing or invalid
configuration fails loud; the helper does not invent permissive defaults.

The local helper evaluates the same ordered rules and dispatch defaults, recording the
matched rule IDs. It enumerates only lanes whose exact configured vendor type equals the
caller's already-resolved static provider and whose exact configured model set contains
the caller's static model. Explicit/rule constraints filter first. Remaining
lane/dispatch assignments sort by indexes in `fallback.location_order`,
`fallback.isolation_order`, and `fallback.dispatch_mode_order`, then by `agent_id`; a
mode not configured on a lane is never emitted. No matching lane or valid dispatch mode
raises a bounded `LocalRoutingFallbackError` and preserves the caller's existing static
result rather than fabricating an assignment.

The fallback table's order is only a deterministic choice among the lane's exact
configured values while the coordinator is unreachable. It is not an isolation-strength
precedence or enforcement policy. The reusable helper lives in
`skills/coordination-bridge/scripts/routing_fallback.py`, resolves repository config from
an explicit root or discovered checkout root, and is used only by client/bridge callers.
`http_proxy.py` remains a coordinator transport mirror and does not import skills-side
code.

The existing `resolve_archetype_for_phase` fallback is not rewritten: disabled,
failure, malformed-response, and timeout paths still return the exact dg-00 static
`ResolvedArchetype` object with no added reasons or fields.

## D9 — DG-05/DG-06 boundaries remain closed

DG-04 carries the lane's current configured isolation as data and may filter an explicit
request. It does not define per-mode overrides, the isolation precedence ladder, or
enforcement; DG-05 owns that contract. It does not call routing before `dispatch_fn`,
change `phase_agent.py`, redispatch work, or add loop caps; DG-06 owns obedience.
No sandbox is launched; DG-07 owns enforcement.

## D10 — Test-first packages and validation

Static OpenAPI/JSON-Schema/config tests fail first without importing unfinished runtime
models. Runtime HTTP/MCP parity tests live in the later policy/transport packages, after
the request/response models exist. Pure policy/association tests precede service and
transport/fallback tests. PostgreSQL coverage proves the additive JSONB decision
round trip and durable audit link. Full coordinator and affected skills suites, Ruff,
strict mypy, strict OpenSpec, work-package DAG/scope checks, configured vendor-panel
plan/implementation convergence, stacked PR CI, and exact static-fallback regression
must all pass before roadmap reconciliation.

Framework-specific implementation follows the installed FastAPI/Pydantic versions and
their official model/response documentation:
https://docs.pydantic.dev/latest/concepts/models/ and
https://fastapi.tiangolo.com/tutorial/response-model/.

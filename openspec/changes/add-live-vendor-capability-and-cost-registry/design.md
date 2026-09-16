# Design: add-live-vendor-capability-and-cost-registry

## D1 — Compose existing owners and make them deployable

Static lane data comes from `get_agents_config()`; CLI/key readiness comes from the existing
`vendor_health.py` probe; local endpoint health and pricing stay in the dg-00 catalog. The
registry aggregates those sources but does not score models or choose dg-04 dimensions. The
coordinator image copies the health probe, resolves it through `SKILLS_ROOT`, sets
`AGENTS_YAML=/app/agents.yaml`, and starts watchdog independently of optional notification
channels. A deployment test must persist at least one snapshot, not merely find the file.

## D2 — Keep four identities and location typed

- `agent_id`: dispatch lane, exactly `AgentEntry.name`.
- `vendor_type`: provider grouping, exactly `AgentEntry.type`.
- `policy_vendor`: existing roadmap-policy compatibility name, explicitly configured.
- `catalog_vendor`: optional dg-00 catalog constraint, explicitly configured.
- `location`: explicit `local|cloud|unknown`; never inferred from an ID suffix or publisher.

Bundled `agents.yaml` declares these values. Missing location is `unknown` only for external
backward compatibility and fails location constraints closed. Catalog model membership is the
deterministic union of authored CLI/SDK models and the existing provider model map; exact model ID
is the primary join, endpoint kind/base URL constrain it when configured, and catalog vendor
constrains it only when configured. Base URL is an additional exact constraint for local endpoints and is surfaced in model
projections. This supports multi-publisher lanes such as pi without fuzzy publisher matching.

## D3 — Persist availability, never pricing

`vendor_probe_state` stores the latest lane probe. `vendor_rate_limits` stores bounded
observations and canonical request hashes. Neither contains prices. Reads batch one probe query,
one active-limit query, and one dg-00 catalog read, then join in memory. Returned model projections
include catalog/model/endpoint identity, price, `available`, freshness, and staleness. Catalog
misses are explicit and audited.

## D4 — Deterministic effective state and model scope

Precedence is:

1. active lane-scoped limit → lane `limited`;
2. for `endpoint_kind=local` only, no non-stale available matching catalog model →
   `unavailable` or `unknown` from the catalog evidence;
3. current failed readiness probe → `unavailable`;
4. current successful readiness probe → `available`;
5. missing/stale/no-probe-method evidence → `unknown`.

A model-scoped limit does not mark the whole lane limited. It removes only that model from
model-aware eligibility; the lane remains available when another eligible model remains.
Watchdog persists every configured lane, including non-CLI lanes as
`unknown(reason=no_probe_method)`, with
`stale_after = observed_at + 2 × VENDOR_HEALTH_INTERVAL_SECONDS`. The first poll writes without
transition events. Per-lane write failures never suppress other writes or legacy transitions.
`now >= stale_after/reset_at` is expired.

## D5 — Rate limits always expire and replay atomically

POST accepts at most one future `reset_at` or bounded `retry_after_seconds`; neither means
`VENDOR_UNKNOWN_LIMIT_TTL_SECONDS` (default 900). Retry-after anchors to server receipt time and
all resets are bounded by `VENDOR_MAX_LIMIT_TTL_SECONDS` (default 604800). Storage always has an
absolute non-null reset.

SQL RPCs perform atomic probe upsert, rate-limit insert/replay/conflict, and compaction. Replay
hashes canonical client semantics (target/source lane, observation ID, scope/model/reason/metadata,
and original absolute reset, retry-after, or default-TTL marker), never server receipt time or a
derived relative reset. Identical replay returns `duplicate`; different content returns 409.
Expired rows leave reads immediately and a watchdog compaction job deletes them after seven days.

## D6 — Authorization matches dispatcher topology

Routes accept Bearer, `X-Coordinator-API-Key`, and `X-API-Key`. Source principal and receipt
time are server-derived. The explicit `vendor_limit_reporter` capability maps to `report_vendor_rate_limit` through
`CAPABILITY_OPERATIONS`; dispatcher/orchestrator entries receive that capability in bundled config
and profile sync tests pin it. `authorize_operation` permits those principals to report
the concrete lane they dispatched even when it differs from the orchestrator lane. Keys without
that operation are denied; trust-level 3 remains an administrative override. Thus cloud trust-2
orchestrators can report dispatched lanes without making every valid key a cross-lane writer.

Bridge helpers retain existing `status/operation/response-or-error` conventions. Problem detail
codes distinguish `unknown_vendor_lane` from `vendor_registry_unavailable`, so bridge 404
handling does not conflate a bad lane with an older coordinator.

## D7 — Exact dispatcher attribution through additive fields

`review_dispatcher.py` retains selected `agent_id` on `ReviewerInfo`; `ReviewResult` gains
additive lane/reset fields and its shared collector reports terminal capacity exactly once. Adapter
model-attempt callbacks report intermediate model-scoped limits even when a fallback later succeeds. `provider_dispatch.py` gains optional `agent_id`, capacity error class,
and reset metadata on structured payload/results; it never infers a lane from provider. Standard
HTTP/SDK `Retry-After` may be forwarded; current CLI paths normally omit reset metadata and
therefore use the server default TTL. Reporting failures never mask dispatch results.

Legacy `vendor_limit:<policy_vendor>:<reason>` has no lane. It is not persisted without
`dispatch_agent_id`. For that in-run policy decision only, all lanes with that
`policy_vendor` are excluded because the legacy signal is provider-scoped; the skip and
exclusion are recorded in structured policy-decision provenance and logs.

## D8 — Lane-aware policy and request-scoped quotes

A registry snapshot carries lane/provider/policy identity, location, eligibility fields,
availability, and model prices. Candidates satisfy phase archetype, dispatch mode, optional
capability/location, model limits, and effective state. Policy selects a concrete lane and retains compatibility `to_vendor` plus `to_agent_id`.
`dispatchable` means a configured executable transport/adapter exists, independent of live
availability; automatic candidates require both dispatchable and eligible availability. The selected
lane writer in `phase_agent.py` carries `dispatch_agent_id` into structured dispatch payloads and
subsequent retry context; initial legacy prompt-only outcomes remain provider-scoped.

When structured dispatch context provides exact catalog model and prompt/completion token
estimates, the quote is:

`quote_usd = prompt_tokens × prompt_usd_per_mtok / 1_000_000 + completion_tokens × completion_usd_per_mtok / 1_000_000`

Use decimal arithmetic and six-place rounding. Missing/stale/ambiguous data yields unknown cost.
Static tiers may order degraded candidates but never populate USD deltas or enforce USD ceilings.
When a configured cost ceiling cannot be evaluated, switching proceeds under the existing
availability policy with explicit `cost_guard=unavailable` provenance and a warning. This is the
migration from former heuristic “USD” enforcement until structured dispatch supplies estimates.

## D9 — Coordinator-unavailable behavior is configuration-derived

Automatic switching fails closed on registry transport/auth/payload failure by default. An
explicit fallback may read only an explicitly supplied checkout `agents.yaml`, project typed
fields with unknown availability/cost, and apply identical filters. Policy may use unknown lanes
only when that fallback is injected. No fallback embeds a roster, cached health, or synthetic
price. Timeout, auth, route-unavailable, unknown-lane, server, and malformed failures remain
distinct.

## D10 — Observability, retention, and audit scope

Accepted/duplicate/rejected observations, catalog misses, stale/expired state, persistence
failures, compaction, ambiguous legacy skips, and fallback activation emit structured logs and
audit/decision provenance without secret-bearing metadata. Durable coordinator audit is required
for coordinator-side events; skills-only ambiguous skips use the existing policy decision record
and structured log. The watchdog owns scheduled compaction.

## D11 — Execution packages

Contracts land first, then registry/config/RPC core, then API/watchdog. Dispatcher/bridge lands
next. Roadmap policy depends on those bridge helpers rather than duplicating HTTP/error logic.
Integration reruns contract, non-skipping migration/RPC probes, focused/full non-e2e tests, Ruff,
coordinator-local mypy, DAG/scope, and strict OpenSpec before review or roadmap reconciliation.

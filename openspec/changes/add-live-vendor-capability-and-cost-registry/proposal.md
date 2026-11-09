# Add live vendor capability and availability registry

> Parent roadmap: `dispatch-governance`
> Roadmap item: `dg-01`
> Change ID: `add-live-vendor-capability-and-cost-registry`
> Effort: M
> Priority: 1

## Summary

Add a coordinator-owned registry that aggregates configured dispatch-lane capabilities from
`agents.yaml`, probed health, and observed rate-limit windows. Expose `GET /vendors` and
`GET /vendors/{id}/availability`, add authenticated rate-limit ingestion, and teach the
coordination bridge and roadmap orchestrator to consume it. Costs remain projections from the
model-routing catalog landed by dg-00; this change introduces no second cost table.

## Dependencies

- `dispatch-governance:dg-00` / `add-adaptive-model-router`, finalized at
  `d125ebadcc64799962aae65142d418ff72705a8b`.

## Acceptance Outcomes

- `GET /vendors` returns capabilities, live availability, rate-limit reset times, and
  catalog-derived cost projections for every configured dispatch lane, including explicit typed location.
- Watchdog health changes and dispatcher-observed limits update registry state; expired limits
  stop excluding lanes without operator repair.
- The coordination bridge exposes normalized registry reads and fail-closed observation writes.
- Roadmap policy receives registry-derived, capability-filtered alternates grouped by vendor
  type; `orchestrator.py` contains no hardcoded vendor roster.
- No cost data is persisted outside the dg-00 model catalog.

## Scope

In scope: `AgentEntry` aggregation; durable probe snapshots and lane-scoped rate-limit windows;
catalog-backed cost projections with provenance; HTTP, bridge, watchdog, dispatcher-result, and
roadmap-policy wiring.

Out of scope: a new pricing store; replacing the dg-00 resolver/catalog/local probe; new quota
providers; and dg-04's vendor × location × isolation × dispatch-mode resolver.

## Rationale

Static dispatch configuration, watchdog health observations, and dg-00 catalog pricing already
exist, but no aggregate read model connects them. This narrow registry composes those sources,
persists only volatile availability state, and gives dg-04 a stable capability boundary without
duplicating routing or pricing ownership.

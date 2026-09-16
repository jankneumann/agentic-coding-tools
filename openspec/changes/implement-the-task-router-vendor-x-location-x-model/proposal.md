# Extend routing to vendor × location × isolation × dispatch mode

> Parent roadmap: `dispatch-governance`
> Roadmap item: `dg-04`
> Change ID: `implement-the-task-router-vendor-x-location-x-model`
> Stacked on: `add-live-vendor-capability-and-cost-registry` (`dg-01`)

## Summary

Extend the existing adaptive model router at `POST /routing/select_model` and its
`select_model_for_task` MCP mirror. The request gains a typed task-routing profile and
the selected candidate gains an exact configured lane assignment: `agent_id`, vendor
type, location, isolation, and dispatch mode. The dg-01 `VendorRegistryService` supplies
live lane feasibility and exact catalog-model projections before the dg-00 utility
scorer ranks candidates.

Routing rules are deterministic, validated, and versioned in
`agent-coordinator/routing.yaml`. Coordinator decisions retain additive assignment and
policy provenance in both `routing_decisions` and the durable audit log. A local
configuration-derived fallback returns the same assignment shape with explicit
`fallback=true` provenance when the coordinator is unreachable.

This change does **not** create `POST /route/task`, score a second time, alter dispatch
execution, pin isolation precedence, or enforce a sandbox. Those boundaries remain with
dg-05, dg-06, and dg-07.

## Dependencies

- `dispatch-governance:dg-00` — model catalog, utility scorer, `/routing/*`, MCP mirror,
  routing decision store, and exact static fallback equality.
- `dispatch-governance:dg-01` — configured lane identity, typed location, live
  availability/rate limits, and exact lane-to-catalog projections.

## Acceptance Outcomes

- `POST /routing/select_model` and `select_model_for_task` return location, isolation,
  dispatch mode, and exact lane identity alongside the selected vendor/model.
- Lane, task, and roadmap-policy feasibility is resolved before the existing dg-00
  utility scorer runs; no second resolver or model call is introduced.
- Every lane/model association comes from dg-01's exact catalog projection. Name
  suffixes, publisher guesses, and fuzzy model matching are forbidden.
- Changing validated `routing.yaml` rules changes deterministic decisions without code
  edits, and the policy version/checksum is recorded.
- Coordinator-side decisions are durably recorded in both routing decision storage and
  coordinator audit. Local fallback decisions declare that durable audit was unavailable.
- The dg-00 fallback contract remains byte-for-byte equal for existing
  `resolve_archetype_for_phase` callers when adaptive routing is disabled, fails, or
  times out.

## Non-goals

- No `/route/task` endpoint or parallel scoring implementation.
- No per-dispatch-mode isolation override or precedence ladder (dg-05).
- No orchestrator call-site wiring, redispatch, or loop-control changes (dg-06).
- No operating-system isolation enforcement (dg-07).
- No duplicate price table, roster, health cache, or inferred vendor identity.

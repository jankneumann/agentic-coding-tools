# Design: add-infeasible-incumbent-fallback

## Context

- **Where exclusion reasons are lost.** `RoutingService.select_model` (`api.py`) collapses
  every exclusion to a bare `(vendor, model)` before `apply_incumbent_retention` sees it. The
  reason (`lane:unavailable`, `roadmap:vendor-excluded`, …) survives only in the response's
  `excluded` payload.
- **Unevidenced candidates are already scored.** Feasible unevidenced candidates are in
  `ranked` with full `RoutingAssignment`s. The retention core drops them via the `c.evidenced`
  filter.
- **The order config exists but is client-only.** `routing.yaml` already has a `fallback:`
  block (`location_order`, `isolation_order`, `dispatch_mode_order`), parsed into
  `RoutingPolicyDocument.fallback`. Only
  `skills/coordination-bridge/scripts/routing_fallback.py` uses it, when the coordinator is
  unreachable.
- **The client trusts the router's vendor, but dispatch doesn't.**
  - `phase_agent.build_phase_dispatch_kwargs` sets the payload provider to
    `_resolved_provider or selected_provider`.
  - `run_phase_subagent` (via `make_phase_callback`) ignores `_resolved_provider`.
  - `smoke_provider_dispatch` uses its own fixed provider.
  - The autopilot SKILL.md adapter contract mentions only `prompt`/`model`.
- **Provider-less resolution sends a tier alias.** `_selected_provider()` returns `None` with
  no arg and no `AUTOPILOT_PROVIDER`/`AGENT_TYPE`, so resolution runs provider-less and the
  incumbent is `{vendor: null, model: "<tier alias>"}`.

## Goals / Non-Goals

**Goals**
- No dispatch ever pairs a routed model with a different vendor's runner.
- Provider-less dispatch routes like provider-ful dispatch.
- A transiently unavailable incumbent falls back to a configured, deterministic choice.

**Non-goals**
- Falling back on permanent mismatches.
- Using evidence to pick the fallback; evidenced alternatives already win via
  `incumbent-infeasible-evidenced-alternative`, which is unchanged.
- #636 item 4 (attribution), which is decided and lives in #612.
- Changing `routing_fallback.py`'s behavior when the coordinator is unreachable, beyond
  honoring the new `vendor_order` key.

## Decisions

### D1: Phase 1 (dispatch) lands before phase 2 (fallback)

The phase 1 changes are prerequisites and independently correct:
- every dispatch path honors `_resolved_provider`;
- the SKILL.md adapter contract names `provider`;
- the default provider is resolved before archetype resolution.

They touch only `skills/`, so they can merge ahead of the contract chain. Phase 2 must not
merge before phase 1, because a cross-vendor fallback over unfixed dispatch produces
mismatched model/vendor pairs.

### D2: The default provider is resolved before resolution, and it is the same default

`_selected_provider()` falls back to `claude_code`, the value `build_phase_dispatch_payload`
already applies *after* resolution. Behavior for provider-less callers changes in exactly one
way: the incumbent becomes concrete, so routing can act. The dispatched vendor is the one it
already was.

### D3: The fallback fires only on transient availability exclusions

Trigger set: `lane:unavailable`, `unavailable`, `quota:exhausted`, `lane:model-rate-limited`.

Permanent mismatches keep `incumbent-infeasible-no-evidenced-alternative` with a null
selection, because they encode operator policy that a fallback must not bypass:
- `lane:archetype-ineligible`, `lane:dispatch-mode-ineligible`, `lane:not-dispatchable`;
- `lane:location-mismatch`, `lane:isolation-mismatch`;
- `roadmap:*`, `cedar:*`, `cost-policy:unclassified`;
- `catalog:no-configured-lane`, `registry:no-catalog-projection`.

`cost-policy:lower-priority-tier` keeps its existing path (`api.py` sends it to plain
`choose()`).

Exclusion reasons are carried into retention as `(vendor, model) → reason`. When an incumbent
has several excluded rows, it counts as transiently unavailable only if **every** row's reason
is transient. A mixed set is treated as permanent, which errs toward not bypassing policy.

### D4: The order is lexicographic over the configured keys, with agent_id as the final tie-break

Sort key, ascending:
`(vendor_order.index(vendor_type), location_order.index(location),
isolation_order.index(isolation), dispatch_mode_order.index(dispatch_mode), agent_id)`.

A value missing from a list sorts after every listed value. Only **feasible** candidates are
considered, the incumbent's own rows are excluded, and score and RNG are never consulted.
That makes the pick reproducible (NFR determinism) and identical to the client-side sort,
which gains the same `vendor_order` key.

### D5: No `vendor_order` means no fallback

The trigger requires `fallback.vendor_order` to be present and non-empty. With it absent,
behavior is exactly today's, so the change is opt-in by config. The shipped `routing.yaml`
gets an order for the owner to review in the PR. It starts empty, and the owner populates it
at implementation review.

### D6: A new retention reason, `retained: false`, in a v1.4 overlay

`incumbent-infeasible-configured-fallback` is a routed selection, not a kept one, so the
client follows it to the new provider through the dispatch path D1 fixes. The persisted
decision adds `retention.fallback = {incumbent_exclusion_reason, order_applied}`. The v1.4
overlay builds on `split-no-evidence-retention-reason`'s v1.3; the archived v1.2 and v1.3 stay
untouched (D7 of `retain-static-model-until-routing-evidence`). There is no migration:
`retention` is JSONB with no CHECK on its contents.

## Risks / Trade-offs

- **Contract chain dependency.** v1.4 needs v1.3 first, and v1.3 waits on the task-router
  change. Phase 1 is independent of that chain, so the most important correctness fix doesn't
  wait.
- **A configured order can name a vendor whose model is weaker.** That is the explicit
  trade-off the owner chose: an available, human-chosen model over a known-failing one. The
  reason and order are persisted, so this is auditable.
- **#647's displaced-incumbent rule does not apply here.** Exploration is not involved: the
  fallback pick is deterministic and the incumbent is infeasible anyway.

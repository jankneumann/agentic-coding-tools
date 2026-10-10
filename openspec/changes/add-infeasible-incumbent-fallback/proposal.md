# Change: add-infeasible-incumbent-fallback

## Why

With `ROUTING_ADAPTIVE` on, each phase offers its static model as the incumbent. If the
incumbent's lane is **infeasible** (its vendor is down, out of quota, or rate-limited) and no
feasible alternative has evidence, `apply_incumbent_retention` returns
`incumbent-infeasible-no-evidenced-alternative` with `retained: true`. The client then
dispatches to the model the router has just been told is unavailable. Since #653, lane probes
are real, so this case happens in production rather than only in theory.

The owner decided (#636 item 7, option B) to fall back in this case to a **configured,
deterministic, human-chosen alternative**, not to the router's ranking. Without evidence, the
ranking is the arbitrary sort order that #624 exists to avoid.

Two prerequisites surfaced during discovery, and this change also takes both on.

**Dispatch does not reliably honor a vendor chosen by the router.**
- `phase_agent.build_phase_dispatch_kwargs` puts the coordinator's provider into the payload.
- But `run_phase_subagent` never reads it.
- `smoke_provider_dispatch` pairs the routed model with its own fixed provider.
- The autopilot SKILL.md tells harnesses to call the adapter with `prompt`/`model` only.

A cross-vendor fallback on top of that could send, for example, a Codex model to the Claude
runner. That mismatched pair is worse than today's failure.

**Provider-less dispatch can never route** (#636 item 6). With no `--provider`,
`AUTOPILOT_PROVIDER` or `AGENT_TYPE`, `_selected_provider()` returns `None`. The static model
then stays a tier alias (`standard`), which is sent as the incumbent
`{vendor: null, model: "standard"}` and always ends `incumbent-unresolved`. The
`"claude_code"` default exists, but it is applied only *after* resolution
(`phase_agent.py:1108`).

## What Changes

**Phase 1: dispatch honors the resolved provider**
- Every autopilot dispatch path sends the work to the provider resolution returned, and never
  pairs a routed model with a different vendor's runner:
  - `build_phase_dispatch_kwargs` (already correct; gains a regression test);
  - `run_phase_subagent`, which passes the routed provider to its runner as
    `options["provider"]`; a runner that cannot serve that provider raises instead of
    substituting its own (design D1);
  - `smoke_provider_dispatch`, which pairs the resolved provider with the resolved model and
    re-runs its Claude-alias and `local` trust-boundary checks against it.
- The autopilot SKILL.md adapter contract names `provider` alongside `prompt`/`model` in every
  per-phase dispatch block, with the rule that a non-`claude_code` provider goes through the
  provider adapter or escalates, never through `Agent(...)`.
- Provider-less dispatch resolves its default provider (`claude_code`, the same default applied
  today after resolution) **before** archetype resolution. The incumbent is then a concrete
  `(vendor, model)`, not a tier alias (#636 item 6), so every routing outcome that needs a
  concrete incumbent becomes reachable (design D2).

**Phase 2: configured fallback for a transiently unavailable incumbent**
- `routing.yaml`'s existing `fallback:` block gains an optional `vendor_order`: an
  **allowlist** of agent types, most preferred first. Only listed vendors are fallback targets.
  The coordinator now applies the block in retention; until now only the
  coordinator-unreachable client path used it (that path stays same-provider and only
  validates the new key).
- When every excluded row of the incumbent carries a **transient availability** reason
  (`lane:unavailable`, `unavailable`, `quota:exhausted`, `lane:model-rate-limited`), the
  incumbent is not excluded by cost policy, no feasible alternative is evidenced, and lane
  assignments are enabled:
  - the router picks an eligible feasible candidate **deterministically by the configured
    order**: `vendor_order`, then `location_order` / `isolation_order` /
    `dispatch_mode_order`, then `agent_id`; a candidate must be enumerated in every list to be
    eligible;
  - it records the new reason `incumbent-infeasible-configured-fallback` with
    `retained: false` and a `retention.fallback` record (the incumbent's exclusion reasons
    and the order applied);
  - the client then dispatches to the fallback's provider, an explicit provider change as
    `agent-archetypes` *Fallback Chain Integration* requires.
- Permanent mismatches keep today's behavior: the static configuration and the lane policy
  contradict each other, and the router surfaces that rather than guessing. The authoritative
  list is design D3 (for example `lane:archetype-ineligible`, `lane:location-mismatch`,
  `roadmap:*`, `registry:no-catalog-projection`).
- A routed selection onto the `local` provider is subject to the same `LOCAL_TRUSTED_ARCHETYPES`
  boundary the static path applies (design D7); today only the caller's provider is checked.
- Exclusion reasons are now carried through to retention. Today `api.py` collapses them to bare
  `(vendor, model)`.
- A **v1.4 contract overlay**, built on `split-no-evidence-retention-reason`'s v1.3, adds the
  reason and the `retention.fallback` record.

Nothing here is **BREAKING**:
- `ROUTING_ADAPTIVE` still defaults off.
- With no `vendor_order` configured, phase 2 changes nothing. The fallback is opt-in by config:
  the shipped `routing.yaml` keeps the key absent with a commented example, and the owner
  populates it at implementation review (design D5).
- Phase 1 only corrects pairs that were already wrong.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Correctness | Dispatches whose runner vendor ≠ the routed provider, across all autopilot dispatch paths | 0 | Dispatch-pairing tests, task 1.3 (Implementation) |
| Determinism | Fallback pick for identical catalog + config + availability | Identical on every run; no RNG involved; `allow_exploration` has no effect | Repeated-call unit test, task 3.3 (Implementation) |
| Safety | Fallback chosen when the incumbent's exclusion is a permanent mismatch, or onto a vendor absent from `vendor_order`, or onto `local` for an untrusted archetype | 0 | Parametrized test over every exclusion reason (3.3) + allowlist test (3.3) + trust-boundary test (3.8) (Implementation) |
| Compatibility | Selection outcomes with `vendor_order` absent, or with assignments disabled | 0 differences from today | Retention matrix (3.3) + `test_empty_evidence_end_to_end` (4.1) (CI) |
| Observability | Fallback decisions carrying their reasons and the config order used | 100% persisted (`retention.reason` + `retention.fallback.{incumbent_exclusion_reasons, order_applied}`), validated against the v1.4 record schema | Service-level persistence test, task 3.5 (Implementation) |

## Approaches Considered

### Approach 1: Server-side configured fallback in the router (Recommended)

The router keeps the exclusion reasons, recognizes a transiently unavailable incumbent, and
chooses among feasible unevidenced candidates using `routing.yaml`'s `fallback:` order. It
returns that candidate with reason `incumbent-infeasible-configured-fallback`.

- **Pros**
  - One decision point: the persisted decision records what was chosen and why.
  - It reuses the `fallback:` semantics the offline client path already uses, so online and
    offline fallback agree.
  - Every client benefits: HTTP, MCP and autopilot.
- **Cons**
  - Router and contract change: a new reason, a v1.4 overlay, and reasons threaded through
    `api.py`.
  - The server now reads a config block that was client-only.
- **Effort:** M

### Approach 2: Client-side fallback after a kept-infeasible decision

The router is unchanged apart from returning its exclusion reasons. When the client sees
`incumbent-infeasible-no-evidenced-alternative` for a transient reason, it re-resolves locally,
reusing `routing_fallback.py`'s ordered lane sort.

- **Pros**
  - No retention-enum change; it reuses an existing client sort.
- **Cons**
  - The persisted decision says "kept static" while the client actually dispatched elsewhere,
    which is the same attribution gap #636 item 4 had to decide around.
  - The logic is duplicated per client, and non-autopilot clients don't get it.
- **Effort:** M

### Approach 3: Same-vendor fallback only

When the incumbent's lane is down, try the same agent type's other lanes or `model_fallbacks`.
No cross-vendor move.

- **Pros**
  - No dispatch changes are needed, because the vendor never changes.
  - It is consistent with *Fallback Chain Integration* as written.
- **Cons**
  - No help when a **whole vendor** is unavailable, which is the case #653's probes now reveal.
  - It falls short of the owner's option-B decision.
- **Effort:** S

### Recommended

**Approach 1.** It keeps the decision and its reason in the one persisted record, so
attribution (#636 item 4) stays correct without client bookkeeping. It also makes online and
offline fallback use the same configured order. Approach 2 would reopen the attribution gap.
Approach 3 doesn't cover a vendor outage.

### Selected Approach

**Approach 1: server-side configured fallback.** Selected at Gate 1 (2026-10-05) with no
modifications. Discovery answers folded into the plan:

- **Dispatch:** dispatch-honors-provider is phase 1 of this change.
- **Trigger:** the fallback fires on transient availability exclusions only.
- **Config:** the order lives in `routing.yaml`'s existing `fallback:` block.
- **Sequencing:** the contract is a v1.4 overlay, landing after
  `split-no-evidence-retention-reason`.

Approaches 2 and 3 were not taken, for the reasons under Recommended.

## Impact

- **Specs**
  - `model-routing`: MODIFIED *Incumbent Retention Until Routing Evidence*. The infeasible
    scenarios split into transient vs permanent, and the configured-fallback scenario is added.
  - `agent-archetypes`: MODIFIED *Archetype Resolution Delegates to Adaptive Router*. It covers
    the default provider resolved before resolution, dispatch honoring the routed provider, a
    runner that cannot serve the routed provider, and the `local` trust boundary on routed
    selections.
- **Coordinator**
  - `src/model_routing/resolver.py`: `apply_incumbent_retention` with the reasons map, the
    configured-order pick, and `RetentionDecision.fallback`.
  - `src/model_routing/api.py`: exclusion reasons threaded into retention, `retention.fallback`
    persisted, plus the new `RetentionReason`.
  - `src/model_routing/routing_policy.py`: `FallbackOrder.vendor_order`.
  - `src/agents_config.py`: the `local` trust boundary applied to routed selections (D7).
  - `routing.yaml` (commented example; key absent).
  - `CLAUDE.md`: the retention reason list.
- **Skills**
  - `skills/autopilot/scripts/phase_agent.py`: `_selected_provider` default, plus
    `run_phase_subagent` passing `options["provider"]`.
  - `skills/autopilot/scripts/smoke_provider_dispatch.py`.
  - `skills/autopilot/SKILL.md`: the adapter contract, every per-phase block.
  - `skills/coordination-bridge/scripts/routing_fallback.py`: parses and validates
    `vendor_order` (no behavior change).
- **Contracts**
  - `contracts/openapi/v1.4.yaml`;
  - `contracts/events/routing-decision-record.schema.json`;
  - `contracts/generated/models.py`.
- **Architecture layers:** Coordination (router) and Execution (dispatch).
- **Sequencing**
  - **Operator hold (2026-10-10, design D8):** only `wp-dispatch` runs in the current autopilot
    run. `wp-router` starts after `split-no-evidence-retention-reason` (v1.3) merges to `main`
    and after `wp-dispatch` merges; `work-packages.yaml` records the hold and task 2.0 enforces
    it.
  - v1.3 itself waits for `implement-the-task-router-vendor-x-location-x-model` to close out.
  - Phase 1 touches only skills, so it can be implemented and merged independently, ahead of
    that chain.

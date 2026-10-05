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
  - `build_phase_dispatch_kwargs`;
  - `run_phase_subagent`;
  - `smoke_provider_dispatch`.
- The autopilot SKILL.md adapter contract names `provider` alongside `prompt`/`model`.
- Provider-less dispatch resolves its default provider (`claude_code`, the same default applied
  today after resolution) **before** archetype resolution. The incumbent is then a concrete
  `(vendor, model)`, not a tier alias (#636 item 6).

**Phase 2: configured fallback for a transiently unavailable incumbent**
- `routing.yaml`'s existing `fallback:` block gains a `vendor_order` (agent types, most
  preferred first). The coordinator now reads the block; until now only the
  coordinator-unreachable client path used it.
- When the incumbent is excluded **for transient availability only** (`lane:unavailable`,
  `unavailable`, `quota:exhausted`, `lane:model-rate-limited`) and no feasible alternative is
  evidenced:
  - the router picks a feasible candidate **deterministically by the configured order**:
    `vendor_order`, then `location_order` / `isolation_order` / `dispatch_mode_order`, then
    `agent_id`;
  - it records the new reason `incumbent-infeasible-configured-fallback` with
    `retained: false`;
  - the client then dispatches to the fallback's provider, an explicit provider change as
    `agent-archetypes` *Fallback Chain Integration* requires.
- Permanent mismatches keep today's behavior, because a fallback must not route around policy
  the operator set on purpose. These include `lane:archetype-ineligible`, `roadmap:*`,
  `location-mismatch` and `registry:no-catalog-projection`.
- Exclusion reasons are now carried through to retention. Today `api.py` collapses them to bare
  `(vendor, model)`.
- A **v1.4 contract overlay**, built on `split-no-evidence-retention-reason`'s v1.3, adds the
  reason.

Nothing here is **BREAKING**:
- `ROUTING_ADAPTIVE` still defaults off.
- With no `vendor_order` configured, phase 2 changes nothing. The fallback is opt-in by config,
  and the default `routing.yaml` ships with an order the owner reviews.
- Phase 1 only corrects pairs that were already wrong.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Correctness | Dispatches whose runner vendor ≠ the routed provider, across all autopilot dispatch paths | 0 | New dispatch-pairing tests (Implementation) |
| Determinism | Fallback pick for identical catalog + config + availability | Identical on every run; no RNG involved | Repeated-call unit test (Implementation) |
| Safety | Fallback chosen when the incumbent's exclusion is a permanent mismatch | 0 | Parametrized test over every exclusion reason (Implementation) |
| Compatibility | Selection outcomes with `vendor_order` absent | 0 differences from today | Retention matrix + `test_empty_evidence_end_to_end` (CI) |
| Observability | Fallback decisions carrying their reason and the config order used | 100% persisted (`retention.reason` + `fallback_order`) | Integration test on the migrated DB (Validation) |

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
    the default provider resolved before resolution, and dispatch honoring the routed provider.
- **Coordinator**
  - `src/model_routing/resolver.py`: `apply_incumbent_retention` plus the configured-order pick.
  - `src/model_routing/api.py`: exclusion reasons threaded into retention, plus the new
    `RetentionReason`.
  - `src/model_routing/routing_policy.py`: `FallbackOrder.vendor_order`.
  - `routing.yaml`.
- **Skills**
  - `skills/autopilot/scripts/phase_agent.py`: `_selected_provider` default, plus
    `run_phase_subagent` honoring `_resolved_provider`.
  - `skills/autopilot/scripts/smoke_provider_dispatch.py`.
  - `skills/autopilot/SKILL.md`: the adapter contract.
  - `skills/coordination-bridge/scripts/routing_fallback.py`: shared `vendor_order` semantics.
- **Contracts**
  - `contracts/openapi/v1.4.yaml`;
  - `contracts/events/routing-decision-record.schema.json`;
  - `contracts/generated/models.py`.
- **Architecture layers:** Coordination (router) and Execution (dispatch).
- **Sequencing**
  - Lands after `split-no-evidence-retention-reason` (v1.3), which itself waits for
    `implement-the-task-router-vendor-x-location-x-model`.
  - Phase 1 touches only skills, so it can be implemented and merged independently, ahead of
    that chain.

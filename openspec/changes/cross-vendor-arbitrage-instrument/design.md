# Design: Cross-Vendor Cost-Arbitrage Learning Instrument

**Change ID**: cross-vendor-arbitrage-instrument
**Approach**: A — Dedicated bounded instrument capability

## Context

We are building a kill-switchable instrument that (a) records five families of signals about cross-vendor agent routing, (b) maintains a metered-counterfactual cost ledger, (c) runs two scheduled probes that make invisible state (ToS terms, silent model swaps) observable, (d) drives a deliberately simple static-priority router behind a hard/soft constraint split, (e) flips system posture on tripwires, and (f) emits a weekly landscape digest. The governing principle is that the **instrument is durable and the arbitrage logic is transient** — the design must keep the whole thing removable as one unit.

The exploration confirmed every storage/telemetry/policy/scheduling primitive already exists; this change adds an interpretive layer, not new infrastructure.

## Module Layout (the bounded context)

```
agent-coordinator/src/arbitrage_signal.py     # signal recording (audit_log + OTel emission)
agent-coordinator/src/probes/tos_monitor.py   # ToS clause diff probe
agent-coordinator/src/probes/model_canary.py  # model-drift fingerprint probe
agent-coordinator/cedar/                       # vendor/modality eligibility (forbid policies + schema attrs)
skills/vendor-arbitrage/                        # router, ledger, tripwires, digest (the skill)
  scripts/router.py        # static-priority selection over the Cedar-feasible set
  scripts/ledger.py        # metered-counterfactual cost ledger (extends roadmap-runtime)
  scripts/tripwires.py     # threshold evaluation + posture flips
  scripts/digest.py        # weekly landscape report generator
  scripts/eligibility.py   # mutable per-vendor pricing + eligibility config loader
```

## Key Decisions

### D1: Bounded capability, not diffused logic
The instrument is one capability with one feature flag. A coordinator-side signal/probe module + a skill-side router/ledger/digest, joined by the `contracts/` JSON schemas. Disabling the flag leaves coordinator and skills behaviourally unchanged. *(Rejected: extending each existing module in place — no kill switch.)*

### D2: Signals ride `audit_log` + OTel — no new tables
Signal *events* are recorded as `audit_log` operations (`operation="arbitrage.signal.<family>"`) and as OTel measurements on a new `coordinator.signal` meter with `vendor`/`model`/`modality`/`archetype` labels. Rationale: append-only immutability (DB trigger), non-blocking async write, and graceful-degrade-when-disabled are already solved in `audit.py`/`telemetry.py`.

### D3: Interpretive records extend roadmap-runtime — single source of truth
Decision provenance and the cost ledger extend `LearningEntry.vendor_notes` (already defines `cost_observed_usd`, `latency_observed_seconds`) and `checkpoint.vendor_state` (already defines `switch_history`, `blocked_vendors`). No parallel cost store. Rationale: avoid two sources of truth for cost/decision data.

### D4: Hard constraints as Cedar `forbid()` + mutable eligibility config
Vendor role/modality eligibility is expressed as Cedar `forbid()` policies, gated on new Agent-entity attributes `vendor` / `modality` / `data_residency`. The eligibility *values* (Claude=lead-eligible/programmatic-ineligible; Codex/Gemini/opencode=programmatic-eligible) live mutably in `agent_profiles.metadata` / `agents.yaml`, NOT in code. Runtime changes invalidate the cache via the existing `NOTIFY policy_changed`. Rationale: the EULA is a moving input — a config edit must reorganise the topology.

### D5: Cost model — static price table + adapter tokens, estimates labelled
A versioned per-vendor price table (`eligibility.py` config) supplies metered-counterfactual rates. Token counts come from CLI/SDK adapter responses where available; where a CLI does not report usage, a heuristic estimate is used and the ledger entry is flagged `estimated: true`. The cumulative `(metered_baseline − actual_spend)` is the load-bearing metric; estimated entries are tracked separately so the headline number can be reported with and without estimates.

### D6: Probes on `WatchdogService`
ToS monitor and model canary register as `WatchdogService` periodic jobs (`WATCHDOG_INTERVAL_SECONDS`). The network-touching ToS fetch may alternatively run as a GitHub Actions cron when the coordinator deployment lacks egress. Both no-op cleanly when the instrument flag is off.

### D7: Single kill switch — `ARBITRAGE_INSTRUMENT_ENABLED`
Default `false`. When off: signal recording no-ops, probes do not schedule, and the router falls back to the existing default dispatch (identity behaviour). One flag, total removal — verified by a test that asserts default-off leaves dispatch unchanged.

### D8: Router is static-priority with a slot-in interface
`select_assignment(work_unit, feasible_set) -> assignment`: cheap-tier-first, spill on hard rate-limit (429), cohesion penalty to keep a work-package on one vendor. **No bandit, no temporal optimiser, no learned priors** in this slice. The interface is the seam where the deferred smart router slots in without touching the signal layer.

### D9: Tripwires are declarative thresholds that write learnings
Each tripwire (ToS-diff→freeze; enforcement→demote; savings<maintenance→economic-kill; canary-drift→invalidate-priors; integration>savings→collapse-granularity) is a declarative threshold evaluated against the signal substrate. A flip both (a) writes a `LearningEntry` recording the world-change and (b) sets a posture flag (e.g. a vendor freeze in `agent_profiles.metadata`) that the router's feasibility check then honours.

### D10: The contract boundary is the `contracts/` JSON schemas
Because Approach A spans two codebases, the coordination boundary is explicit: `arbitrage-signal.schema.json`, `cost-ledger-entry.schema.json`, `router-decision.schema.json`, `vendor-pricing-eligibility.schema.json`. Both the coordinator module and the skill validate against these — they are the only cross-codebase coupling.

### D11: Spec coordination, not duplication
The new `cross-vendor-arbitrage` capability spec explicitly fulfils the `observability` spec's unimplemented cost requirement and subsumes the `symphony` roadmap's `token-rate-limit-and-run-accounting` item by cross-reference. It references `agent-archetypes` for model resolution and `roadmap-orchestration` for learning emission.

## Risks & Mitigations

| Risk (from pressure test) | Mitigation in this design |
|---|---|
| Quota cliff is invisible | D2 logs every 429 with cumulative-usage-at-throttle — the throttles *are* the sparse cliff sensor. |
| Models mutate silently | D6 model canary fingerprints detect swaps under fixed names. |
| Cost data unobtainable | D5 degrades to labelled estimates rather than blocking; headline metric reportable with/without estimates. |
| Arbitrage stops paying | D9 economic-kill tripwire fires when cumulative savings < maintenance. |
| Cross-vendor integration eats savings silently | D9 integration-cost tripwire collapses granularity; integration cost is attributed to the splitting decision (signal family d). |
| Lock-in / churn | D4 keeps eligibility as mutable config; D8 keeps the router swappable. |
